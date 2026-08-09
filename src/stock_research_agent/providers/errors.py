"""Typed provider-registry failures."""


class ProviderRegistryError(Exception):
    """Base class for safe provider-registry failures."""


class DuplicateProviderError(ProviderRegistryError):
    """A provider code is already registered."""


class ProviderContractError(ProviderRegistryError):
    """An adapter's direct metadata disagrees with its descriptor."""


class ProviderNotFoundError(ProviderRegistryError):
    """The requested provider code is not registered."""


class ProviderDisabledError(ProviderRegistryError):
    """The requested provider is disabled."""


class ProviderNotAllowedError(ProviderRegistryError):
    """The requested provider is explicitly disallowed."""


class MissingProviderCapabilityError(ProviderRegistryError):
    """The requested provider does not declare a required capability."""


class ProviderCredentialsNotConfiguredError(ProviderRegistryError):
    """The requested provider requires credentials that are not configured."""


class ProviderHttpError(Exception):
    """Base class for safe provider HTTP failures."""


class NetworkDisabledError(ProviderHttpError):
    """Provider network access is disabled by policy."""


class HttpPolicyError(ProviderHttpError):
    """A client policy or request URL is unsafe."""


class RetryExhaustedError(ProviderHttpError):
    """A retryable request failed through its allowed attempts."""


class HttpTimeoutError(ProviderHttpError):
    """A provider request exceeded a timeout boundary."""


class RedirectError(ProviderHttpError):
    """A redirect response could not be followed safely."""


class ResponseTooLargeError(ProviderHttpError):
    """A provider response exceeded the configured byte cap."""


class InvalidNotModifiedError(ProviderHttpError):
    """A 304 response arrived without cached content."""
