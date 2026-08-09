from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)

NOW = datetime(2026, 7, 26, 16, tzinfo=UTC)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.blocks")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 atomic report block contracts are missing")


def _draft(**updates: object) -> object:
    module = _module()
    basis: dict[str, object] = {
        "block_key": "financial.metric.row",
        "block_index": 0,
        "block_type": ReportBlockType.METRIC_TABLE,
        "status": ReportBlockStatus.COMPLETE,
        "text": None,
        "payload": {"rows": [{"row_key": "roe.fy2025", "value": "0.125", "unit": "RATIO"}]},
        "factual_location_key": "roe.fy2025",
    }
    basis.update(updates)
    checksum_basis = {key: value for key, value in basis.items() if key != "checksum"}
    basis.setdefault("checksum", report_checksum(checksum_basis))
    return module.ReportBlockDraft.model_validate(basis)


def test_block_type_vocabulary_is_exactly_ten_closed_values() -> None:
    assert len(ReportBlockType) == 10
    assert {item.value for item in ReportBlockType} == {
        "HEADING",
        "PARAGRAPH",
        "BULLET_LIST",
        "METRIC_TABLE",
        "EVIDENCE_TABLE",
        "WARNING",
        "LIMITATION",
        "CONFLICT",
        "CLAIM_INDEX",
        "CITATION_LIST",
    }


def test_factual_block_requires_stable_location_and_exact_checksum() -> None:
    module = _module()
    block = _draft()

    assert module.validate_report_block(block) is None
    with pytest.raises(module.ReportBlockError) as raised:
        module.validate_report_block(block.model_copy(update={"factual_location_key": None}))
    assert raised.value.code == "FACTUAL_LOCATION_REQUIRED"

    with pytest.raises(module.ReportBlockError) as raised:
        module.validate_report_block(block.model_copy(update={"checksum": "f" * 64}))
    assert raised.value.code == "REPORT_BLOCK_CHECKSUM_MISMATCH"


def test_heading_is_structural_exception_but_cannot_carry_factual_payload() -> None:
    module = _module()
    heading = _draft(
        block_key="financial.heading",
        block_type=ReportBlockType.HEADING,
        text="财务健康",
        payload={},
        factual_location_key=None,
    )

    module.validate_report_block(heading)
    with pytest.raises(module.ReportBlockError) as raised:
        module.validate_report_block(heading.model_copy(update={"payload": {"value": "123"}}))
    assert raised.value.code == "STRUCTURAL_BLOCK_HAS_FACTUAL_PAYLOAD"


def test_block_payload_rejects_float_oversize_and_executable_fields() -> None:
    module = _module()
    for payload in (
        {"value": 1.25},
        {"text": "x" * 70_000},
        {"sql": "select * from research_claims"},
        {"template_path": "../unsafe"},
        {"model_provider": "openai"},
    ):
        values = _draft().model_dump(mode="python")
        values["payload"] = payload
        values["checksum"] = (
            report_checksum({key: value for key, value in values.items() if key != "checksum"})
            if not isinstance(payload.get("value"), float)
            else "a" * 64
        )
        with pytest.raises((ValidationError, module.ReportBlockError, TypeError)):
            candidate = module.ReportBlockDraft.model_validate(values)
            module.validate_report_block(candidate)


def test_completed_block_write_is_frozen_and_context_bound() -> None:
    module = _module()
    draft = _draft()
    write = module.ReportBlockWrite(
        **draft.model_dump(mode="python"),
        id=UUID("10000000-0000-0000-0000-000000000001"),
        report_id=UUID("10000000-0000-0000-0000-000000000002"),
        report_section_id=UUID("10000000-0000-0000-0000-000000000003"),
        created_at=NOW,
    )

    with pytest.raises(ValidationError, match="Instance is frozen"):
        write.payload = {}
