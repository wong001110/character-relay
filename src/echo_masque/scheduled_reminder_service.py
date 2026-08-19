"""Background delivery service for scheduled reminders and Presence system notices."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from pydantic import SecretStr

from echo_masque.credentials import CredentialVault
from echo_masque.deployment_activity_scheduler import DeploymentActivityScheduler
from echo_masque.deployment_presence_rhythm import DeploymentPresenceRhythmService
from echo_masque.deployment_presence_scheduler import DeploymentPresenceScheduler
from echo_masque.media_retention import MediaRetentionService
from echo_masque.persistence import DeploymentRepository, DiscordIdentityRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_notice_models import (
    DeploymentPresenceNoticeRecord,
)
from echo_masque.persistence.deployment_presence_notice_repository import (
    DeploymentPresenceNoticeRepository,
)
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.scheduled_reminder_models import ScheduledReminderRecord
from echo_masque.persistence.scheduled_reminder_repository import ScheduledReminderRepository
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository

_DISCORD_API = "https://discord.com/api/v10"
_WEBHOOK_SCOPE = "discord_webhook"

logger = logging.getLogger(__name__)


class ScheduledReminderDeliveryService:
    """Poll persistent reminders and Bot-only Deployment Presence notices."""

    def __init__(
        self,
        repository: ScheduledReminderRepository,
        deployment_repository: DeploymentRepository,
        identity_repository: DiscordIdentityRepository,
        credential_store: CredentialVault,
        *,
        discord_bot_token: SecretStr | None = None,
        poll_seconds: int = 5,
        retry_seconds: int = 30,
        max_attempts: int = 3,
        http_transport: httpx.AsyncBaseTransport | None = None,
        media_retention_service: MediaRetentionService | None = None,
        presence_scheduler: DeploymentPresenceScheduler | None = None,
        activity_scheduler: DeploymentActivityScheduler | None = None,
    ) -> None:
        self.repository = repository
        self.deployment_repository = deployment_repository
        self.identity_repository = identity_repository
        self.credential_store = credential_store
        self.discord_bot_token = discord_bot_token
        self.poll_seconds = max(2, poll_seconds)
        self.retry_seconds = max(5, retry_seconds)
        self.max_attempts = max(1, max_attempts)
        self.http_transport = http_transport
        self.presence_notices = DeploymentPresenceNoticeRepository(repository.database)
        self.presence = DeploymentPresenceRepository(repository.database)
        self.server_runtime = ServerRuntimeRepository(repository.database)
        self.presence_scheduler = presence_scheduler or DeploymentPresenceScheduler(
            DeploymentPresenceRhythmService(repository.database)
        )
        self.activity_scheduler = activity_scheduler
        self.media_retention_service = (
            media_retention_service
            or MediaRetentionService.for_database(repository.database)
        )
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self.repository.recover_interrupted()
        self.presence_notices.recover_interrupted()
        self.repository.purge_orphans()
        await self.media_retention_service.start()
        await self.presence_scheduler.start()
        if self.activity_scheduler is not None:
            await self.activity_scheduler.start()
        self._task = asyncio.create_task(
            self._run(),
            name="character-relay-reminder-delivery",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self.activity_scheduler is not None:
            await self.activity_scheduler.stop()
        await self.presence_scheduler.stop()
        await self.media_retention_service.stop()

    async def deliver_due_once(self) -> int:
        records = self.repository.claim_due(limit=20)
        delivered = 0
        for record in records:
            try:
                await self._deliver(record)
            except Exception as exc:
                self.repository.mark_failure(
                    record.id,
                    str(exc),
                    max_attempts=self.max_attempts,
                    retry_seconds=self.retry_seconds,
                )
            else:
                self.repository.mark_delivered(record.id)
                delivered += 1

        notices = self.presence_notices.claim_due(limit=20)
        for notice in notices:
            try:
                await self._deliver_presence_notice(notice)
            except Exception as exc:
                self.presence_notices.mark_failure(
                    notice.id,
                    str(exc),
                    max_attempts=self.max_attempts,
                    retry_seconds=self.retry_seconds,
                )
            else:
                self.presence_notices.mark_delivered(notice.id)
                delivered += 1
        return delivered

    async def _run(self) -> None:
        try:
            while True:
                await self.deliver_due_once()
                await asyncio.sleep(self.poll_seconds)
        except asyncio.CancelledError:
            raise

    async def _deliver(self, reminder: ScheduledReminderRecord) -> None:
        if reminder.platform != "discord":
            raise RuntimeError("Scheduled reminder delivery currently supports Discord only.")
        deployment = self.deployment_repository.get_deployment(
            reminder.deployment_id,
            reminder.owner_id,
        )
        if deployment is None or deployment.status != "active":
            raise RuntimeError("Reminder deployment is no longer active.")
        identity = self.identity_repository.get_identity(deployment.id, deployment.owner_id)
        mode = identity.mode if identity is not None else "webhook"
        content = reminder.reminder_text.strip()
        allowed_users: list[str] = []
        if reminder.target_user_id:
            content = f"<@{reminder.target_user_id}> {content}"
            allowed_users = [reminder.target_user_id]
        content = content[:2000]

        if mode == "bot":
            message_id = await self._send_bot_message(
                channel_id=reminder.thread_id or reminder.channel_id,
                content=content,
                allowed_users=allowed_users,
            )
            self._register_message_route(
                reminder,
                deployment,
                message_id=message_id,
                webhook_id="",
            )
            return

        binding = self.identity_repository.get_binding(
            owner_id=reminder.owner_id,
            connection_id=reminder.connection_id,
            channel_id=reminder.channel_id,
        )
        if binding is None or binding.status != "active":
            raise RuntimeError("Character webhook is not ready for this reminder destination.")
        token = self.credential_store.get_scope(
            owner_id=reminder.owner_id,
            scope_kind=_WEBHOOK_SCOPE,
            scope_id=binding.id,
        )
        if token is None:
            raise RuntimeError("Character webhook credential is unavailable.")
        query = {"wait": "true"}
        if reminder.thread_id:
            query["thread_id"] = reminder.thread_id
        url = (
            f"{_DISCORD_API}/webhooks/{binding.webhook_id}/"
            f"{token.get_secret_value()}?{urlencode(query)}"
        )
        payload: dict[str, object] = {
            "content": content,
            "allowed_mentions": (
                {"parse": [], "users": allowed_users}
                if allowed_users
                else {"parse": []}
            ),
        }
        if identity is not None:
            payload["username"] = identity.display_name[:80]
            if identity.avatar_url:
                payload["avatar_url"] = identity.avatar_url
        async with self._client() as client:
            response = await client.post(url, json=payload)
        if response.is_error:
            raise RuntimeError(f"Discord reminder webhook returned HTTP {response.status_code}.")
        self._register_message_route(
            reminder,
            deployment,
            message_id=self._message_id(response),
            webhook_id=binding.webhook_id,
        )

    async def _deliver_presence_notice(
        self,
        notice: DeploymentPresenceNoticeRecord,
    ) -> None:
        """Deliver Runtime status through the real Bot identity, never the Character webhook."""

        deployment = self.deployment_repository.get_deployment(
            notice.deployment_id,
            notice.owner_id,
        )
        if deployment is None or deployment.status != "active":
            raise RuntimeError("Presence notice deployment is no longer active.")
        if notice.notice_type != "sleeping":
            raise RuntimeError(f"Unsupported Presence notice type: {notice.notice_type}")

        presence = self.presence.get(
            owner_id=notice.owner_id,
            deployment_id=notice.deployment_id,
        )
        # A queued notice can become stale before the background poll delivers it. Never tell
        # the room that a Character is asleep after the authoritative Presence has already moved on.
        if presence is None or presence.state != "sleeping":
            return

        content = f"🌙 {notice.character_display_name} 当前正在睡觉。"
        if presence.expected_end_at is not None:
            timezone = self.server_runtime.resolve_timezone(
                owner_id=deployment.owner_id,
                connection_id=deployment.connection_id,
                guild_id=deployment.workspace_id,
            )
            try:
                wake_at = presence.expected_end_at.astimezone(ZoneInfo(timezone))
                content = (
                    f"🌙 {notice.character_display_name} 当前正在睡觉\uFF0C"
                    f"预计约 {wake_at:%H:%M} 醒来。"
                )
            except (ValueError, KeyError):
                pass
        await self._send_bot_message(
            channel_id=notice.thread_id or notice.channel_id,
            content=content[:2000],
            allowed_users=[],
            reply_to_message_id=notice.source_message_id,
        )

    async def _send_bot_message(
        self,
        *,
        channel_id: str,
        content: str,
        allowed_users: list[str],
        reply_to_message_id: str = "",
    ) -> str:
        if self.discord_bot_token is None:
            raise RuntimeError("Discord Bot credential is unavailable for reminder delivery.")
        payload: dict[str, object] = {
            "content": content,
            "allowed_mentions": (
                {"parse": [], "users": allowed_users}
                if allowed_users
                else {"parse": []}
            ),
        }
        if reply_to_message_id:
            payload["message_reference"] = {
                "message_id": reply_to_message_id,
                "fail_if_not_exists": False,
            }
        async with self._client() as client:
            response = await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers={
                    "Authorization": f"Bot {self.discord_bot_token.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.is_error:
            raise RuntimeError(f"Discord reminder message returned HTTP {response.status_code}.")
        return self._message_id(response)

    @staticmethod
    def _message_id(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Discord reminder delivery returned invalid JSON.") from exc
        message_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(message_id, str) or not message_id.strip():
            raise RuntimeError("Discord reminder delivery did not return a message ID.")
        return message_id.strip()

    def _register_message_route(
        self,
        reminder: ScheduledReminderRecord,
        deployment: CharacterDeploymentRecord,
        *,
        message_id: str,
        webhook_id: str,
    ) -> None:
        try:
            self.identity_repository.register_message_routes(
                connection_id=deployment.connection_id,
                deployment_id=deployment.id,
                workspace_id=deployment.workspace_id,
                channel_id=reminder.channel_id,
                thread_id=reminder.thread_id,
                webhook_id=webhook_id,
                message_ids=[message_id],
            )
        except Exception as exc:
            # Delivery already happened. Route bookkeeping must never turn a successful
            # side effect into a retry that could duplicate the reminder.
            logger.warning(
                (
                    "Unable to persist Discord reminder message route: "
                    "deployment=%s message=%s error=%s"
                ),
                reminder.deployment_id,
                message_id,
                exc,
            )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            transport=self.http_transport,
            follow_redirects=False,
            headers={"User-Agent": "CharacterRelay/0.2 ReminderRuntime"},
        )
