"""Explicit, gate-bound credential resolution with no ambient environment access."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import NoReturn
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.schemas import FrozenProviderContract


class CredentialBindingKind(StrEnum):
    HEADER = "HEADER"
    BODY = "BODY"


class ProviderCredentialExecutionRequest(FrozenProviderContract):
    provider_definition_id: UUID
    credential_reference_id: UUID
    declared_name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    binding_kind: CredentialBindingKind
    binding_name: str = Field(min_length=1, max_length=64)
    license_allowed: bool
    configuration_allowed: bool
    live_authorized: bool


class ResolvedCredentialContext:
    """Ephemeral credential binding; deliberately not serializable or printable."""

    __slots__ = ("__binding_kind", "__binding_name", "__value")

    def __init__(
        self,
        binding_kind: CredentialBindingKind,
        binding_name: str,
        value: str,
    ) -> None:
        self.__binding_kind = binding_kind
        self.__binding_name = binding_name
        self.__value = value

    def __repr__(self) -> str:
        return "<ResolvedCredentialContext redacted>"

    __str__ = __repr__

    def __reduce__(self) -> NoReturn:
        raise TypeError("ResolvedCredentialContext cannot be serialized")

    def bind_header(self) -> dict[str, str]:
        if self.__binding_kind is not CredentialBindingKind.HEADER:
            raise ValueError("CREDENTIAL_BINDING_KIND_MISMATCH")
        return {self.__binding_name: self.__value}

    def bind_body(self) -> dict[str, str]:
        if self.__binding_kind is not CredentialBindingKind.BODY:
            raise ValueError("CREDENTIAL_BINDING_KIND_MISMATCH")
        return {self.__binding_name: self.__value}


class EnvironmentCredentialResolver:
    """Resolve from one explicitly supplied mapping after all prerequisite gates."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    def resolve_for_execution(
        self,
        reference: CredentialReferenceRecord,
        request: ProviderCredentialExecutionRequest,
    ) -> ResolvedCredentialContext:
        checks = (
            (
                not request.license_allowed,
                "CREDENTIAL_LICENSE_GATE_REQUIRED",
            ),
            (
                not request.configuration_allowed,
                "CREDENTIAL_CONFIGURATION_GATE_REQUIRED",
            ),
            (
                not request.live_authorized,
                "CREDENTIAL_LIVE_AUTHORIZATION_REQUIRED",
            ),
            (
                request.provider_definition_id != reference.provider_definition_id,
                "CREDENTIAL_PROVIDER_MISMATCH",
            ),
            (
                request.credential_reference_id != reference.id,
                "CREDENTIAL_REFERENCE_MISMATCH",
            ),
            (
                reference.resolver_kind is not CredentialResolverKind.ENVIRONMENT,
                "CREDENTIAL_RESOLVER_KIND_UNSUPPORTED",
            ),
            (
                request.declared_name != reference.declared_name,
                "CREDENTIAL_NAME_NOT_DECLARED",
            ),
            (
                not _binding_allowed(request.binding_kind, request.binding_name),
                "CREDENTIAL_BINDING_NOT_ALLOWED",
            ),
        )
        for failed, reason in checks:
            if failed:
                raise ValueError(reason)

        value = self._environment.get(request.declared_name)
        if value is None or not value:
            raise ValueError("CREDENTIAL_NOT_CONFIGURED")
        return ResolvedCredentialContext(
            request.binding_kind,
            request.binding_name,
            value,
        )


def _binding_allowed(kind: CredentialBindingKind, name: str) -> bool:
    if kind is CredentialBindingKind.HEADER:
        return name.startswith("X-") and name.lower() not in {
            "x-authorization",
            "x-cookie",
        }
    return name in {"token", "api_key"}
