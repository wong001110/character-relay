"""Deliver generated image artifacts through a Character deployment's Discord identity."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from echo_masque.credentials import CredentialVault
from echo_masque.persistence import (
    ConversationMediaReferenceRepository,
    DeploymentRepository,
    DiscordIdentityRepository,
    GeneratedMediaArtifactRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.generated_media_models import GeneratedMediaArtifactRecord

_DISCORD_API = "https://discord.com/api/v10"
_WEBHOOK_SCOPE = "discord_webhook"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GeneratedMediaDeliveryResult:
    message_id: str
    attachment_url: str = ""


class GeneratedMediaDeliveryService:
    """Send one already-generated artifact exactly as the Character's configured identity."""

    def __init__(
        self,
        artifact_repository: GeneratedMediaArtifactRepository,
        deployment_repository: DeploymentRepository,
        identity_repository: DiscordIdentityRepository,
        credential_store: CredentialVault,
        *,
        discord_bot_token: SecretStr | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        conversation_media_repository: ConversationMediaReferenceRepository | None = None,
    ) -> None:
        self.artifacts = artifact_repository
        self.deployments = deployment_repository
        self.identities = identity_repository
        self.credentials = credential_store
        self.discord_bot_token = discord_bot_token
        self.http_transport = http_transport
        self.conversation_media = (
            conversation_media_repository
            or ConversationMediaReferenceRepository(artifact_repository.database)
        )

    async def deliver(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        channel_id: str,
        thread_id: str,
        artifact_id: str,
    ) -> GeneratedMediaDeliveryResult:
        artifact = self.artifacts.get(artifact_id, owner_id=owner_id)
        if artifact is None or artifact.deployment_id != deployment_id:
            raise RuntimeError("Generated image artifact is unavailable for this deployment.")
        deployment = self.deployments.get_deployment(deployment_id, owner_id)
        if deployment is None or deployment.status != "active":
            raise RuntimeError("Image generation deployment is no longer active.")
        if deployment.platform != "discord":
            raise RuntimeError("Generated image delivery currently supports Discord only.")

        identity = self.identities.get_identity(deployment.id, deployment.owner_id)
        mode = identity.mode if identity is not None else "webhook"
        if mode == "bot":
            result = await self._send_bot(
                channel_id=thread_id or channel_id,
                filename=artifact.filename,
                mime_type=artifact.mime_type,
                content=artifact.content,
            )
            self._register_route(
                deployment,
                channel_id=channel_id,
                thread_id=thread_id,
                message_id=result.message_id,
                webhook_id="",
            )
            self._remember_generated_reference(
                artifact,
                deployment,
                channel_id=channel_id,
                thread_id=thread_id,
                result=result,
            )
            return result

        binding = self.identities.get_binding(
            owner_id=owner_id,
            connection_id=deployment.connection_id,
            channel_id=channel_id,
        )
        if binding is None or binding.status != "active":
            raise RuntimeError("Character webhook is not ready for generated image delivery.")
        token = self.credentials.get_scope(
            owner_id=owner_id,
            scope_kind=_WEBHOOK_SCOPE,
            scope_id=binding.id,
        )
        if token is None:
            raise RuntimeError("Character webhook credential is unavailable.")

        query = {"wait": "true"}
        if thread_id:
            query["thread_id"] = thread_id
        url = (
            f"{_DISCORD_API}/webhooks/{binding.webhook_id}/"
            f"{token.get_secret_value()}?{urlencode(query)}"
        )
        payload: dict[str, object] = {"allowed_mentions": {"parse": []}}
        if identity is not None:
            payload["username"] = identity.display_name[:80]
            if identity.avatar_url:
                payload["avatar_url"] = identity.avatar_url
        async with self._client() as client:
            response = await client.post(
                url,
                data={"payload_json": json.dumps(payload, separators=(",", ":"))},
                files={
                    "files[0]": (
                        artifact.filename,
                        artifact.content,
                        artifact.mime_type,
                    )
                },
            )
        if response.is_error:
            raise RuntimeError(
                f"Discord generated-image webhook returned HTTP {response.status_code}."
            )
        result = self._delivery_result(response)
        self._register_route(
            deployment,
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=result.message_id,
            webhook_id=binding.webhook_id,
        )
        self._remember_generated_reference(
            artifact,
            deployment,
            channel_id=channel_id,
            thread_id=thread_id,
            result=result,
        )
        return result

    async def _send_bot(
        self,
        *,
        channel_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> GeneratedMediaDeliveryResult:
        if self.discord_bot_token is None:
            raise RuntimeError("Discord Bot credential is unavailable for image delivery.")
        async with self._client() as client:
            response = await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers={
                    "Authorization": f"Bot {self.discord_bot_token.get_secret_value()}",
                },
                data={
                    "payload_json": json.dumps(
                        {"allowed_mentions": {"parse": []}},
                        separators=(",", ":"),
                    )
                },
                files={"files[0]": (filename, content, mime_type)},
            )
        if response.is_error:
            raise RuntimeError(
                f"Discord generated-image message returned HTTP {response.status_code}."
            )
        return self._delivery_result(response)

    @staticmethod
    def _delivery_result(response: httpx.Response) -> GeneratedMediaDeliveryResult:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Discord generated-image delivery returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Discord generated-image delivery returned an invalid payload.")
        message_id = payload.get("id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise RuntimeError("Discord generated-image delivery did not return a message ID.")
        attachment_url = ""
        attachments = payload.get("attachments")
        if isinstance(attachments, list) and attachments:
            first = attachments[0]
            if isinstance(first, dict):
                raw_url = first.get("url")
                if isinstance(raw_url, str):
                    attachment_url = raw_url[:4096]
        return GeneratedMediaDeliveryResult(
            message_id=message_id.strip(),
            attachment_url=attachment_url,
        )

    def _register_route(
        self,
        deployment: CharacterDeploymentRecord,
        *,
        channel_id: str,
        thread_id: str,
        message_id: str,
        webhook_id: str,
    ) -> None:
        try:
            self.identities.register_message_routes(
                connection_id=deployment.connection_id,
                deployment_id=deployment.id,
                workspace_id=deployment.workspace_id,
                channel_id=channel_id,
                thread_id=thread_id,
                webhook_id=webhook_id,
                message_ids=[message_id],
            )
        except Exception as exc:
            # The media is already delivered. Never turn bookkeeping into a duplicate-send retry.
            logger.warning(
                "Unable to persist generated-image message route: deployment=%s message=%s error=%s",
                deployment.id,
                message_id,
                exc,
            )

    def _remember_generated_reference(
        self,
        artifact: GeneratedMediaArtifactRecord,
        deployment: CharacterDeploymentRecord,
        *,
        channel_id: str,
        thread_id: str,
        result: GeneratedMediaDeliveryResult,
    ) -> None:
        if not result.attachment_url:
            return
        try:
            self.conversation_media.remember_generated_reference(
                owner_id=deployment.owner_id,
                deployment_id=deployment.id,
                character_card_id=artifact.character_card_id,
                guild_id=deployment.workspace_id,
                channel_id=channel_id,
                thread_id=thread_id,
                message_id=result.message_id,
                source_key=f"generated:{artifact.media_key}",
                label=artifact.filename,
                source_uri=result.attachment_url,
            )
        except Exception as exc:
            # The image is already delivered. Reference bookkeeping must never cause a retry.
            logger.warning(
                (
                    "Unable to persist generated-image reference: "
                    "deployment=%s message=%s error=%s"
                ),
                deployment.id,
                result.message_id,
                exc,
            )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            transport=self.http_transport,
            follow_redirects=False,
            headers={"User-Agent": "CharacterRelay/0.4 GeneratedMediaRuntime"},
        )


__all__ = ["GeneratedMediaDeliveryResult", "GeneratedMediaDeliveryService"]
