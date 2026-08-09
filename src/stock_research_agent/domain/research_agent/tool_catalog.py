"""Immutable fingerprints for the approved Tool Registry."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.tools.registry import ToolRegistry


class ToolCatalogEntry(BaseModel):
    """One exact Tool contract included in a catalog fingerprint."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tool_name: str = Field(min_length=1, max_length=128)
    tool_version: str = Field(min_length=1, max_length=64)
    permission: Literal["READ_ONLY"]
    read_only: Literal[True]
    writes: Literal[False]
    requires_network: Literal[False]
    input_schema_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_domain: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=512)
    snapshot_behavior: str = Field(min_length=1, max_length=64)


class ToolCatalogSnapshot(BaseModel):
    """Stable sorted catalog bound to a Research Run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["tool-catalog-v1"] = "tool-catalog-v1"
    catalog_version: str = Field(min_length=80, max_length=80)
    catalog_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_count: int = Field(ge=1, le=256)
    entries: tuple[ToolCatalogEntry, ...] = Field(min_length=1, max_length=256)


def build_tool_catalog_snapshot(registry: ToolRegistry) -> ToolCatalogSnapshot:
    """Fingerprint the exact sorted metadata exposed by a Registry."""

    entries_list: list[ToolCatalogEntry] = []
    for metadata in registry.list():
        if (
            metadata.permission.value != "READ_ONLY"
            or not metadata.read_only
            or metadata.writes
            or metadata.requires_network
        ):
            raise ValueError("Tool Catalog includes a non-read-only or network Tool")
        entries_list.append(
            ToolCatalogEntry(
                tool_name=metadata.name,
                tool_version=metadata.version,
                permission="READ_ONLY",
                read_only=True,
                writes=False,
                requires_network=False,
                input_schema_version=stable_checksum(metadata.input_schema),
                output_schema_version=stable_checksum(metadata.output_schema),
                data_domain=metadata.domain,
                description=metadata.description,
                snapshot_behavior=metadata.snapshot_behavior.value,
            )
        )
    entries = tuple(entries_list)
    checksum = stable_checksum(tuple(entry.model_dump(mode="python") for entry in entries))
    return ToolCatalogSnapshot(
        catalog_version=f"tool-catalog-v1:{checksum}",
        catalog_checksum=checksum,
        entry_count=len(entries),
        entries=entries,
    )
