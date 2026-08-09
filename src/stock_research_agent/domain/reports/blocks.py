"""Atomic immutable report blocks with deterministic safety validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import Field, JsonValue

from stock_research_agent.domain.reports.canonical import (
    canonical_report_json,
    report_checksum,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenReportContract,
)

_MAX_PAYLOAD_BYTES = 65_536
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "code",
        "environment",
        "expression",
        "model_provider",
        "path",
        "prompt",
        "script",
        "sql",
        "template_path",
        "url",
    }
)


class ReportBlockError(ValueError):
    """Stable deterministic rejection raised for an unsafe report block."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReportBlockDraft(FrozenReportContract):
    """One canonical block before transaction-owned persistence."""

    block_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    block_index: int = Field(ge=0, le=299)
    block_type: ReportBlockType
    status: ReportBlockStatus
    text: str | None = Field(default=None, max_length=10_000)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    factual_location_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}$",
    )
    checksum: Checksum


class ReportBlockWrite(ReportBlockDraft):
    """Immutable context-bound report block ready for persistence."""

    id: UUID
    report_id: UUID
    report_section_id: UUID
    created_at: AwareUtcDateTime


def validate_report_block(block: ReportBlockDraft) -> None:
    """Reject structurally invalid, executable, oversized, or altered blocks."""

    if block.block_type is ReportBlockType.HEADING:
        if block.payload:
            raise ReportBlockError("STRUCTURAL_BLOCK_HAS_FACTUAL_PAYLOAD")
        if block.factual_location_key is not None:
            raise ReportBlockError("STRUCTURAL_BLOCK_HAS_FACTUAL_LOCATION")
    elif block.factual_location_key is None:
        raise ReportBlockError("FACTUAL_LOCATION_REQUIRED")

    _reject_forbidden_payload_keys(block.payload)
    payload_json = canonical_report_json(block.payload)
    if len(payload_json.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ReportBlockError("REPORT_BLOCK_PAYLOAD_TOO_LARGE")

    checksum_payload = block.model_dump(
        mode="python",
        exclude={"checksum"},
    )
    if report_checksum(checksum_payload) != block.checksum:
        raise ReportBlockError("REPORT_BLOCK_CHECKSUM_MISMATCH")


def _reject_forbidden_payload_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.casefold() in _FORBIDDEN_PAYLOAD_KEYS:
                raise ReportBlockError("EXECUTABLE_REPORT_PAYLOAD_FORBIDDEN")
            _reject_forbidden_payload_keys(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, str):
        for item in value:
            _reject_forbidden_payload_keys(item)
