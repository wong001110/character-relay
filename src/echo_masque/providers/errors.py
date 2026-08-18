"""Provider error taxonomy."""

from echo_masque.provider_capabilities import ModelCapability
from echo_masque.providers.base import ProviderQuotaObservation


class ProviderError(RuntimeError):
    """Base error for one model-provider call."""

    reason_code = "provider_error"
    transient = False
    deployment_fatal = False


class ProviderTimeoutError(ProviderError):
    reason_code = "provider_timeout"
    transient = True


class ProviderUnavailableError(ProviderError):
    reason_code = "provider_unavailable"
    transient = True


class ProviderModelUnavailableError(ProviderUnavailableError):
    reason_code = "provider_model_unavailable"


class ProviderModelNotFoundError(ProviderError):
    reason_code = "provider_model_not_found"
    deployment_fatal = True


class ProviderRateLimitError(ProviderError):
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
    reason_code = "provider_billing_required"
    deployment_fatal = True


class ProviderInsufficientBalanceError(ProviderError):
    """The account has insufficient balance; keep semantics separate from billing setup."""

    reason_code = "provider_insufficient_balance"
    deployment_fatal = True


class ProviderAuthenticationError(ProviderError):
    reason_code = "provider_authentication_rejected"
    deployment_fatal = True


class ProviderCapabilityUnsupportedError(ProviderError):
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
