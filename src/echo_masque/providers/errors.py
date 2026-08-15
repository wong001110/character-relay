"""Provider error taxonomy."""

from echo_masque.providers.base import ProviderQuotaObservation


class ProviderError(RuntimeError):
    """Base error for one model-provider call.

    ``reason_code`` is safe to expose to Runtime/Connector diagnostics. ``transient``
    describes whether a later turn can reasonably retry without a configuration change.
    ``deployment_fatal`` is intentionally narrower: a single failed provider turn must not
    disable an otherwise valid deployment.
    """

    reason_code = "provider_error"
    transient = False
    deployment_fatal = False


class ProviderTimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""

    reason_code = "provider_timeout"
    transient = True


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached or reported a temporary server failure."""

    reason_code = "provider_unavailable"
    transient = True


class ProviderRateLimitError(ProviderError):
    """The provider rejected the request because of a temporary rate limit."""

    reason_code = "provider_rate_limited"
    transient = True

    def __init__(
        self,
        message: str,
        *,
        quota_observations: tuple[ProviderQuotaObservation, ...] = (),
    ) -> None:
        super().__init__(message)
        self.quota_observations = quota_observations


class ProviderAuthenticationError(ProviderError):
    """The provider rejected the supplied credential."""

    reason_code = "provider_authentication_rejected"
    deployment_fatal = True


class ProviderProtocolError(ProviderError):
    """The provider returned a malformed or unsupported response."""

    reason_code = "provider_protocol_error"
    transient = True
