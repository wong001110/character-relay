"""Account registration, login, logout, and session management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, SecretStr

from echo_masque.api.dependencies import AuthContextDependency
from echo_masque.auth import (
    AuthenticatedUser,
    AuthenticationError,
    AuthService,
    DuplicateAccountError,
    RegistrationClosedError,
)
from echo_masque.config import Settings
from echo_masque.persistence.models import AuthSessionRecord

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=256)


class UserView(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["user", "admin"]

    @classmethod
    def from_user(cls, user: AuthenticatedUser) -> UserView:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        )


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserView


class AuthConfigView(BaseModel):
    registration_enabled: bool
    authentication_required: bool


class SessionView(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool

    @classmethod
    def from_record(
        cls,
        record: AuthSessionRecord,
        *,
        current_session_id: str | None,
    ) -> SessionView:
        return cls(
            id=record.id,
            created_at=record.created_at,
            last_seen_at=record.last_seen_at,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            current=record.id == current_session_id,
        )


def service(request: Request) -> AuthService:
    return cast(AuthService, request.app.state.auth_service)


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _set_session_cookie(response: Response, resolved: Settings, token: str) -> None:
    response.set_cookie(
        key=resolved.auth_cookie_name,
        value=token,
        max_age=resolved.auth_session_ttl_seconds,
        httponly=True,
        secure=resolved.environment == "production" or resolved.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/config", response_model=AuthConfigView)
def auth_config(request: Request) -> AuthConfigView:
    resolved = settings(request)
    return AuthConfigView(
        registration_enabled=(
            resolved.environment != "production" or resolved.public_registration_enabled
        ),
        authentication_required=(
            resolved.environment == "production" or not resolved.legacy_local_user_enabled
        ),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
) -> AuthResponse:
    auth = service(request)
    try:
        auth.register(
            email=payload.email,
            display_name=payload.display_name,
            password=payload.password.get_secret_value(),
        )
        issued = auth.login(
            email=payload.email,
            password=payload.password.get_secret_value(),
            user_agent=request.headers.get("user-agent"),
        )
    except RegistrationClosedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DuplicateAccountError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _set_session_cookie(response, settings(request), issued.token)
    expires_at = issued.context.expires_at
    if expires_at is None:
        raise RuntimeError("A persisted login must have an expiry.")
    return AuthResponse(
        access_token=issued.token,
        expires_at=expires_at,
        user=UserView.from_user(issued.context.user),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    try:
        issued = service(request).login(
            email=payload.email,
            password=payload.password.get_secret_value(),
            user_agent=request.headers.get("user-agent"),
        )
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc
    _set_session_cookie(response, settings(request), issued.token)
    expires_at = issued.context.expires_at
    if expires_at is None:
        raise RuntimeError("A persisted login must have an expiry.")
    return AuthResponse(
        access_token=issued.token,
        expires_at=expires_at,
        user=UserView.from_user(issued.context.user),
    )


@router.get("/me", response_model=UserView)
def me(context: AuthContextDependency) -> UserView:
    return UserView.from_user(context.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    context: AuthContextDependency,
) -> None:
    if context.session_id is not None:
        service(request).revoke_session(context.session_id, user_id=context.user.id)
    response.delete_cookie(
        key=settings(request).auth_cookie_name,
        path="/",
        httponly=True,
        secure=settings(request).environment == "production"
        or settings(request).auth_cookie_secure,
        samesite="lax",
    )


@router.get("/sessions", response_model=list[SessionView])
def sessions(request: Request, context: AuthContextDependency) -> list[SessionView]:
    return [
        SessionView.from_record(item, current_session_id=context.session_id)
        for item in service(request).list_sessions(context.user.id)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str,
    request: Request,
    context: AuthContextDependency,
) -> None:
    if not service(request).revoke_session(session_id, user_id=context.user.id):
        raise HTTPException(status_code=404, detail="Session not found.")
