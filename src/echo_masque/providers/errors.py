"""Provider error taxonomy."""


class ProviderError(RuntimeError):
    """Base error for a model provider call."""


class ProviderTimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""


class ProviderAuthenticationError(ProviderError):
    """The provider rejected the supplied credential."""


class ProviderProtocolError(ProviderError):
    """The provider returned a malformed or unsupported response."""
