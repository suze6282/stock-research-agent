from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ObservationStatus,
    ObservationType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import ControlledRunContext

MODULE = "stock_research_agent.domain.research_agent.observations"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
INVOCATION_ID = UUID("22222222-2222-4222-8222-222222222222")
OBSERVATION_ID = UUID("33333333-3333-4333-8333-333333333333")


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _context() -> ControlledRunContext:
    return ControlledRunContext(
        security_id=UUID("44444444-4444-4444-8444-444444444444"),
        snapshot_id=UUID("55555555-5555-4555-8555-555555555555"),
        research_as_of_time=NOW,
        research_agent_run_id=RUN_ID,
        research_request_id=UUID("66666666-6666-4666-8666-666666666666"),
        policy_version="controlled-offline-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
    )


def test_builder_canonicalizes_output_and_binds_immutable_provenance() -> None:
    observations = _module()
    payload = {
        "source_record_type": "derived_metric",
        "source_record_id": "77777777-7777-4777-8777-777777777777",
        "value": "12.50",
    }

    result = observations.ResearchObservationBuilder().build(
        observation_id=OBSERVATION_ID,
        context=_context(),
        invocation_id=INVOCATION_ID,
        observation_type=ObservationType.STRUCTURED_METRIC,
        status=ObservationStatus.PASS,
        schema_version="observation-v1",
        payload=payload,
        synthetic_status=SyntheticStatus.REAL_VERIFIED,
        warnings=(),
        created_at=NOW,
    )

    assert result.run_id == RUN_ID
    assert result.invocation_id == INVOCATION_ID
    assert result.security_id == _context().security_id
    assert result.snapshot_id == _context().snapshot_id
    assert result.research_as_of_time == NOW
    assert result.output_checksum == stable_checksum(payload)
    assert result.payload == payload
    assert result.payload is not payload


def test_builder_rejects_non_json_output_binary_float_and_oversize_payload() -> None:
    observations = _module()
    builder = observations.ResearchObservationBuilder()
    base = {
        "observation_id": OBSERVATION_ID,
        "context": _context(),
        "invocation_id": INVOCATION_ID,
        "observation_type": ObservationType.DATA_QUALITY,
        "status": ObservationStatus.PASS,
        "schema_version": "observation-v1",
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "warnings": (),
        "created_at": NOW,
    }

    with pytest.raises(observations.ResearchObservationError) as unsupported:
        builder.build(payload={"value": object()}, **base)
    with pytest.raises(observations.ResearchObservationError) as binary_float:
        builder.build(payload={"value": 0.1}, **base)
    with pytest.raises(observations.ResearchObservationError) as oversize:
        builder.build(payload={"value": "x" * 262_145}, **base)

    assert unsupported.value.code == "INVALID_OBSERVATION_OUTPUT"
    assert binary_float.value.code == "INVALID_OBSERVATION_OUTPUT"
    assert oversize.value.code == "OBSERVATION_OUTPUT_TOO_LARGE"


def test_tool_error_and_blocked_capability_have_strict_safe_shapes() -> None:
    observations = _module()
    builder = observations.ResearchObservationBuilder()
    common = {
        "observation_id": OBSERVATION_ID,
        "context": _context(),
        "invocation_id": INVOCATION_ID,
        "schema_version": "observation-v1",
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "warnings": (),
        "created_at": NOW,
    }

    with pytest.raises(observations.ResearchObservationError) as tool_error:
        builder.build(
            observation_type=ObservationType.TOOL_ERROR,
            status=ObservationStatus.PASS,
            payload={"error_code": "INTERNAL"},
            **common,
        )
    with pytest.raises(observations.ResearchObservationError) as blocked:
        builder.build(
            observation_type=ObservationType.BLOCKED_CAPABILITY,
            status=ObservationStatus.BLOCKED,
            payload={"detail": "missing code"},
            **common,
        )

    assert tool_error.value.code == "INVALID_TOOL_ERROR_OBSERVATION"
    assert blocked.value.code == "INVALID_BLOCKED_OBSERVATION"


def test_synthetic_markers_are_preserved_and_never_inferred() -> None:
    observations = _module()

    result = observations.ResearchObservationBuilder().build(
        observation_id=OBSERVATION_ID,
        context=_context(),
        invocation_id=INVOCATION_ID,
        observation_type=ObservationType.DOCUMENT_EVIDENCE,
        status=ObservationStatus.PASS,
        schema_version="observation-v1",
        payload={
            "markers": [
                "SYNTHETIC_TEST_ONLY",
                "NOT_COMPANY_EVIDENCE",
                "OFFLINE",
                "NOT_LIVE",
            ]
        },
        synthetic_status=SyntheticStatus.SYNTHETIC_TEST_ONLY,
        warnings=(),
        created_at=NOW,
    )

    assert result.synthetic_status is SyntheticStatus.SYNTHETIC_TEST_ONLY
    assert result.payload["markers"] == [
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "OFFLINE",
        "NOT_LIVE",
    ]
