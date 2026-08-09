"""In-memory registry for injected provider adapters."""

from __future__ import annotations

from stock_research_agent.domain.data_access.enums import ProviderCapability, ProviderStatus
from stock_research_agent.domain.data_access.schemas import ProviderDescriptor
from stock_research_agent.providers.base import DataProviderAdapter
from stock_research_agent.providers.errors import (
    DuplicateProviderError,
    MissingProviderCapabilityError,
    ProviderContractError,
    ProviderCredentialsNotConfiguredError,
    ProviderDisabledError,
    ProviderNotAllowedError,
    ProviderNotFoundError,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, DataProviderAdapter] = {}

    def register(self, adapter: DataProviderAdapter) -> None:
        try:
            code = adapter.code
        except AttributeError as error:
            raise ProviderContractError("adapter must expose code") from error

        if code in self._adapters:
            raise DuplicateProviderError(f"provider {code!r} is already registered")

        try:
            descriptor = adapter.descriptor
            version = adapter.version
            capabilities = adapter.capabilities
        except AttributeError as error:
            raise ProviderContractError("adapter metadata is incomplete") from error

        if not isinstance(descriptor, ProviderDescriptor):
            raise ProviderContractError("descriptor must be a ProviderDescriptor")
        if code != descriptor.code:
            raise ProviderContractError("adapter code must equal descriptor code")
        if version != descriptor.version:
            raise ProviderContractError("adapter version must equal descriptor version")
        if capabilities != descriptor.capabilities:
            raise ProviderContractError("adapter capabilities must equal descriptor capabilities")

        self._adapters[code] = adapter

    def get(
        self,
        code: str,
        required_capability: ProviderCapability | None = None,
    ) -> DataProviderAdapter:
        adapter = self._find(code)
        descriptor = adapter.descriptor
        if not descriptor.is_enabled:
            raise ProviderDisabledError(f"provider {code!r} is disabled")
        if descriptor.status is ProviderStatus.NOT_ALLOWED:
            raise ProviderNotAllowedError(f"provider {code!r} is not allowed")
        if required_capability is not None and required_capability not in descriptor.capabilities:
            raise MissingProviderCapabilityError(
                f"provider {code!r} does not support {required_capability.value}"
            )
        if descriptor.requires_credentials and not descriptor.credentials_configured:
            raise ProviderCredentialsNotConfiguredError(
                f"provider {code!r} requires configured credentials"
            )
        return adapter

    def list(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(self._adapters[code].descriptor for code in sorted(self._adapters))

    def describe(self, code: str) -> ProviderDescriptor:
        return self._find(code).descriptor

    def _find(self, code: str) -> DataProviderAdapter:
        try:
            return self._adapters[code]
        except KeyError as error:
            raise ProviderNotFoundError(f"provider {code!r} is not registered") from error
