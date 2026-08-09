from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.blocks import ReportBlockDraft
from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    ResearchMode,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import ResearchClaimRecord

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)
RUN_ID = UUID("10000000-0000-0000-0000-000000000001")
CLAIM_ID = UUID("20000000-0000-0000-0000-000000000001")
BLOCK_ID = UUID("30000000-0000-0000-0000-000000000001")


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.bindings")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report Claim binding contracts are missing")


def _block(
    *,
    block_type: ReportBlockType = ReportBlockType.METRIC_TABLE,
    status: ReportBlockStatus = ReportBlockStatus.COMPLETE,
    location: str = "roe.fy2025",
) -> ReportBlockDraft:
    values = {
        "block_key": "financial.metric.row",
        "block_index": 0,
        "block_type": block_type,
        "status": status,
        "text": None,
        "payload": {"rows": [{"row_key": location, "value": "0.125"}]},
        "factual_location_key": location,
    }
    return ReportBlockDraft.model_validate({**values, "checksum": report_checksum(values)})


def _claim(
    support_status: ClaimSupportStatus = ClaimSupportStatus.SUPPORTED,
    **updates: object,
) -> ResearchClaimRecord:
    values: dict[str, object] = {
        "id": CLAIM_ID,
        "run_id": RUN_ID,
        "claim_type": ClaimType.FINANCIAL_METRIC,
        "lifecycle_status": ClaimLifecycleStatus.VALIDATED,
        "support_status": support_status,
        "statement_code": "RETURN_ON_EQUITY",
        "value": Decimal("0.125"),
        "unit": "RATIO",
        "period": "FY2025",
        "as_of_time": NOW,
        "metric_basis": "CANONICAL_V1",
        "builder_version": "deterministic-claim-builder-v1",
        "validator_version": "claim-support-validator-v1",
        "created_at": NOW,
        "completed_at": NOW,
    }
    values.update(updates)
    return ResearchClaimRecord.model_validate(values)


def _manifest(**updates: object) -> ReportInputManifest:
    values: dict[str, object] = {
        "research_agent_run_id": RUN_ID,
        "claim_ids": (CLAIM_ID,),
        "research_mode": ResearchMode.REAL_RESEARCH,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
    }
    values.update(updates)
    return ReportInputManifest.model_construct(**values)


def _binding(
    *,
    role: str = "PRIMARY",
    item_or_row_key: str | None = "roe.fy2025",
    sentence_index: int | None = None,
    **updates: object,
) -> object:
    module = _module()
    values: dict[str, object] = {
        "id": UUID("40000000-0000-0000-0000-000000000001"),
        "report_block_id": BLOCK_ID,
        "claim_id": CLAIM_ID,
        "role": module.ReportClaimBindingRole(role),
        "sentence_index": sentence_index,
        "item_or_row_key": item_or_row_key,
        "created_at": NOW,
    }
    values.update(updates)
    return module.ReportClaimBindingWrite.model_validate(values)


def test_supported_primary_claim_binds_to_exact_factual_location() -> None:
    module = _module()
    binding = _binding()

    assert (
        module.validate_claim_binding(
            _block(),
            _claim(),
            binding,
            _manifest(),
        )
        is None
    )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        binding.claim_id = UUID("ffffffff-0000-0000-0000-000000000001")


def test_binding_requires_exactly_one_matching_location() -> None:
    module = _module()
    for binding in (
        _binding(item_or_row_key=None),
        _binding(sentence_index=0),
        _binding(item_or_row_key="roe.fy2024"),
    ):
        with pytest.raises(module.ReportBindingError) as raised:
            module.validate_claim_binding(_block(), _claim(), binding, _manifest())
        assert raised.value.code in {
            "CLAIM_BINDING_LOCATION_REQUIRED",
            "CLAIM_BINDING_LOCATION_AMBIGUOUS",
            "CLAIM_BINDING_LOCATION_MISMATCH",
        }


def test_binding_rejects_unreachable_or_cross_run_claim() -> None:
    module = _module()
    cases = (
        (_claim(run_id=UUID("ffffffff-0000-0000-0000-000000000001")), _manifest()),
        (_claim(), _manifest(claim_ids=())),
        (_claim(lifecycle_status=ClaimLifecycleStatus.CANDIDATE, support_status=None), _manifest()),
    )
    for claim, manifest in cases:
        with pytest.raises(module.ReportBindingError):
            module.validate_claim_binding(_block(), claim, _binding(), manifest)


@pytest.mark.parametrize(
    ("support", "block_type", "block_status", "role", "expected_code"),
    [
        (
            ClaimSupportStatus.PARTIALLY_SUPPORTED,
            ReportBlockType.METRIC_TABLE,
            ReportBlockStatus.COMPLETE,
            "PRIMARY",
            "PARTIAL_CLAIM_REQUIRES_PARTIAL_BLOCK",
        ),
        (
            ClaimSupportStatus.CONFLICTING,
            ReportBlockType.METRIC_TABLE,
            ReportBlockStatus.PARTIAL,
            "CONTRADICTING",
            "CONFLICTING_CLAIM_REQUIRES_CONFLICT_BLOCK",
        ),
        (
            ClaimSupportStatus.UNSUPPORTED,
            ReportBlockType.METRIC_TABLE,
            ReportBlockStatus.NO_EVIDENCE,
            "LIMITATION",
            "UNSUPPORTED_CLAIM_REQUIRES_DISCLOSURE_BLOCK",
        ),
        (
            ClaimSupportStatus.BLOCKED,
            ReportBlockType.WARNING,
            ReportBlockStatus.BLOCKED,
            "PRIMARY",
            "BLOCKED_CLAIM_REQUIRES_LIMITATION_ROLE",
        ),
    ],
)
def test_support_state_and_block_role_matrix_is_closed(
    support: ClaimSupportStatus,
    block_type: ReportBlockType,
    block_status: ReportBlockStatus,
    role: str,
    expected_code: str,
) -> None:
    module = _module()
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_claim_binding(
            _block(block_type=block_type, status=block_status),
            _claim(support),
            _binding(role=role),
            _manifest(),
        )
    assert raised.value.code == expected_code


def test_qualified_non_normal_claim_blocks_are_allowed() -> None:
    module = _module()
    accepted = (
        (
            _block(status=ReportBlockStatus.PARTIAL),
            _claim(ClaimSupportStatus.PARTIALLY_SUPPORTED),
            _binding(),
        ),
        (
            _block(
                block_type=ReportBlockType.CONFLICT,
                status=ReportBlockStatus.PARTIAL,
            ),
            _claim(ClaimSupportStatus.CONFLICTING),
            _binding(role="CONTRADICTING"),
        ),
        (
            _block(
                block_type=ReportBlockType.LIMITATION,
                status=ReportBlockStatus.NO_EVIDENCE,
            ),
            _claim(ClaimSupportStatus.UNSUPPORTED),
            _binding(role="LIMITATION"),
        ),
        (
            _block(
                block_type=ReportBlockType.LIMITATION,
                status=ReportBlockStatus.BLOCKED,
            ),
            _claim(ClaimSupportStatus.BLOCKED),
            _binding(role="LIMITATION"),
        ),
    )
    for block, claim, binding in accepted:
        module.validate_claim_binding(block, claim, binding, _manifest())


def test_real_research_rejects_synthetic_or_unknown_manifest_claim_context() -> None:
    module = _module()
    for status in (
        SyntheticStatus.SYNTHETIC_TEST_ONLY,
        SyntheticStatus.UNKNOWN,
    ):
        with pytest.raises(module.ReportBindingError) as raised:
            module.validate_claim_binding(
                _block(),
                _claim(),
                _binding(),
                _manifest(synthetic_status=status),
            )
        assert raised.value.code == "REAL_REPORT_SYNTHETIC_CLAIM_FORBIDDEN"


def test_binding_set_rejects_duplicate_claim_location() -> None:
    module = _module()
    duplicate = _binding(id=UUID("40000000-0000-0000-0000-000000000002"))
    with pytest.raises(module.ReportBindingError) as raised:
        module.validate_claim_binding_set((_binding(), duplicate))
    assert raised.value.code == "DUPLICATE_CLAIM_BINDING"
