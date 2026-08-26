from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

ENUMS_MODULE = "stock_research_agent.domain.research_agent.enums"
SCHEMAS_MODULE = "stock_research_agent.domain.research_agent.schemas"
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
SNAPSHOT_ID = UUID("22222222-2222-4222-8222-222222222222")
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
STEP_ID = UUID("55555555-5555-4555-8555-555555555554")
AS_OF = datetime(2026, 7, 23, 4, 5, 6, tzinfo=UTC)


def _modules() -> tuple[object, object]:
    assert importlib.util.find_spec(ENUMS_MODULE) is not None
    assert importlib.util.find_spec(SCHEMAS_MODULE) is not None
    return importlib.import_module(ENUMS_MODULE), importlib.import_module(SCHEMAS_MODULE)


def test_closed_research_run_and_claim_vocabularies_are_exact() -> None:
    enums, _ = _modules()

    assert tuple(item.value for item in enums.ResearchType) == (
        "COMPANY_OVERVIEW",
        "FINANCIAL_HEALTH",
        "VALUATION_SNAPSHOT",
        "CATALYSTS_AND_RISKS",
        "DATA_QUALITY_REVIEW",
        "FULL_RESEARCH_PACKAGE",
    )
    assert tuple(item.value for item in enums.ResearchRunStatus) == (
        "CREATED",
        "PLANNING",
        "PLANNED",
        "RUNNING",
        "PAUSED",
        "COMPLETED",
        "PARTIAL",
        "BLOCKED",
        "FAILED",
        "CANCELLED",
    )
    assert tuple(item.value for item in enums.ClaimSupportStatus) == (
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "CONFLICTING",
        "UNSUPPORTED",
        "BLOCKED",
    )


def test_research_request_is_strict_frozen_bounded_and_utc() -> None:
    enums, schemas = _modules()
    request = schemas.ResearchRequestCreate(
        security_query="601138.SH",
        research_type=enums.ResearchType.COMPANY_OVERVIEW,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        requested_sections=(enums.ResearchSection.SECURITY_IDENTITY,),
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
    )

    assert request.security_query == "601138.SH"
    with pytest.raises(ValidationError):
        request.security_query = "MU"
    with pytest.raises(ValidationError):
        schemas.ResearchRequestCreate(
            **request.model_dump(),
            unexpected=True,
        )
    for invalid_time in (
        datetime(2026, 7, 23, 4, 5, 6),
        datetime(
            2026,
            7,
            23,
            12,
            5,
            6,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    ):
        with pytest.raises(ValidationError):
            schemas.ResearchRequestCreate(
                **{
                    **request.model_dump(),
                    "research_as_of_time": invalid_time,
                }
            )


def test_policy_enforces_hard_budgets_and_zero_model_tokens() -> None:
    enums, schemas = _modules()
    policy = schemas.ResearchPolicyRecord(
        version="controlled-offline-v1",
        checksum="a" * 64,
        allowed_research_types=tuple(enums.ResearchType),
        allowed_sections=tuple(enums.ResearchSection),
        allowed_tools=(schemas.AllowedTool(tool_name="get_data_snapshot", tool_version="1.0.0"),),
        max_steps=12,
        max_tool_calls=24,
        max_calls_per_tool=5,
        max_retries_per_step=1,
        max_duration_seconds=120,
        model_token_budget=0,
    )

    assert policy.model_token_budget == 0
    for field, value in (
        ("max_steps", 21),
        ("max_tool_calls", 51),
        ("max_calls_per_tool", 6),
        ("max_retries_per_step", 2),
        ("max_duration_seconds", 601),
        ("model_token_budget", 1),
    ):
        with pytest.raises(ValidationError):
            schemas.ResearchPolicyRecord(
                **{
                    **policy.model_dump(),
                    field: value,
                }
            )


def test_controlled_context_and_run_budget_cannot_accept_model_use_or_float() -> None:
    _, schemas = _modules()
    context = schemas.ControlledRunContext(
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        research_agent_run_id=RUN_ID,
        research_request_id=REQUEST_ID,
        policy_version="controlled-offline-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
    )
    budget = schemas.RunBudget(
        max_steps=12,
        max_tool_calls=24,
        max_calls_per_tool=5,
        max_retries_per_step=1,
        max_duration_seconds=120,
        model_token_budget=0,
        consumed_steps=0,
        consumed_tool_calls=0,
        consumed_model_tokens=0,
        elapsed_seconds=Decimal("0"),
    )

    assert context.snapshot_id == SNAPSHOT_ID
    assert budget.elapsed_seconds == Decimal("0")
    with pytest.raises(ValidationError):
        schemas.RunBudget(**{**budget.model_dump(), "elapsed_seconds": 0.5})
    with pytest.raises(ValidationError):
        schemas.RunBudget(**{**budget.model_dump(), "consumed_model_tokens": 1})


def test_observation_rejects_binary_float_and_unbounded_payload() -> None:
    enums, schemas = _modules()
    base = {
        "id": UUID("55555555-5555-4555-8555-555555555555"),
        "run_id": RUN_ID,
        "research_step_id": STEP_ID,
        "invocation_id": UUID("66666666-6666-4666-8666-666666666666"),
        "observation_type": enums.ObservationType.STRUCTURED_METRIC,
        "status": enums.ObservationStatus.PASS,
        "schema_version": "research-observation-v1",
        "payload": {"metric": "PE", "value": "10.25"},
        "output_checksum": "b" * 64,
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": AS_OF,
        "synthetic_status": enums.SyntheticStatus.REAL_VERIFIED,
        "warnings": (),
        "created_at": AS_OF,
    }

    observation = schemas.ResearchObservationRecord(**base)

    assert observation.payload["value"] == "10.25"
    with pytest.raises(ValidationError):
        schemas.ResearchObservationRecord(**{**base, "payload": {"value": 10.25}})
    with pytest.raises(ValidationError):
        schemas.ResearchObservationRecord(**{**base, "payload": {"text": "x" * 262_145}})


def test_component_security_identity_observation_has_step_lineage_without_invocation() -> None:
    """RED-016: a component Observation has a real Step parent and no Invocation."""
    enums, schemas = _modules()

    observation = schemas.ResearchObservationWrite(
        id=UUID("55555555-5555-4555-8555-555555555555"),
        run_id=RUN_ID,
        research_step_id=STEP_ID,
        invocation_id=None,
        observation_type=enums.ObservationType.SECURITY_IDENTITY,
        status=enums.ObservationStatus.PASS,
        schema_version="research-observation-v1",
        payload={"security_id": str(SECURITY_ID)},
        output_checksum="b" * 64,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        synthetic_status=enums.SyntheticStatus.REAL_VERIFIED,
        warnings=(),
        created_at=AS_OF,
    )

    assert observation.research_step_id == STEP_ID
    assert observation.invocation_id is None


def test_numeric_claim_requires_exact_shape_and_serializes_decimal_as_string() -> None:
    enums, schemas = _modules()
    base = {
        "id": UUID("77777777-7777-4777-8777-777777777777"),
        "run_id": RUN_ID,
        "claim_type": enums.ClaimType.FINANCIAL_METRIC,
        "lifecycle_status": enums.ClaimLifecycleStatus.CANDIDATE,
        "support_status": None,
        "statement_code": "PE_RATIO",
        "value": Decimal("10.2500"),
        "unit": "RATIO",
        "currency_code": None,
        "period": "FY2025",
        "as_of_time": AS_OF,
        "metric_basis": "FORMULA:pe:v1",
        "builder_version": "deterministic-claim-builder-v1",
        "validator_version": None,
        "created_at": AS_OF,
        "completed_at": None,
    }

    claim = schemas.ResearchClaimRecord(**base)

    assert '"value":"10.2500"' in claim.model_dump_json()
    for missing in ("value", "unit", "period", "as_of_time", "metric_basis"):
        with pytest.raises(ValidationError):
            schemas.ResearchClaimRecord(**{**base, missing: None})


def test_package_is_structured_only_and_has_explicit_empty_section_status() -> None:
    enums, schemas = _modules()
    section = schemas.ResearchPackageSection(
        section=enums.ResearchSection.DOCUMENT_EVIDENCE,
        status=enums.PackageSectionStatus.BLOCKED,
        claim_ids=(),
        warning_codes=("COMPANY_BODY_NOT_AVAILABLE",),
    )
    package = schemas.ResearchPackageWrite(
        run_id=RUN_ID,
        request_id=REQUEST_ID,
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=AS_OF,
        research_type=enums.ResearchType.COMPANY_OVERVIEW,
        policy_version="controlled-offline-v1",
        planner_version="deterministic-template-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        evidence_version="research-evidence-v1",
        claim_version="claim-support-v1",
        package_version="research-package-v1",
        status=enums.ResearchPackageStatus.BLOCKED,
        sections=(section,),
        evidence_ids=(),
        unsupported_claim_ids=(),
        conflicting_claim_ids=(),
        blocked_capabilities=("DOCUMENT_EVIDENCE",),
        warnings=("COMPANY_BODY_NOT_AVAILABLE",),
        checksum="c" * 64,
    )

    assert package.sections == (section,)
    with pytest.raises(ValidationError):
        schemas.ResearchPackageWrite(
            **package.model_dump(),
            narrative_report="buy this stock",
        )
