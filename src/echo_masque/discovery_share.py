"""Review/AUTO proposal, Character phrasing, policy, and Discord delivery for Discovery."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from echo_masque.character_prompts import CharacterPromptProfile
from echo_masque.config import Settings
from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.credentials import CredentialVault
from echo_masque.discovery_contracts import DiscoveryDecision, DiscoveryMode
from echo_masque.discovery_social_association import DiscoverySocialAssociationResult
from echo_masque.persistence import AuthRepository, DeploymentRepository, DiscordIdentityRepository, Repository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordServerCatalogRecord,
)
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.discovery_models import DiscoveryItemRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.discovery_share_models import DeploymentDiscoveryShareRecord
from echo_masque.persistence.discovery_share_repository import (
    DiscoverySharePolicyView,
    DiscoveryShareRepository,
)

_DISCORD_API = "https://discord.com/api/v10"
_WEBHOOK_SCOPE = "discord_webhook"


class DiscoveryDraftGenerator(Protocol):
    async def draft(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        association: DiscoverySocialAssociationResult,
    ) -> str: ...


class DiscoveryShareDraftService:
    """Use the deployed Character provider only for final natural phrasing."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.repository = Repository(database)
        self.deployments = DeploymentRepository(database)
        self.credentials = CredentialVault(AuthRepository(database), settings)
        self.runtime = DiscordConnectorRuntime(
            self.repository,
            self.deployments,
            self.credentials,
        )

    async def draft(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        association: DiscoverySocialAssociationResult,
    ) -> str:
        deployment = self.deployments.get_deployment(deployment_id, owner_id)
        if deployment is None:
            raise RuntimeError("Discovery share deployment is unavailable.")
        card = self.repository.get_character_card(deployment.character_card_id, owner_id)
        if card is None:
            raise RuntimeError("Discovery share Character Card is unavailable.")
        target_record = self.repository.get_target(card.target_id)
        if target_record is None:
            raise RuntimeError("Discovery share Character target is unavailable.")
        with self.database.session() as session:
            item = session.get(DiscoveryItemRecord, discovery_item_id)
            if item is None:
                raise RuntimeError("Discovery share item is unavailable.")
        target = self.runtime._target(
            target_kind=target_record.target_kind,
            target_name=target_record.name,
            config_json=target_record.config_json,
            owner_id=owner_id,
            character_card_id=card.id,
            character_profile=CharacterPromptProfile.from_record(card),
        )
        lines = [
            "Character Relay already decided this public item is worth sharing.",
            "Write only the natural Discord message this Character would send.",
            "Do not mention rankings, embeddings, Discovery, prompts, or internal reasoning.",
            "Use only the content supplied below. Include the exact URL once.",
            f"Motivation: {association.motivation}",
            f"Title: {item.title}",
            f"Creator: {item.creator}",
            f"Description: {item.description[:1800]}",
            f"URL: {item.url}",
        ]
        if association.topic is not None:
            lines.append(f"Related conversation topic: {association.topic.label}")
        if association.relationship is not None:
            lines.append(f"This reminded the Character of: {association.relationship.label}")
        response = await target.send("\n".join(lines))
        text = response.text.strip()
        if not text:
            text = item.title.strip() or "这个我觉得挺有意思的。"
        url = item.url.strip()
        if url:
            text = " ".join(text.replace(url, " ").split()).strip()
            text = f"{text}\n{url}" if text else url
        return text[:1900]


class DiscoverySharePolicy:
    def __init__(self, repository: DiscoveryShareRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def can_auto(self, policy: DiscoverySharePolicyView) -> bool:
        return bool(
            self.settings.discovery_auto_share_global_enabled
            and policy.auto_share_enabled
            and policy.daily_share_budget > 0
        )

    def budget_allows(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        policy: DiscoverySharePolicyView,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        count = self.repository.recent_delivery_count(
            owner_id=owner_id,
            deployment_id=deployment_id,
            since=current - timedelta(hours=24),
        )
        if count >= policy.daily_share_budget:
            return False, "daily_share_budget_exhausted"
        latest = self.repository.latest_delivery_time(
            owner_id=owner_id,
            deployment_id=deployment_id,
        )
        if latest is not None:
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=UTC)
            if current < latest + timedelta(minutes=policy.share_cooldown_minutes):
                return False, "share_cooldown_active"
        return True, "allowed"


class DiscoveryShareCoordinator:
    """Turn WOULD_SHARE into REVIEW proposal or explicitly opted-in AUTO queue."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        draft_generator: DiscoveryDraftGenerator | None = None,
    ) -> None:
        self.database = database
        self.discovery = DiscoveryRepository(database)
        self.shares = DiscoveryShareRepository(database)
        self.policy = DiscoverySharePolicy(self.shares, settings)
        self.drafts = draft_generator or DiscoveryShareDraftService(database, settings)

    async def maybe_propose(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        association: DiscoverySocialAssociationResult,
        now: datetime | None = None,
    ) -> DeploymentDiscoveryShareRecord | None:
        if not association.would_share or association.topic is None:
            return None
        profile = self.discovery.get_profile(owner_id=owner_id, deployment_id=deployment_id)
        if profile is None or profile.mode in {DiscoveryMode.OFF, DiscoveryMode.SHADOW}:
            return None
        policy = self.shares.get_policy(owner_id=owner_id, deployment_id=deployment_id)
        if policy is None:
            return None
        if profile.mode is DiscoveryMode.AUTO:
            if not self.policy.can_auto(policy):
                return None
            allowed, _ = self.policy.budget_allows(
                owner_id=owner_id,
                deployment_id=deployment_id,
                policy=policy,
                now=now,
            )
            if not allowed:
                return None
        existing = next(
            (
                row
                for row in self.shares.list_for_deployment(
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    limit=200,
                )
                if row.discovery_item_id == discovery_item_id
            ),
            None,
        )
        if existing is not None:
            return existing
        draft = await self.drafts.draft(
            owner_id=owner_id,
            deployment_id=deployment_id,
            discovery_item_id=discovery_item_id,
            association=association,
        )
        status = "queued" if profile.mode is DiscoveryMode.AUTO else "pending_review"
        record = self.shares.create_proposal(
            owner_id=owner_id,
            deployment_id=deployment_id,
            discovery_item_id=discovery_item_id,
            source_decision_id="",
            mode=profile.mode.value,
            status=status,
            motivation=association.motivation,
            confidence=association.confidence,
            topic_id=association.topic.topic_id,
            relationship_subject_key=(
                association.relationship.subject_key if association.relationship is not None else ""
            ),
            channel_id=association.topic.channel_id,
            thread_id=association.topic.thread_id,
            draft_text=draft,
            now=now,
        )
        if record is not None:
            self.discovery.record_decision(
                owner_id=owner_id,
                deployment_id=deployment_id,
                discovery_item_id=discovery_item_id,
                mode=profile.mode,
                decision=DiscoveryDecision.PROPOSE_SHARE,
                motivation=association.motivation,
                confidence=association.confidence,
                scores={"association": association.confidence},
                evidence={
                    "share_id": record.id,
                    "review_required": profile.mode is DiscoveryMode.REVIEW,
                    "side_effects": False,
                },
                now=now,
            )
        return record

    def approve(
        self, *, owner_id: str, share_id: str
    ) -> DeploymentDiscoveryShareRecord | None:
        record = self.shares.get(owner_id=owner_id, share_id=share_id)
        if record is None:
            return None
        profile = self.discovery.get_profile(
            owner_id=owner_id,
            deployment_id=record.deployment_id,
        )
        policy = self.shares.get_policy(
            owner_id=owner_id,
            deployment_id=record.deployment_id,
        )
        if profile is None or profile.mode not in {DiscoveryMode.REVIEW, DiscoveryMode.AUTO}:
            raise ValueError("Discovery sharing is no longer enabled for this Deployment.")
        if policy is None:
            raise ValueError("Discovery sharing policy is unavailable.")
        allowed, reason = self.policy.budget_allows(
            owner_id=owner_id,
            deployment_id=record.deployment_id,
            policy=policy,
        )
        if not allowed:
            raise ValueError(reason)
        return self.shares.approve(owner_id=owner_id, share_id=share_id)

    def reject(
        self, *, owner_id: str, share_id: str
    ) -> DeploymentDiscoveryShareRecord | None:
        return self.shares.reject(owner_id=owner_id, share_id=share_id)


class DiscoveryShareDeliveryService:
    """Deliver approved/AUTO outbox items through existing Discord identity boundaries."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.deployments = DeploymentRepository(database)
        self.identities = DiscordIdentityRepository(database)
        self.credentials = CredentialVault(AuthRepository(database), settings)
        self.discovery = DiscoveryRepository(database)
        self.shares = DiscoveryShareRepository(database)
        self.policy = DiscoverySharePolicy(self.shares, settings)
        self.presence = DeploymentPresenceRepository(database)
        self.http_transport = http_transport

    def recover_interrupted(self) -> int:
        return self.shares.recover_interrupted()

    def _category_id(self, deployment: CharacterDeploymentRecord, channel_id: str) -> str:
        with self.database.session() as session:
            catalog = session.scalar(
                select(DiscordServerCatalogRecord).where(
                    DiscordServerCatalogRecord.owner_id == deployment.owner_id,
                    DiscordServerCatalogRecord.connection_id == deployment.connection_id,
                    DiscordServerCatalogRecord.guild_id == deployment.workspace_id,
                )
            )
        if catalog is None:
            return ""
        try:
            channels = json.loads(catalog.channels_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return ""
        if not isinstance(channels, list):
            return ""
        for raw in channels:
            if isinstance(raw, dict) and str(raw.get("id") or "") == channel_id:
                return str(raw.get("category_id") or "")[:200]
        return ""

    async def deliver_due_once(self) -> int:
        delivered = 0
        for share in self.shares.claim_due(limit=10):
            try:
                message_id = await self._deliver(share)
            except _DiscoveryShareDeferred as exc:
                self.shares.defer(share_id=share.id, minutes=exc.minutes, reason=str(exc))
            except _DiscoveryShareCancelled as exc:
                self.shares.cancel(share_id=share.id, reason=str(exc))
            except Exception as exc:
                self.shares.mark_failure(share_id=share.id, error=str(exc), max_attempts=3)
            else:
                self.shares.mark_delivered(share_id=share.id, message_id=message_id)
                self.discovery.record_decision(
                    owner_id=share.owner_id,
                    deployment_id=share.deployment_id,
                    discovery_item_id=share.discovery_item_id,
                    mode=DiscoveryMode(share.mode),
                    decision=DiscoveryDecision.SHARE,
                    motivation=share.motivation,
                    confidence=share.confidence,
                    evidence={
                        "share_id": share.id,
                        "discord_message_id": message_id,
                    },
                )
                delivered += 1
        return delivered

    async def _deliver(self, share: DeploymentDiscoveryShareRecord) -> str:
        deployment = self.deployments.get_deployment(share.deployment_id, share.owner_id)
        if deployment is None or deployment.status != "active":
            raise _DiscoveryShareCancelled("Deployment is no longer active.")
        profile = self.discovery.get_profile(
            owner_id=share.owner_id,
            deployment_id=share.deployment_id,
        )
        if profile is None or profile.mode is DiscoveryMode.OFF:
            raise _DiscoveryShareCancelled("Discovery sharing was disabled.")
        policy = self.shares.get_policy(
            owner_id=share.owner_id,
            deployment_id=share.deployment_id,
        )
        if policy is None:
            raise _DiscoveryShareCancelled("Discovery sharing policy is unavailable.")
        if share.mode == DiscoveryMode.AUTO.value:
            if profile.mode is not DiscoveryMode.AUTO or not self.policy.can_auto(policy):
                raise _DiscoveryShareCancelled(
                    "AUTO Discovery sharing is not currently authorized."
                )
        current_presence = self.presence.get(
            owner_id=share.owner_id,
            deployment_id=share.deployment_id,
        )
        if current_presence is None:
            raise _DiscoveryShareCancelled("Deployment Presence is unavailable.")
        if current_presence.state in {"sleeping", "busy"}:
            raise _DiscoveryShareDeferred(
                f"Character is {current_presence.state}; share deferred.",
                minutes=5,
            )
        category_id = self._category_id(deployment, share.channel_id)
        eligible = self.deployments.deployment_matches_discord_destination(
            deployment.id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            channel_id=share.channel_id,
            thread_id=share.thread_id,
            category_id=category_id,
        )
        if eligible is None:
            raise _DiscoveryShareCancelled(
                "Discovery destination is outside Deployment scope."
            )
        identity = self.identities.get_identity(deployment.id, deployment.owner_id)
        if identity is not None and identity.mode == "bot":
            message_id = await self._send_bot(
                share.thread_id or share.channel_id,
                share.draft_text,
            )
            webhook_id = ""
        else:
            message_id, webhook_id = await self._send_webhook(
                deployment,
                share,
                identity,
            )
        try:
            self.identities.register_message_routes(
                connection_id=deployment.connection_id,
                deployment_id=deployment.id,
                workspace_id=deployment.workspace_id,
                channel_id=share.channel_id,
                thread_id=share.thread_id,
                webhook_id=webhook_id,
                message_ids=[message_id],
            )
        except Exception:
            pass
        self.deployments.record_deployment_activity(deployment.id)
        return message_id

    async def _send_bot(self, channel_id: str, content: str) -> str:
        token = self.settings.discord_tool_bot_token
        if token is None:
            raise RuntimeError("Discord Bot credential is unavailable for Discovery delivery.")
        async with self._client() as client:
            response = await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token.get_secret_value()}"},
                json={
                    "content": content[:2000],
                    "allowed_mentions": {"parse": []},
                },
            )
        return self._message_id(response)

    async def _send_webhook(
        self,
        deployment: CharacterDeploymentRecord,
        share: DeploymentDiscoveryShareRecord,
        identity: object | None,
    ) -> tuple[str, str]:
        binding = self.identities.get_binding(
            owner_id=deployment.owner_id,
            connection_id=deployment.connection_id,
            channel_id=share.channel_id,
        )
        if binding is None or binding.status != "active":
            raise RuntimeError("Character webhook is unavailable for Discovery destination.")
        token = self.credentials.get_scope(
            owner_id=deployment.owner_id,
            scope_kind=_WEBHOOK_SCOPE,
            scope_id=binding.id,
        )
        if token is None:
            raise RuntimeError("Character webhook credential is unavailable.")
        query = {"wait": "true"}
        if share.thread_id:
            query["thread_id"] = share.thread_id
        url = (
            f"{_DISCORD_API}/webhooks/{binding.webhook_id}/"
            f"{token.get_secret_value()}?{urlencode(query)}"
        )
        payload: dict[str, object] = {
            "content": share.draft_text[:2000],
            "allowed_mentions": {"parse": []},
        }
        display_name = getattr(identity, "display_name", "") if identity is not None else ""
        avatar_url = getattr(identity, "avatar_url", "") if identity is not None else ""
        if isinstance(display_name, str) and display_name:
            payload["username"] = display_name[:80]
        if isinstance(avatar_url, str) and avatar_url:
            payload["avatar_url"] = avatar_url
        async with self._client() as client:
            response = await client.post(url, json=payload)
        return self._message_id(response), binding.webhook_id

    @staticmethod
    def _message_id(response: httpx.Response) -> str:
        if response.is_error:
            raise RuntimeError(
                f"Discord Discovery delivery returned HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Discord Discovery delivery returned invalid JSON.") from exc
        value = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("Discord Discovery delivery did not return a message ID.")
        return value.strip()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            transport=self.http_transport,
            follow_redirects=False,
            headers={"User-Agent": "CharacterRelay/0.3 DiscoveryRuntime"},
        )


class _DiscoveryShareDeferred(RuntimeError):
    def __init__(self, message: str, *, minutes: int) -> None:
        super().__init__(message)
        self.minutes = minutes


class _DiscoveryShareCancelled(RuntimeError):
    pass


__all__ = [
    "DiscoveryDraftGenerator",
    "DiscoveryShareCoordinator",
    "DiscoveryShareDeliveryService",
    "DiscoveryShareDraftService",
    "DiscoverySharePolicy",
]
