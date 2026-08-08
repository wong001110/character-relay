"""Background delivery service for scheduled character reminders."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from echo_masque.credentials import CredentialVault
from echo_masque.persistence import DeploymentRepository, DiscordIdentityRepository
from echo_masque.persistence.scheduled_reminder_models import ScheduledReminderRecord
from echo_masque.persistence.scheduled_reminder_repository import ScheduledReminderRepository

_DISCORD_API = "https://discord.com/api/v10"
_WEBHOOK_SCOPE = "discord_webhook"


class ScheduledReminderDeliveryService:
    """Poll persistent reminders and deliver them through the deployment's Discord identity."""

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
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self.repository.recover_interrupted()
        self.repository.purge_orphans()
        self._task = asyncio.create_task(
            self._run(),
            name="character-relay-reminder-delivery",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

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
            await self._send_bot_message(
                channel_id=reminder.thread_id or reminder.channel_id,
                content=content,
                allowed_users=allowed_users,
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

    async def _send_bot_message(
        self,
        *,
        channel_id: str,
        content: str,
        allowed_users: list[str],
    ) -> None:
        if self.discord_bot_token is None:
            raise RuntimeError("Discord Bot credential is unavailable for reminder delivery.")
        async with self._client() as client:
            response = await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers={
                    "Authorization": f"Bot {self.discord_bot_token.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "content": content,
                    "allowed_mentions": (
                        {"parse": [], "users": allowed_users}
                        if allowed_users
                        else {"parse": []}
                    ),
                },
            )
        if response.is_error:
            raise RuntimeError(f"Discord reminder message returned HTTP {response.status_code}.")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            transport=self.http_transport,
            follow_redirects=False,
            headers={"User-Agent": "CharacterRelay/0.2 ReminderRuntime"},
        )
