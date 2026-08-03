"""Server-enforced mutation boundary for the shared public Demo account."""

from __future__ import annotations

from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from echo_masque.auth import AuthService
from echo_masque.config import Settings
from echo_masque.public_demo import is_public_demo_email

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ALLOWED_POST_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/register",
    "/api/comparisons",
    "/api/trials",
}


class PublicDemoReadOnlyMiddleware(BaseHTTPMiddleware):
    """Allow test execution while rejecting shared-workspace mutations."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        settings = cast(Settings, request.app.state.settings)
        if not settings.public_demo_enabled:
            return await call_next(request)

        context = self._resolve_context(request)
        if context is None or not is_public_demo_email(context.user.email):
            return await call_next(request)

        path = request.url.path
        if request.method in _SAFE_METHODS:
            if path == "/api/auth/sessions":
                return self._blocked()
            return await call_next(request)
        if request.method == "POST" and self._allowed_post(path):
            return await call_next(request)
        return self._blocked()

    @staticmethod
    def _allowed_post(path: str) -> bool:
        if path in _ALLOWED_POST_PATHS:
            return True
        if path.startswith("/api/trials/") and path.endswith("/cancel"):
            return True
        return path.startswith("/api/experiments/") and path.endswith("/rerun")

    @staticmethod
    def _blocked() -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "The shared Demo account is read-only. "
                    "Character, credential, workspace, account, Matrix, and authoring "
                    "mutations are disabled."
                )
            },
            headers={"Cache-Control": "no-store"},
        )

    @staticmethod
    def _resolve_context(request: Request):
        settings = cast(Settings, request.app.state.settings)
        service = cast(AuthService, request.app.state.auth_service)
        authorization = request.headers.get("authorization", "")
        token: str | None = None
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not token:
            token = request.cookies.get(settings.auth_cookie_name)
        if not token:
            return None
        return service.resolve(token)


__all__ = ["PublicDemoReadOnlyMiddleware"]
