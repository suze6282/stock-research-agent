from __future__ import annotations

from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ReportSectionStatus,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)

FIRST_METRIC_ID = UUID(int=101)
SECOND_METRIC_ID = UUID(int=102)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.references")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 stable reference allocator is missing")


def _target(kind: str, record_id: UUID, label: str) -> dict[str, str]:
    return {
        "kind": kind,
        "record_id": str(record_id),
        "label": label,
    }


def _content(
    *,
    first_metric_id: UUID = FIRST_METRIC_ID,
    second_metric_id: UUID = SECOND_METRIC_ID,
) -> StructuredReportContent:
    return StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.EN_US,
        sections=(
            StructuredReportSection(
                section=ReportSection.FINANCIAL_HEALTH,
                section_index=0,
                title="Financial Health",
                status=ReportSectionStatus.PARTIAL,
                blocks=(
                    StructuredReportBlock(
                        block_key="metric.first",
                        block_index=0,
                        block_type=ReportBlockType.METRIC_TABLE,
                        status=ReportBlockStatus.COMPLETE,
                        text="First [MET-999], citation [CIT-700].",
                        payload={
                            "reference": "[MET-999]",
                            "reference_targets": [
                                _target("METRIC", first_metric_id, "MET-999"),
                                _target("CITATION", UUID(int=201), "CIT-700"),
                            ],
                        },
                    ),
                    StructuredReportBlock(
                        block_key="metric.second",
                        block_index=1,
                        block_type=ReportBlockType.METRIC_TABLE,
                        status=ReportBlockStatus.COMPLETE,
                        text="Second [MET-010], reused [MET-999], evidence [EV-800].",
                        payload={
                            "reference": "[MET-010]",
                            "reference_targets": [
                                _target("METRIC", second_metric_id, "MET-010"),
                                _target("METRIC", first_metric_id, "MET-999"),
                                _target("EVIDENCE", UUID(int=301), "EV-800"),
                            ],
                        },
                    ),
                ),
            ),
            StructuredReportSection(
                section=ReportSection.LIMITATIONS,
                section_index=1,
                title="Limitations",
                status=ReportSectionStatus.BLOCKED,
                blocks=(
                    StructuredReportBlock(
                        block_key="limitation.one",
                        block_index=0,
                        block_type=ReportBlockType.LIMITATION,
                        status=ReportBlockStatus.BLOCKED,
                        text="Blocked [LIM-500]. Conflict [CON-600].",
                        payload={
                            "reference": "[LIM-500]",
                            "reference_targets": [
                                _target("LIMITATION", UUID(int=401), "LIM-500"),
                                _target("CONFLICT", UUID(int=501), "CON-600"),
                            ],
                        },
                    ),
                ),
            ),
        ),
    )


def test_allocator_uses_first_appearance_and_reuses_each_target() -> None:
    module = _module()
    allocation = module.ReportReferenceAllocator().allocate(_content())

    assert tuple(item.label for item in allocation.references) == (
        "MET-001",
        "CIT-001",
        "MET-002",
        "EV-001",
        "LIM-001",
        "CON-001",
    )
    markdown_source = " ".join(
        block.text or "" for section in allocation.content.sections for block in section.blocks
    )
    assert markdown_source.count("[MET-001]") == 2
    assert "[MET-002]" in markdown_source
    assert "[CIT-001]" in markdown_source
    assert "[EV-001]" in markdown_source
    assert "[LIM-001]" in markdown_source
    assert "[CON-001]" in markdown_source


def test_visible_numbering_is_independent_of_uuid_values() -> None:
    module = _module()
    low_high = module.ReportReferenceAllocator().allocate(
        _content(first_metric_id=UUID(int=1), second_metric_id=UUID(int=2))
    )
    high_low = module.ReportReferenceAllocator().allocate(
        _content(
            first_metric_id=UUID(int=2**128 - 1),
            second_metric_id=UUID(int=1),
        )
    )

    assert tuple(item.label for item in low_high.references) == tuple(
        item.label for item in high_low.references
    )


def test_revision_recalculates_numbering_after_removed_first_reference() -> None:
    module = _module()
    original = _content()
    first_section = original.sections[0]
    revised = original.model_copy(
        update={
            "sections": (
                first_section.model_copy(
                    update={
                        "blocks": (first_section.blocks[1].model_copy(update={"block_index": 0}),)
                    }
                ),
                original.sections[1],
            )
        }
    )
    allocation = module.ReportReferenceAllocator().allocate(revised)

    labels = {item.record_id: item.label for item in allocation.references}
    assert labels[UUID(int=102)] == "MET-001"
    assert labels[UUID(int=101)] == "MET-002"


@pytest.mark.parametrize(
    ("content_update", "expected_code"),
    [
        ("LABEL_POINTS_TO_MULTIPLE_RECORDS", "REFERENCE_LABEL_NOT_BIJECTIVE"),
        ("RECORD_HAS_MULTIPLE_LABELS", "REFERENCE_RECORD_NOT_BIJECTIVE"),
        ("ORPHAN_TARGET", "REFERENCE_TARGET_UNUSED"),
        ("UNBOUND_BODY_REFERENCE", "BODY_REFERENCE_UNBOUND"),
    ],
)
def test_allocator_rejects_duplicate_or_orphan_reference_graphs(
    content_update: str,
    expected_code: str,
) -> None:
    module = _module()
    content = _content()
    section = content.sections[0]
    block = section.blocks[0]
    targets = list(block.payload["reference_targets"])
    text = block.text
    if content_update == "LABEL_POINTS_TO_MULTIPLE_RECORDS":
        targets.append(_target("METRIC", UUID(int=999), "MET-999"))
    elif content_update == "RECORD_HAS_MULTIPLE_LABELS":
        targets.append(_target("METRIC", UUID(int=101), "MET-998"))
        text = f"{text} [MET-998]"
    elif content_update == "ORPHAN_TARGET":
        targets.append(_target("METRIC", UUID(int=999), "MET-998"))
    else:
        text = f"{text} [EV-777]"
    broken_block = block.model_copy(
        update={
            "text": text,
            "payload": {
                **block.payload,
                "reference_targets": targets,
            },
        }
    )
    broken = content.model_copy(
        update={
            "sections": (
                section.model_copy(
                    update={
                        "blocks": (broken_block, section.blocks[1]),
                    }
                ),
                content.sections[1],
            )
        }
    )

    with pytest.raises(module.ReportReferenceError) as raised:
        module.ReportReferenceAllocator().allocate(broken)
    assert raised.value.code == expected_code
