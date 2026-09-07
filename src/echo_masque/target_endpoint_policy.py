"""Outbound endpoint admission for configurable targets and OpenAI-compatible providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from echo_masque.config import Settings


DEFAULT_PROVIDER_ALLOWED_ORIGINS = (
    "https://api.deepseek.com",
    "https://api.openai.com",
    "https://openrouter.ai",
)


class EndpointPolicyRejected(ValueError):
    """A configured outbound destination is outside the current runtime policy."""


def canonical_endpoint_origin(value: str, *, label: str = "Endpoint") -> str:
    """Return one credential-free HTTP(S) origin with its effective port made explicit."""

    try:
        parsed = urlsplit(value.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise EndpointPolicyRejected(f"{label} is not a valid HTTP(S) URL.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise EndpointPolicyRejected(f"{label} must be a credential-free HTTP(S) URL.")
    normalized_host = hostname.casefold().rstrip(".")
    if not normalized_host:
        raise EndpointPolicyRejected(f"{label} must include a hostname.")
    effective_port = port if port is not None else (443 if parsed.scheme == "https" else 80)
    host = (
        f"[{normalized_host}]"
        if ":" in normalized_host and not normalized_host.startswith("[")
        else normalized_host
    )
    return f"{parsed.scheme}://{host}:{effective_port}"


def validated_operator_origin(value: str) -> str:
    """Validate an operator allowlist entry rather than silently accepting URL paths or secrets."""

    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError("Allowed outbound origin is invalid.") from exc
    if (
        parsed.scheme != "https"
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Allowed outbound origin must be a credential-free HTTPS origin.")
    try:
        return canonical_endpoint_origin(candidate, label="Allowed outbound origin")
    except EndpointPolicyRejected as exc:
        raise ValueError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class TargetEndpointPolicy:
    """Exact-origin admission, intentionally separate from DNS or network-firewall controls."""

    environment: str
    provider_allowed_origins: frozenset[str]
    http_target_allowed_origins: frozenset[str]

    @classmethod
    def from_settings(cls, settings: Settings) -> TargetEndpointPolicy:
        return cls(
            environment=settings.environment,
            provider_allowed_origins=frozenset(
                canonical_endpoint_origin(item, label="Allowed provider origin")
                for item in settings.provider_allowed_origins
            ),
            http_target_allowed_origins=frozenset(
                canonical_endpoint_origin(item, label="Allowed HTTP target origin")
                for item in settings.http_target_allowed_origins
            ),
        )

    def require_provider_url(self, value: str) -> None:
        self._require(value, allowed_origins=self.provider_allowed_origins, kind="Provider")

    def require_http_target_url(self, value: str) -> None:
        self._require(value, allowed_origins=self.http_target_allowed_origins, kind="HTTP target")

    def _require(self, value: str, *, allowed_origins: frozenset[str], kind: str) -> None:
        origin = canonical_endpoint_origin(value, label=kind)
        if self.environment == "test":
            return
        if self.environment == "development":
            if origin.startswith("https://") or _is_local_http_origin(origin):
                return
            raise EndpointPolicyRejected(f"{kind} endpoint is not allowed in development.")
        if origin not in allowed_origins:
            raise EndpointPolicyRejected(f"{kind} endpoint origin is not approved.")


def _is_local_http_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "http" and hostname in {"localhost", "127.0.0.1", "::1"}


__all__ = [
    "DEFAULT_PROVIDER_ALLOWED_ORIGINS",
    "EndpointPolicyRejected",
    "TargetEndpointPolicy",
    "canonical_endpoint_origin",
    "validated_operator_origin",
]
