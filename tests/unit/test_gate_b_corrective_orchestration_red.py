from __future__ import annotations

import inspect
import json
from collections.abc import Iterable
from uuid import UUID

import pytest

from stock_research_agent import cli_live
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.gate_b_pilot import (
    SecArtifactSettlementService,
    SecDataQualityStopService,
    SecDocumentCitationResult,
    SecGateBPilotApplication,
)
from stock_research_agent.domain.providers.quality import ProviderDataQualityValidator
from stock_research_agent.providers.sec_edgar.policy import bind_sec_authorized_plan
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptPermit,
    SecAttemptReservationRequest,
    SecExecutionStartResult,
)
from stock_research_agent.providers.sec_edgar.transport import (
    SecTransportResult,
    SecTransportStatus,
)
from tests.unit.test_sec_gate_b_pilot import (
    ARTIFACT_ID,
    _adapter,
    _attempt,
    _context,
    _SettlementTransaction,
    _Storage,
    _TerminalStore,
)
from tests.unit.test_sec_gate_b_transport import (
    _contact_reference,
    _execution,
    _plan,
    _slice,
)

_ACCESSION = "0000723125-25-000028"
_INDEX_PATH = "index.json"
_PRIMARY_PATH = "mu-20250828.htm"
_ORDER = ("SEC_SUBMISSIONS", "SEC_FILING_INDEX", "SEC_PRIMARY_DOCUMENT")


def _exact_plan(*, include_artifact_kinds: bool) -> object:
    submissions = _slice(
        "SEC_SUBMISSIONS",
        0,
        "SEC_SUBMISSIONS_JSON",
        max_response_bytes=2 * 1024 * 1024,
    )
    filing_index = _slice(
        "SEC_FILING_INDEX",
        1,
        "SEC_FILING_DOCUMENT",
        accession_number=_ACCESSION,
        document_path=_INDEX_PATH,
        form="10-K",
        max_response_bytes=1024 * 1024,
    )
    filing_index["depends_on"] = ("SEC_SUBMISSIONS",)
    primary = _slice(
        "SEC_PRIMARY_DOCUMENT",
        2,
        "SEC_FILING_DOCUMENT",
        accession_number=_ACCESSION,
        document_path=_PRIMARY_PATH,
        form="10-K",
        max_response_bytes=20 * 1024 * 1024,
    )
    primary["depends_on"] = ("SEC_FILING_INDEX",)
    if include_artifact_kinds:
        submissions["request_parameters"]["artifact_kind"] = "SUBMISSIONS_METADATA"  # type: ignore[index]
        filing_index["request_parameters"]["artifact_kind"] = "FILING_INDEX"  # type: ignore[index]
        primary["request_parameters"]["artifact_kind"] = "PRIMARY_FILING_DOCUMENT"  # type: ignore[index]
    return _plan(slices=(submissions, filing_index, primary), slice_count=3)


def _non_exact_plans() -> Iterable[tuple[str, object]]:
    exact_without_kinds = _exact_plan(include_artifact_kinds=False)
    slices = exact_without_kinds.slices  # type: ignore[attr-defined]
    yield "missing filing index", _plan(slices=(slices[0], slices[2]), slice_count=2)
    yield (
        "wrong order",
        _plan(
            slices=(
                {**slices[1], "ordinal": 0, "depends_on": ()},
                {**slices[0], "ordinal": 1, "depends_on": ()},
                slices[2],
            ),
            slice_count=3,
        ),
    )
    yield (
        "Company Facts is out of scope",
        _plan(
            slices=(
                _slice("SEC_SUBMISSIONS", 0, "SEC_SUBMISSIONS_JSON"),
                _slice("SEC_COMPANY_FACTS", 1, "SEC_COMPANY_FACTS_JSON"),
                _slice(
                    "SEC_PRIMARY_DOCUMENT",
                    2,
                    "SEC_FILING_DOCUMENT",
                    accession_number=_ACCESSION,
                    document_path=_PRIMARY_PATH,
                ),
            ),
            slice_count=3,
        ),
    )
    wrong_kind = _exact_plan(include_artifact_kinds=True)
    wrong_slices = list(wrong_kind.slices)  # type: ignore[attr-defined]
    wrong_slices[1]["request_parameters"]["artifact_kind"] = "PRIMARY_FILING_DOCUMENT"
    yield "wrong artifact kind", _plan(slices=tuple(wrong_slices), slice_count=3)
    wrong_ordinal = list(slices)
    wrong_ordinal[2] = {**wrong_ordinal[2], "ordinal": 3}
    yield "wrong ordinal", _plan(slices=tuple(wrong_ordinal), slice_count=3)


def test_red_057_exact_plan_binds_submissions_index_and_primary_with_frozen_kinds() -> None:
    authorized = bind_sec_authorized_plan(
        _execution(),
        _exact_plan(include_artifact_kinds=True),  # type: ignore[arg-type]
    )

    assert tuple(resource.slice_id for resource in authorized.resources) == _ORDER
    assert tuple(resource.artifact_kind.value for resource in authorized.resources) == (
        "SUBMISSIONS_METADATA",
        "FILING_INDEX",
        "PRIMARY_FILING_DOCUMENT",
    )
    assert tuple(resource.max_response_bytes for resource in authorized.resources) == (
        2 * 1024 * 1024,
        1024 * 1024,
        20 * 1024 * 1024,
    )


@pytest.mark.parametrize(("reason", "plan"), tuple(_non_exact_plans()))
def test_red_057_non_exact_or_company_facts_plan_is_rejected_before_send(
    reason: str,
    plan: object,
) -> None:
    del reason
    with pytest.raises(ValueError, match="SEC_PLAN_RESOURCE_INVALID"):
        bind_sec_authorized_plan(_execution(), plan)  # type: ignore[arg-type]


class _RecordingTransport:
    def __init__(
        self,
        *,
        failed_slices: frozenset[str] = frozenset(),
        submissions_primary: str = _PRIMARY_PATH,
    ) -> None:
        self.calls: list[str] = []
        self.failed_slices = failed_slices
        self.submissions_primary = submissions_primary

    def execute(
        self,
        execution: object,
        *,
        plan: object,
        slice_id: str,
        contact_reference: object,
        permit: SecAttemptPermit,
    ) -> SecTransportResult:
        del contact_reference
        self.calls.append(slice_id)
        bind_sec_authorized_plan(execution, plan).require_resource(slice_id)  # type: ignore[arg-type]
        body = (
            json.dumps(
                {
                    "cik": "0000723125",
                    "filings": [
                        {
                            "accessionNumber": _ACCESSION,
                            "form": "10-K",
                            "filingDate": "2025-10-03",
                            "reportDate": "2025-08-28",
                            "acceptanceDateTime": "2025-10-03T10:30:00Z",
                            "primaryDocument": self.submissions_primary,
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()
            if slice_id == "SEC_SUBMISSIONS"
            else (
                b"<!doctype html><html><body>"
                + _PRIMARY_PATH.encode()
                + b" offline SEC fixture</body></html>"
            )
        )
        attempt = _attempt(
            body,
            content_type=("application/json" if slice_id == "SEC_SUBMISSIONS" else "text/html"),
        ).model_copy(
            update={
                "permit": permit,
            }
        )
        if slice_id in self.failed_slices:
            attempt = attempt.model_copy(
                update={
                    "response": None,
                    "safe_error_code": f"{slice_id}_FAILED",
                    "socket_opened": False,
                }
            )
            return SecTransportResult(
                status=SecTransportStatus.BLOCKED,
                reason_code=f"{slice_id}_FAILED",
                attempts=(attempt,),
            )
        return SecTransportResult(
            status=SecTransportStatus.COMPLETED,
            reason_code="SEC_TRANSPORT_COMPLETED",
            attempts=(attempt,),
        )


class _Documents:
    def admit(self, committed: object, validated: object) -> SecDocumentCitationResult:
        del committed, validated
        return SecDocumentCitationResult(
            document_version_id=UUID("91000000-0000-0000-0000-000000000001"),
            citation_ids=(UUID("92000000-0000-0000-0000-000000000001"),),
        )


class _Reservations:
    def __init__(self) -> None:
        self.requests: list[SecAttemptReservationRequest] = []

    def reserve(self, request: SecAttemptReservationRequest) -> SecAttemptPermit:
        self.requests.append(request)
        return SecAttemptPermit(
            **request.model_dump(mode="python"),
            request_attempt_id=UUID(int=100 + request.attempt_number),
        )


def _start() -> SecExecutionStartResult:
    execution = _execution()
    return SecExecutionStartResult(
        execution=execution,
        initial_permit=SecAttemptPermit(
            authorization_id=execution.authorization_id,
            plan_id=execution.plan_id,
            plan_checksum=execution.plan_checksum,
            slice_id="SEC_SUBMISSIONS",
            endpoint_id="SEC_SUBMISSIONS_JSON",
            attempt_number=1,
            kind=SecAttemptKind.INITIAL,
            request_attempt_id=UUID(int=101),
        ),
    )


def _context_for(resource: object) -> object:
    slice_id = resource.slice_id  # type: ignore[attr-defined]
    if slice_id == "SEC_SUBMISSIONS":
        return _context()
    document_path = _INDEX_PATH if slice_id == "SEC_FILING_INDEX" else _PRIMARY_PATH
    return _context(
        source_identity=(f"SEC_FILING_DOCUMENT:0000723125:{_ACCESSION}:{document_path}"),
        source_endpoint_type="SEC_FILING_DOCUMENT",
        artifact_kind=resource.artifact_kind,  # type: ignore[attr-defined]
        source_published_at=_context().retrieved_at,  # type: ignore[attr-defined]
        expected_accession_number=_ACCESSION,
        expected_document_path=document_path,
    )


def _pilot(transport: _RecordingTransport) -> tuple[SecGateBPilotApplication, _TerminalStore]:
    terminal = _TerminalStore()
    return (
        SecGateBPilotApplication(
            transport=transport,
            adapter=_adapter(),
            settlement=SecArtifactSettlementService(
                storage=_Storage(),
                transaction_factory=lambda: _SettlementTransaction([]),
            ),
            documents=_Documents(),
            data_quality=SecDataQualityStopService(
                validator=ProviderDataQualityValidator(),
                terminal_store=terminal,
            ),
            artifact_id_factory=lambda: ARTIFACT_ID,
            reservations=_Reservations(),
            ingestion_context_factory=_context_for,  # type: ignore[arg-type]
        ),
        terminal,
    )


def test_red_058_pilot_executes_all_three_resources_in_order_under_one_execution() -> None:
    transport = _RecordingTransport()
    pilot, _terminal = _pilot(transport)

    pilot.execute_authorized(
        _start(),
        plan=_exact_plan(include_artifact_kinds=False),  # type: ignore[arg-type]
        contact_reference=_contact_reference(),
    )

    assert transport.calls == list(_ORDER), (
        "pilot still executes only the caller-selected slice instead of the full plan"
    )


def test_red_058_submissions_primary_identity_must_match_frozen_plan() -> None:
    transport = _RecordingTransport(submissions_primary="forged-primary.htm")
    pilot, terminal = _pilot(transport)

    with pytest.raises(LiveEvidenceValidationError, match="SEC_RESOURCE_DEPENDENCY_INVALID"):
        pilot.execute_authorized(
            _start(),
            plan=_exact_plan(include_artifact_kinds=False),  # type: ignore[arg-type]
            contact_reference=_contact_reference(),
        )

    assert transport.calls == ["SEC_SUBMISSIONS"]
    assert len(terminal.results) == 1
    terminal_result, issues = terminal.results[0]
    assert terminal_result.status == "BLOCKED"
    assert terminal_result.failed_ordinal == 0
    assert terminal_result.failed_slice_id == "SEC_SUBMISSIONS"
    assert terminal_result.stop_reason == "SEC_RESOURCE_DEPENDENCY_INVALID"
    assert issues == ()


@pytest.mark.parametrize(
    ("failed_slice", "forbidden_successor"),
    (
        ("SEC_SUBMISSIONS", "SEC_FILING_INDEX"),
        ("SEC_FILING_INDEX", "SEC_PRIMARY_DOCUMENT"),
    ),
)
def test_red_059_failure_at_ordinal_stops_the_next_resource(
    failed_slice: str,
    forbidden_successor: str,
) -> None:
    transport = _RecordingTransport(failed_slices=frozenset({failed_slice}))
    pilot, _terminal = _pilot(transport)
    plan = _exact_plan(include_artifact_kinds=False)

    with pytest.raises(LiveEvidenceValidationError, match=f"{failed_slice}_FAILED"):
        pilot.execute_authorized(
            _start(),
            plan=plan,  # type: ignore[arg-type]
            contact_reference=_contact_reference(),
        )
    assert forbidden_successor not in transport.calls, (
        "full-plan orchestrator started a successor after predecessor failure"
    )
    assert len(_terminal.results) == 1
    terminal_result, issues = _terminal.results[0]
    assert terminal_result.status == "BLOCKED"
    assert terminal_result.terminal_stage == "RESOURCE_ORCHESTRATION"
    assert terminal_result.failed_slice_id == failed_slice
    assert terminal_result.failed_ordinal == _ORDER.index(failed_slice)
    assert terminal_result.stop_reason == f"{failed_slice}_FAILED"
    assert issues == ()


def test_red_059_primary_failure_never_commits_aggregate_success() -> None:
    transport = _RecordingTransport(failed_slices=frozenset({"SEC_PRIMARY_DOCUMENT"}))
    pilot, terminal = _pilot(transport)

    with pytest.raises(LiveEvidenceValidationError, match="SEC_PRIMARY_DOCUMENT_FAILED"):
        pilot.execute_authorized(
            _start(),
            plan=_exact_plan(include_artifact_kinds=False),  # type: ignore[arg-type]
            contact_reference=_contact_reference(),
        )

    assert len(terminal.results) == 1
    terminal_result, issues = terminal.results[0]
    assert terminal_result.status == "BLOCKED"
    assert terminal_result.terminal_stage == "RESOURCE_ORCHESTRATION"
    assert terminal_result.failed_slice_id == "SEC_PRIMARY_DOCUMENT"
    assert terminal_result.failed_ordinal == 2
    assert terminal_result.stop_reason == "SEC_PRIMARY_DOCUMENT_FAILED"
    assert issues == ()


def test_red_060_single_resource_set_cannot_commit_passed_aggregate_dq() -> None:
    terminal = _TerminalStore()
    service = SecDataQualityStopService(
        validator=ProviderDataQualityValidator(),
        terminal_store=terminal,
    )
    with pytest.raises(LiveEvidenceValidationError, match="GATE_B_RESOURCE_SET_INCOMPLETE"):
        service.evaluate((), _Documents().admit(object(), object()))
    assert terminal.results == []


def test_red_061_production_root_composes_start_full_plan_audit_and_stop() -> None:
    parameters = inspect.signature(cli_live.authorized_sec_pilot_application_factory).parameters
    assert {"execution_start", "audit_repository"} <= set(parameters), (
        "production root does not compose authoritative start and complete audit projection"
    )

    execute_parameters = inspect.signature(SecGateBPilotApplication.execute_authorized).parameters
    assert "slice_id" not in execute_parameters
    assert "ingestion_context" not in execute_parameters
