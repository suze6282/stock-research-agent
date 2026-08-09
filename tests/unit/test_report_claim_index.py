from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.bindings import (
    ReportClaimBindingRole,
    ReportClaimBindingWrite,
)
from stock_research_agent.domain.reports.blocks import validate_report_block
from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ReportSectionStatus,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
)
from stock_research_agent.domain.research_agent.schemas import ResearchClaimRecord

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
CLAIM_IDS = tuple(UUID(int=value) for value in range(101, 107))


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.appendices")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report appendix builders are missing")


def _claim(
    claim_id: UUID,
    status: ClaimSupportStatus,
    statement_code: str,
) -> ResearchClaimRecord:
    return ResearchClaimRecord(
        id=claim_id,
        run_id=RUN_ID,
        claim_type=ClaimType.LIMITATION,
        lifecycle_status=ClaimLifecycleStatus.VALIDATED,
        support_status=status,
        statement_code=statement_code,
        builder_version="deterministic-claim-builder-v1",
        validator_version="claim-support-validator-v1",
        created_at=NOW,
        completed_at=NOW,
    )


def _binding(claim_id: UUID, index: int) -> ReportClaimBindingWrite:
    return ReportClaimBindingWrite(
        id=UUID(int=1000 + index),
        report_block_id=UUID(int=2000 + index),
        claim_id=claim_id,
        role=ReportClaimBindingRole.LIMITATION,
        sentence_index=0,
        created_at=NOW,
    )


def _content(claim_ids: tuple[UUID, ...]) -> StructuredReportContent:
    blocks = tuple(
        StructuredReportBlock(
            block_key=f"claim.item.{index}",
            block_index=index,
            block_type=ReportBlockType.LIMITATION,
            status=ReportBlockStatus.PARTIAL,
            text=f"Claim {index}.",
            payload={"claim_id": str(claim_id)},
        )
        for index, claim_id in enumerate(claim_ids)
    )
    return StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.EN_US,
        sections=(
            StructuredReportSection(
                section=ReportSection.LIMITATIONS,
                section_index=0,
                title="Limitations",
                status=ReportSectionStatus.PARTIAL,
                blocks=blocks,
            ),
        ),
    )


def _claims() -> tuple[ResearchClaimRecord, ...]:
    return (
        _claim(CLAIM_IDS[0], ClaimSupportStatus.SUPPORTED, "SUPPORTED_ITEM"),
        _claim(
            CLAIM_IDS[1],
            ClaimSupportStatus.PARTIALLY_SUPPORTED,
            "PARTIAL_ITEM",
        ),
        _claim(CLAIM_IDS[2], ClaimSupportStatus.CONFLICTING, "CONFLICT_ITEM"),
        _claim(CLAIM_IDS[3], ClaimSupportStatus.UNSUPPORTED, "UNSUPPORTED_ITEM"),
        _claim(CLAIM_IDS[4], ClaimSupportStatus.BLOCKED, "BLOCKED_ITEM"),
        _claim(CLAIM_IDS[5], ClaimSupportStatus.SUPPORTED, "UNUSED_ITEM"),
    )


def test_claim_index_contains_each_used_bound_claim_once_in_report_order() -> None:
    module = _module()
    used = (CLAIM_IDS[2], CLAIM_IDS[0], CLAIM_IDS[3], CLAIM_IDS[4], CLAIM_IDS[1])
    content = _content((*used, CLAIM_IDS[2]))
    bindings = tuple(_binding(claim_id, index) for index, claim_id in enumerate(used))

    block = module.build_claim_index(content, tuple(reversed(_claims())), bindings)

    assert block.block_key == "appendix.claim_index"
    assert block.block_type is ReportBlockType.CLAIM_INDEX
    assert block.status is ReportBlockStatus.PARTIAL
    assert block.factual_location_key == "claim_index.rows"
    assert block.payload["rows"] == [
        {
            "claim_id": str(CLAIM_IDS[2]),
            "statement_code": "CONFLICT_ITEM",
            "claim_type": "LIMITATION",
            "support_status": "CONFLICTING",
            "classification": "CONFLICTING",
        },
        {
            "claim_id": str(CLAIM_IDS[0]),
            "statement_code": "SUPPORTED_ITEM",
            "claim_type": "LIMITATION",
            "support_status": "SUPPORTED",
            "classification": "SUPPORTED",
        },
        {
            "claim_id": str(CLAIM_IDS[3]),
            "statement_code": "UNSUPPORTED_ITEM",
            "claim_type": "LIMITATION",
            "support_status": "UNSUPPORTED",
            "classification": "UNSUPPORTED",
        },
        {
            "claim_id": str(CLAIM_IDS[4]),
            "statement_code": "BLOCKED_ITEM",
            "claim_type": "LIMITATION",
            "support_status": "BLOCKED",
            "classification": "BLOCKED",
        },
        {
            "claim_id": str(CLAIM_IDS[1]),
            "statement_code": "PARTIAL_ITEM",
            "claim_type": "LIMITATION",
            "support_status": "PARTIALLY_SUPPORTED",
            "classification": "PARTIAL",
        },
    ]
    assert str(CLAIM_IDS[5]) not in str(block.payload)
    validate_report_block(block)


def test_claim_index_rejects_used_claim_without_exact_binding() -> None:
    module = _module()

    with pytest.raises(module.ReportAppendixError) as raised:
        module.build_claim_index(
            _content((CLAIM_IDS[0], CLAIM_IDS[1])),
            _claims(),
            (_binding(CLAIM_IDS[0], 0),),
        )

    assert raised.value.code == "CLAIM_INDEX_BINDING_MISSING"


def test_claim_index_rejects_binding_to_unknown_claim() -> None:
    module = _module()
    unknown_id = UUID(int=999)

    with pytest.raises(module.ReportAppendixError) as raised:
        module.build_claim_index(
            _content((unknown_id,)),
            _claims(),
            (_binding(unknown_id, 0),),
        )

    assert raised.value.code == "CLAIM_INDEX_CLAIM_MISSING"
