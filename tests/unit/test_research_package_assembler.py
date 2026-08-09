from __future__ import annotations

import importlib
import importlib.util
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceStatus,
    EvidenceType,
    ResearchPackageStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)

MODULE = "stock_research_agent.domain.research_agent.packages"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
GOLDEN = Path(__file__).parents[1] / "golden" / "research_packages.json"


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _claim(
    index: int,
    claim_type: ClaimType,
    support: ClaimSupportStatus,
    statement_code: str,
) -> ResearchClaimRecord:
    values: dict[str, object] = {
        "id": UUID(int=index),
        "run_id": UUID(int=10),
        "claim_type": claim_type,
        "lifecycle_status": ClaimLifecycleStatus.VALIDATED,
        "support_status": support,
        "statement_code": statement_code,
        "builder_version": "deterministic-claim-builder-v1",
        "validator_version": "claim-support-validator-v1",
        "created_at": NOW,
        "completed_at": NOW,
    }
    if claim_type in {
        ClaimType.FINANCIAL_FACT,
        ClaimType.FINANCIAL_METRIC,
        ClaimType.VALUATION_METRIC,
    }:
        values.update(
            {
                "value": Decimal("0.125"),
                "unit": "RATIO",
                "period": "FY2025",
                "as_of_time": NOW,
                "metric_basis": "formula-v1",
            }
        )
    return ResearchClaimRecord.model_validate(values)


def _evidence(index: int) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord.model_validate(
        {
            "id": UUID(int=index),
            "run_id": UUID(int=10),
            "observation_id": UUID(int=200 + index),
            "evidence_type": EvidenceType.DATA_QUALITY_EVIDENCE,
            "status": EvidenceStatus.VALID,
            "schema_version": "evidence-v1",
            "security_id": UUID(int=12),
            "snapshot_id": UUID(int=13),
            "research_as_of_time": NOW,
            "source_record_type": "source",
            "source_record_id": UUID(int=300 + index),
            "source_checksum": f"{index:064x}",
            "published_at": NOW,
            "synthetic_status": SyntheticStatus.REAL_VERIFIED,
            "payload": {"quality_code": "PARTIAL_REAL_EVIDENCE"},
            "created_at": NOW,
        }
    )


def _assemble(**updates: object) -> object:
    values = {
        "package_id": UUID(int=14),
        "run_id": UUID(int=10),
        "request_id": UUID(int=11),
        "security_id": UUID(int=12),
        "snapshot_id": UUID(int=13),
        "research_as_of_time": NOW,
        "research_type": ResearchType.FULL_RESEARCH_PACKAGE,
        "policy_version": "controlled-offline-v1",
        "planner_version": "deterministic-template-v1",
        "tool_catalog_version": "tool-catalog-v1:" + "a" * 64,
        "requested_sections": (
            ResearchSection.SECURITY_IDENTITY,
            ResearchSection.FINANCIAL_HEALTH,
            ResearchSection.DOCUMENT_EVIDENCE,
            ResearchSection.DATA_QUALITY,
            ResearchSection.LIMITATIONS,
        ),
        "claims": (
            _claim(1, ClaimType.IDENTITY, ClaimSupportStatus.SUPPORTED, "SECURITY_IDENTITY"),
            _claim(
                2,
                ClaimType.FINANCIAL_METRIC,
                ClaimSupportStatus.UNSUPPORTED,
                "RETURN_ON_EQUITY",
            ),
            _claim(
                3,
                ClaimType.DOCUMENT_DISCLOSURE,
                ClaimSupportStatus.BLOCKED,
                "DOCUMENT_BODY_UNAVAILABLE",
            ),
            _claim(
                4,
                ClaimType.DATA_QUALITY,
                ClaimSupportStatus.SUPPORTED,
                "PARTIAL_REAL_EVIDENCE",
            ),
            _claim(
                5,
                ClaimType.LIMITATION,
                ClaimSupportStatus.BLOCKED,
                "DOCUMENT_BODY_UNAVAILABLE",
            ),
        ),
        "evidence": (_evidence(102), _evidence(101)),
        "blocked_capabilities": ("DOCUMENT_BODY_UNAVAILABLE",),
        "warnings": ("PARTIAL_REAL_EVIDENCE",),
        "run_failed": False,
        "created_at": NOW,
    }
    values.update(updates)
    return _module().ResearchPackageAssembler().assemble(**values)


def test_partial_package_matches_independent_golden_checksum_and_sections() -> None:
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))["partial_real_evidence"]

    package = _assemble()

    assert package.status.value == expected["status"]
    assert package.checksum == expected["checksum"]
    assert {item.section.value: item.status.value for item in package.sections} == expected[
        "section_statuses"
    ]
    assert package.evidence_ids == (UUID(int=101), UUID(int=102))
    assert package.unsupported_claim_ids == (UUID(int=2),)
    assert package.blocked_capabilities == ("DOCUMENT_BODY_UNAVAILABLE",)


def test_complete_blocked_and_failed_statuses_are_deterministic() -> None:
    identity = _claim(
        1,
        ClaimType.IDENTITY,
        ClaimSupportStatus.SUPPORTED,
        "SECURITY_IDENTITY",
    )
    limitation = _claim(
        5,
        ClaimType.LIMITATION,
        ClaimSupportStatus.BLOCKED,
        "NO_EVIDENCE",
    )

    complete = _assemble(
        requested_sections=(ResearchSection.SECURITY_IDENTITY,),
        claims=(identity,),
        blocked_capabilities=(),
        warnings=(),
    )
    blocked = _assemble(
        requested_sections=(ResearchSection.LIMITATIONS,),
        claims=(limitation,),
        blocked_capabilities=("NO_EVIDENCE",),
    )
    failed = _assemble(run_failed=True)

    assert complete.status is ResearchPackageStatus.COMPLETE
    assert blocked.status is ResearchPackageStatus.BLOCKED
    assert failed.status is ResearchPackageStatus.FAILED


def test_package_is_structural_and_exposes_all_empty_section_states() -> None:
    package = _assemble()

    assert len(package.sections) == 10
    assert {item.section for item in package.sections} == set(ResearchSection)
    serialized = package.model_dump(mode="json")
    forbidden = {
        "narrative",
        "rating",
        "recommendation",
        "target_price",
        "position_size",
        "forecast",
        "confidence",
    }
    assert forbidden.isdisjoint(serialized)
    assert all(
        item.status.value in {"PASS", "NOT_REQUESTED", "NO_EVIDENCE", "BLOCKED", "PARTIAL"}
        for item in package.sections
    )


def test_conflicting_and_unsupported_claims_remain_visible() -> None:
    conflicting = _claim(
        6,
        ClaimType.FINANCIAL_METRIC,
        ClaimSupportStatus.CONFLICTING,
        "RETURN_ON_EQUITY",
    )

    package = _assemble(claims=(conflicting,))

    assert package.conflicting_claim_ids == (UUID(int=6),)
    assert package.status is ResearchPackageStatus.PARTIAL
