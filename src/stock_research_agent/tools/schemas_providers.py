"""Strict schemas for the ten read-only Provider governance tools."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ProviderToolName = Literal[
    "get_provider",
    "list_provider_capabilities",
    "get_provider_health",
    "get_provider_license_status",
    "get_provider_sync_run",
    "get_provider_sync_checkpoint",
    "list_provider_raw_artifacts",
    "list_provider_quality_issues",
    "list_provider_dead_letters",
    "get_provider_readiness",
]


class ProviderToolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ProviderCodeInput(ProviderToolModel):
    provider_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")


class ProviderCodePageInput(ProviderCodeInput):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100_000)


class ProviderRunInput(ProviderToolModel):
    run_id: UUID


class ProviderRunPageInput(ProviderRunInput):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100_000)


class ProviderSecurityInput(ProviderToolModel):
    security_id: UUID


class ProviderReadOutput(ProviderToolModel):
    tool_name: ProviderToolName
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


__all__ = [
    "ProviderCodeInput",
    "ProviderCodePageInput",
    "ProviderReadOutput",
    "ProviderRunInput",
    "ProviderRunPageInput",
    "ProviderSecurityInput",
    "ProviderToolModel",
    "ProviderToolName",
]
