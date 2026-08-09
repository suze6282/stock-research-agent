from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

NOW = datetime(2026, 7, 28, 8, tzinfo=UTC)
IDS = tuple(UUID(int=value) for value in range(1, 9))


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.reflection")


def _finding(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": IDS[0],
        "reflection_run_id": IDS[1],
        "research_report_id": IDS[2],
        "report_section_id": IDS[3],
        "report_block_id": IDS[4],
        "claim_id": IDS[5],
        "evidence_id": IDS[6],
        "citation_id": IDS[7],
        "finding_code": "MISSING_PRIMARY_EVIDENCE",
        "category": module.ReflectionFindingCategory.BINDING,
        "severity": module.ReflectionSeverity.HIGH,
        "description": "Primary Claim binding has no valid Evidence binding.",
        "remediation_code": "DELETE_UNBOUND_FACT_BLOCK",
        "blocking": True,
        "created_at": NOW,
    }
    values.update(updates)
    return module.ReportReflectionFindingRecord.model_validate(values)


@pytest.mark.parametrize(
    "category_name",
    tuple(
        (
            "BINDING",
            "CONTEXT",
            "TEMPORAL",
            "EVIDENCE",
            "DISCLOSURE",
            "REFERENCE",
            "CHECKSUM",
            "CONTENT_SAFETY",
            "DATA_QUALITY",
            "FORMAT",
            "VERSIONING",
            "CAPABILITY",
        )
    ),
)
def test_all_closed_finding_categories_validate(category_name: str) -> None:
    module = _module()

    finding = _finding(category=module.ReflectionFindingCategory(category_name))

    assert finding.category.value == category_name


def test_finding_preserves_exact_linked_ids_and_is_append_only() -> None:
    finding = _finding()

    assert (
        finding.reflection_run_id,
        finding.research_report_id,
        finding.report_section_id,
        finding.report_block_id,
        finding.claim_id,
        finding.evidence_id,
        finding.citation_id,
    ) == IDS[1:]
    with pytest.raises(ValidationError, match="Instance is frozen"):
        finding.description = "Changed."


@pytest.mark.parametrize(
    "unsafe",
    (
        "password=secret",
        "SELECT * FROM private_table",
        "C:\\Users\\name\\secret.txt",
        "file://private/path",
        "Traceback (most recent call last):",
        "<script>alert(1)</script>",
        "token=abc",
    ),
)
def test_finding_rejects_unsafe_or_leaking_descriptions(unsafe: str) -> None:
    with pytest.raises(ValidationError):
        _finding(description=unsafe)


def test_finding_requires_safe_bounded_description_and_remediation_code() -> None:
    with pytest.raises(ValidationError):
        _finding(description="x" * 513)
    with pytest.raises(ValidationError):
        _finding(remediation_code="../../run-script")


@pytest.mark.parametrize(
    ("severity", "blocking"),
    (
        ("CRITICAL", True),
        ("HIGH", True),
        ("MEDIUM", False),
        ("LOW", False),
    ),
)
def test_blocking_flag_matches_policy_threshold(
    severity: str,
    blocking: bool,
) -> None:
    module = _module()

    assert (
        _finding(
            severity=module.ReflectionSeverity(severity),
            blocking=blocking,
        ).blocking
        is blocking
    )
    with pytest.raises(ValidationError):
        _finding(
            severity=module.ReflectionSeverity(severity),
            blocking=not blocking,
        )


def test_severity_count_helper_is_deterministic_and_exact() -> None:
    module = _module()
    findings = tuple(
        _finding(
            id=UUID(int=100 + index),
            severity=severity,
            blocking=severity
            in {module.ReflectionSeverity.CRITICAL, module.ReflectionSeverity.HIGH},
        )
        for index, severity in enumerate(
            (
                module.ReflectionSeverity.LOW,
                module.ReflectionSeverity.HIGH,
                module.ReflectionSeverity.MEDIUM,
                module.ReflectionSeverity.CRITICAL,
                module.ReflectionSeverity.HIGH,
            )
        )
    )

    counts = module.count_findings_by_severity(tuple(reversed(findings)))

    assert counts.total == 5
    assert counts.critical == 1
    assert counts.high == 2
    assert counts.medium == 1
    assert counts.low == 1
