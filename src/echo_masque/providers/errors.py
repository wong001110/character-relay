"""Provider error taxonomy."""

from echo_masque.provider_capabilities import ModelCapability
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


class ProviderModelUnavailableError(ProviderUnavailableError):
    """The requested model is temporarily unavailable while the provider may remain healthy."""

    reason_code = "provider_model_unavailable"


class ProviderModelNotFoundError(ProviderError):
    """The configured model identifier is invalid or no longer offered."""

    reason_code = "provider_model_not_found"
    deployment_fatal = True


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


class ProviderQuotaExhaustedError(ProviderError):
    """The account/free tier has no remaining allowance for this request."""

    reason_code = "provider_quota_exhausted"
    transient = True

    def __init__(
        self,
        message: str,
        *,
        quota_observations: tuple[ProviderQuotaObservation, ...] = (),
        free_tier: bool = False,
    ) -> None:
        super().__init__(message)
        self.quota_observations = quota_observations
        self.free_tier = free_tier


class ProviderBillingRequiredError(ProviderError):
    """The provider requires billing/payment configuration before more requests are allowed."""

    reason_code = "provider_billing_required"
    deployment_fatal = True


class ProviderInsufficientBalanceError(ProviderBillingRequiredError):
    """The account has insufficient paid/free credit balance."""

    reason_code = "provider_insufficient_balance"


class ProviderAuthenticationError(ProviderError):
    """The provider rejected the supplied credential."""

    reason_code = "provider_authentication_rejected"
    deployment_fatal = True


class ProviderCapabilityUnsupportedError(ProviderError):
    """The selected model/endpoint cannot perform the requested protocol/modality capability."""

    reason_code = "provider_capability_unsupported"

    def __init__(
        self,
        message: str,
        *,
        capability: ModelCapability,
    ) -> None:
        super().__init__(message)
        self.capability = capability


class ProviderProtocolError(ProviderError):
    """The provider returned a malformed or unsupported response."""

    reason_code = "provider_protocol_error"
    transient = True


__all__ = [
    "ProviderAuthenticationError",
    "ProviderBillingRequiredError",
    "ProviderCapabilityUnsupportedError",
    "ProviderError",
    "ProviderInsufficientBalanceError",
    "ProviderModelNotFoundError",
    "ProviderModelUnavailableError",
    "ProviderProtocolError",
    "ProviderQuotaExhaustedError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
