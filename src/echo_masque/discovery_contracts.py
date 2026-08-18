"""Platform-neutral Character Discovery contracts and reserved future account boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class DiscoveryAttentionLevel(StrEnum):
    SCROLL_PAST = "scroll_past"
    NOTICE = "notice"
    OPEN = "open"
    WATCH = "watch"
    ENGAGE = "engage"


class DiscoveryMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    REVIEW = "review"
    AUTO = "auto"


class DiscoveryDecision(StrEnum):
    IGNORE = "ignore"
    REMEMBER = "remember"
    WOULD_SHARE = "would_share"
    PROPOSE_SHARE = "propose_share"
    SHARE = "share"


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    source: str
    canonical_key: str
    content_kind: str
    title: str
    description: str
    creator: str
    url: str
    thumbnail_url: str = ""
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiscoveryFetchRequest:
    queries: tuple[str, ...]
    region: str = ""
    language: str = ""
    limit: int = 20
    include_popular: bool = True


class DiscoverySourceAdapter(Protocol):
    source: str

    async def fetch_candidates(
        self,
        request: DiscoveryFetchRequest,
    ) -> tuple[DiscoveryCandidate, ...]: ...


# ---------------------------------------------------------------------------
# Reserved future external-account boundaries. These contracts intentionally
# contain no credential transport and no implementation that can mutate a social platform.
# ---------------------------------------------------------------------------


class PlatformCapability(StrEnum):
    READ_PUBLIC_CONTENT = "read_public_content"
    READ_HOME_FEED = "read_home_feed"
    READ_MENTIONS = "read_mentions"
    PUBLISH = "publish"
    REPLY = "reply"
    LIKE = "like"
    REPOST = "repost"
    FOLLOW = "follow"
    SAVE = "save"
    COMMENT = "comment"
    DIRECT_MESSAGE = "direct_message"


@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    deployment_id: str
    platform: str
    external_account_id: str
    handle: str
    display_name: str
    status: str
    capabilities: frozenset[PlatformCapability] = frozenset()
    credential_reference: str = ""


@dataclass(frozen=True, slots=True)
class AccountBinding:
    deployment_id: str
    platform: str
    platform_identity_ref: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class SocialIntent:
    deployment_id: str
    platform: str
    action: str
    content_ref: str
    target_ref: str = ""
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityRouter(Protocol):
    def allows(self, identity: PlatformIdentity, intent: SocialIntent) -> bool: ...


class PolicyGate(Protocol):
    def allows(self, identity: PlatformIdentity, intent: SocialIntent) -> bool: ...


class ActionExecutor(Protocol):
    async def execute(self, identity: PlatformIdentity, intent: SocialIntent) -> object: ...


__all__ = [
    "AccountBinding",
    "ActionExecutor",
    "CapabilityRouter",
    "DiscoveryAttentionLevel",
    "DiscoveryCandidate",
    "DiscoveryDecision",
    "DiscoveryFetchRequest",
    "DiscoveryMode",
    "DiscoverySourceAdapter",
    "PlatformCapability",
    "PlatformIdentity",
    "PolicyGate",
    "SocialIntent",
]
