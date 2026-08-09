from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.schemas import (
    FrozenProviderContract,
    SemanticVersion,
)

_RESERVED_PARAMETER_KEYS = frozenset(
    {
        "url",
        "uri",
        "host",
        "port",
        "path",
        "file",
        "filename",
        "sql",
        "headers",
        "cookie",
        "authorization",
        "credential",
        "provider",
    }
)


class ProviderEndpointPolicy(FrozenProviderContract):
    endpoint_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    policy_version: SemanticVersion
    method: Literal["GET", "POST"]
    scheme: Literal["https"]
    host: str = Field(min_length=4, max_length=253)
    port: Literal[443]
    path_template: str = Field(min_length=1, max_length=512)
    parameter_names: tuple[str, ...] = Field(max_length=32)
    query_keys: tuple[str, ...] = Field(max_length=32)
    accepted_content_types: tuple[str, ...] = Field(min_length=1, max_length=16)
    max_redirects: int = Field(ge=0, le=5)

    @field_validator(
        "parameter_names",
        "query_keys",
        "accepted_content_types",
    )
    @classmethod
    def validate_allowlists(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("endpoint allowlists must be unique and sorted")
        return value

    @model_validator(mode="after")
    def validate_transport_constants(self) -> ProviderEndpointPolicy:
        if (
            self.host != self.host.casefold()
            or "@" in self.host
            or "*" in self.host
            or self.host.startswith(".")
            or self.host.endswith(".")
        ):
            raise ValueError("endpoint host must be an exact lowercase DNS name")
        if (
            not self.path_template.startswith("/")
            or "?" in self.path_template
            or "#" in self.path_template
            or "\\" in self.path_template
            or ".." in self.path_template.split("/")
        ):
            raise ValueError("endpoint path template is unsafe")
        return self


class ProviderHttpRequestTemplate(FrozenProviderContract):
    endpoint_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    parameters: dict[str, str] = Field(max_length=32)
    query: dict[str, str] = Field(max_length=32)

    @field_validator("parameters", "query")
    @classmethod
    def validate_normalized_values(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if key.casefold() in _RESERVED_PARAMETER_KEYS:
                raise ValueError("reserved transport parameter")
            if (
                not 1 <= len(key) <= 64
                or not 1 <= len(item) <= 512
                or key != key.strip()
                or item != item.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in item)
            ):
                raise ValueError("request parameters must be normalized and bounded")
        return value


class ProviderExecutionContext(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    policy_id: UUID
    license_policy_id: UUID
    authorization_id: UUID | None
    sync_run_id: UUID
    max_requests: int = Field(ge=1, le=10_000)
    max_response_bytes: int = Field(ge=1, le=52_428_800)
    max_total_bytes: int = Field(ge=1, le=10_737_418_240)

    @model_validator(mode="after")
    def validate_byte_budget(self) -> ProviderExecutionContext:
        if self.max_total_bytes < self.max_response_bytes:
            raise ValueError("total byte budget must cover one response")
        return self


class ProviderHttpResponse(FrozenProviderContract):
    status_code: int = Field(ge=100, le=599)
    content_type: str = Field(min_length=1, max_length=128)
    body: bytes = Field(max_length=52_428_800)
    safe_headers: dict[str, str] = Field(max_length=32)
