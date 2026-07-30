"""Append-only audit coverage for sensitive workspace HTTP operations."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from echo_masque.auth import AuthContext
from echo_masque.persistence import AuthRepository

_DELETE_PREFIXES = (
    "/api/characters/",
    "/api/scenarios/",
    "/api/test-packs/",
    "/api/experiments/",
    "/api/matrices/",
)


class SensitiveAuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, repository: AuthRepository) -> None:
        super().__init__(app)
        self.repository = repository

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        if response.status_code >= 400:
            return response
        context = getattr(request.state, "auth_context", None)
        if not isinstance(context, AuthContext):
            return response
        path = request.url.path
        action: str | None = None
        resource_type = "workspace"
        if request.method == "DELETE" and path.startswith(_DELETE_PREFIXES):
            action = "workspace.resource_deleted"
            resource_type = path.split("/", maxsplit=3)[2]
        elif request.method == "GET" and path == "/api/admin/workspace/export":
            action = "workspace.exported"
        elif request.method == "POST" and path == "/api/admin/workspace/import":
            action = "workspace.imported"
        if action is not None:
            self.repository.audit(
                actor_user_id=context.user.id,
                action=action,
                resource_type=resource_type,
                resource_id=path.rsplit("/", maxsplit=1)[-1],
                metadata={"method": request.method, "path": path},
            )
        return response
