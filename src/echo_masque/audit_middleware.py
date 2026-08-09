"""Append-only audit coverage for sensitive workspace HTTP operations."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager, nullcontext

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from echo_masque.auth import AuthContext
from echo_masque.persistence import AuthRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.providers.trace import provider_trace_scope

_DELETE_PREFIXES = (
    "/api/characters/",
    "/api/scenarios/",
    "/api/test-packs/",
    "/api/experiments/",
    "/api/matrices/",
)
_DISCORD_MESSAGE_PATH = "/api/connectors/discord/messages"


class SensitiveAuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, repository: AuthRepository) -> None:
        super().__init__(app)
        self.repository = repository

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_scope: AbstractContextManager[None] = nullcontext()
        if request.method == "POST" and request.url.path == _DISCORD_MESSAGE_PATH:
            trace_scope = await self._discord_trace_scope(request)

        with trace_scope:
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

    @staticmethod
    async def _discord_trace_scope(request: Request) -> AbstractContextManager[None]:
        """Resolve connector-owned trace scope without trusting model-provided identifiers."""

        try:
            payload = json.loads((await request.body()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return nullcontext()
        if not isinstance(payload, dict):
            return nullcontext()
        deployment_id = str(payload.get("deployment_id", "")).strip()
        if not deployment_id:
            return nullcontext()

        database = getattr(request.app.state, "database", None)
        if database is None:
            return nullcontext()
        with database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None:
                return nullcontext()
            return provider_trace_scope(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
                character_card_id=deployment.character_card_id,
            )
