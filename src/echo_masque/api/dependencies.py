"""Shared authentication and authorization dependencies."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from echo_masque.auth import AuthContext, AuthenticatedUser, AuthService
from echo_masque.config import Settings

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def auth_service(request: Request) -> AuthService:
    return cast(AuthService, request.app.state.auth_service)


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def optional_auth_context(
    request: Request,
    bearer_token: Annotated[str | None, Depends(_oauth2)],
) -> AuthContext | None:
    resolved = settings(request)
    token = bearer_token or request.cookies.get(resolved.auth_cookie_name)
    if token:
        context = auth_service(request).resolve(token)
        if context is not None:
            request.state.auth_context = context
            return context
    if resolved.environment != "production" and resolved.legacy_local_user_enabled:
        legacy_owner = request.headers.get("X-Echo-User", "local-user")
        fallback = auth_service(request).development_context(legacy_owner)
        if fallback is not None:
            request.state.auth_context = fallback
            return fallback
    return None


def current_auth_context(
    context: Annotated[AuthContext | None, Depends(optional_auth_context)],
) -> AuthContext:
    if context is not None:
        return context
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user(
    context: Annotated[AuthContext, Depends(current_auth_context)],
) -> AuthenticatedUser:
    return context.user


def require_admin(
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    legacy_header: Annotated[str | None, Header(alias="X-Echo-Admin")] = None,
) -> AuthenticatedUser:
    if context.user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required.")
    if context.session_id is not None:
        return context.user
    resolved = settings(request)
    if (
        resolved.environment != "production"
        and resolved.legacy_local_user_enabled
        and legacy_header is not None
    ):
        request.state.legacy_admin = True
        return context.user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authenticated Admin session required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


OptionalAuthContextDependency = Annotated[
    AuthContext | None,
    Depends(optional_auth_context),
]
AuthContextDependency = Annotated[AuthContext, Depends(current_auth_context)]
CurrentUserDependency = Annotated[AuthenticatedUser, Depends(current_user)]
AdminUserDependency = Annotated[AuthenticatedUser, Depends(require_admin)]
