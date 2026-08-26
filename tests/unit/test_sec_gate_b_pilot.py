from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.quality import ProviderDataQualityValidator
from stock_research_agent.infrastructure.provider_artifact_storage import StoredProviderArtifact
from stock_research_agent.providers.http_client import HttpResult
from stock_research_agent.providers.http_policy import CanonicalProviderRequest
from stock_research_agent.providers.sec_edgar.adapter import (
    SecEdgarAdapter,
    SecEdgarCapability,
)
from stock_research_agent.providers.sec_edgar.policy import SecAuthorizedResource
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptPermit,
)
from stock_research_agent.providers.sec_edgar.schemas import SecArtifactKind
from stock_research_agent.providers.sec_edgar.transport import SecPhysicalAttempt

NOW = datetime(2026, 8, 20, tzinfo=UTC)
ATTEMPT_ID = UUID("81000000-0000-0000-0000-000000000001")
ARTIFACT_ID = UUID("82000000-0000-0000-0000-000000000001")
PROVIDER_ID = UUID("83000000-0000-0000-0000-000000000001")
CAPABILITY_ID = UUID("84000000-0000-0000-0000-000000000001")
RUN_ID = UUID("85000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("86000000-0000-0000-0000-000000000001")


def _body(*, cik: str = "0000723125", accepted: str = "2026-08-19T10:00:00Z") -> bytes:
    return json.dumps(
        {
            "cik": cik,
            "filings": [
                {
                    "accessionNumber": "0000723125-26-000001",
                    "form": "10-K",
                    "filingDate": "2026-08-19",
                    "reportDate": "2026-08-01",
                    "acceptanceDateTime": accepted,
                    "primaryDocument": "mu-20260801.htm",
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _resource() -> SecAuthorizedResource:
    return SecAuthorizedResource(
        plan_id=UUID("87000000-0000-0000-0000-000000000001"),
        plan_checksum="a" * 64,
        slice_id="SEC_SUBMISSIONS",
        ordinal=0,
        request=CanonicalProviderRequest(
            endpoint_id="SEC_SUBMISSIONS_JSON",
            method="GET",
            scheme="https",
            host="data.sec.gov",
            port=443,
            path="/submissions/CIK0000723125.json",
            query=(),
            accepted_content_types=("application/json",),
            max_redirects=0,
            url="https://data.sec.gov/submissions/CIK0000723125.json",
        ),
        artifact_kind=SecArtifactKind.SUBMISSIONS_METADATA,
        max_response_bytes=4096,
    )


def _attempt(body: bytes, *, content_type: str = "application/json") -> SecPhysicalAttempt:
    return SecPhysicalAttempt(
        permit=SecAttemptPermit(
            authorization_id=UUID("88000000-0000-0000-0000-000000000001"),
            plan_id=_resource().plan_id,
            plan_checksum=_resource().plan_checksum,
            slice_id=_resource().slice_id,
            endpoint_id="SEC_SUBMISSIONS_JSON",
            attempt_number=1,
            kind=SecAttemptKind.INITIAL,
            request_attempt_id=ATTEMPT_ID,
        ),
        response=HttpResult(
            status_code=200,
            body=body,
            content_type=content_type,
            safe_url="https://data.sec.gov/submissions/CIK…3125.json",
            attempts=1,
            cache_status="MISS",
            etag=None,
            last_modified=None,
        ),
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        socket_opened=True,
    )


def _context(**changes: object) -> object:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import SecIngestionContext

    values: dict[str, object] = {
        "provider_definition_id": PROVIDER_ID,
        "provider_capability_id": CAPABILITY_ID,
        "sync_run_id": RUN_ID,
        "license_policy_id": UUID("89000000-0000-0000-0000-000000000001"),
        "security_id": SECURITY_ID,
        "research_as_of_time": NOW,
        "retrieved_at": NOW,
        "source_published_at": None,
        "adapter_version": "1.0.0",
        "parser_version": "1.0.0",
        "schema_version": "SEC_SUBMISSIONS_V1",
        "synthetic_status": ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT,
        "source_identity": "SEC_SUBMISSIONS_JSON:0000723125",
        "source_endpoint_type": "SEC_SUBMISSIONS_JSON",
        "artifact_kind": SecArtifactKind.SUBMISSIONS_METADATA,
    }
    values.update(changes)
    return SecIngestionContext(**values)


def _adapter() -> SecEdgarAdapter:
    return SecEdgarAdapter(
        security_id=SECURITY_ID,
        cik="0000723125",
        approved_capabilities=(SecEdgarCapability.SUBMISSIONS_METADATA,),
        approved_forms=("10-K",),
    )


def test_red_043_valid_response_is_parsed_once_before_blob_and_database_persistence() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import validate_sec_response

    body = _body()
    settlement = validate_sec_response(
        _attempt(body), _resource(), _context(), _adapter(), artifact_id=ARTIFACT_ID
    )

    assert settlement.artifact_id == ARTIFACT_ID
    assert settlement.request_attempt_id == ATTEMPT_ID
    assert settlement.source_checksum == hashlib.sha256(body).hexdigest()
    assert settlement.batch.record_count == 1
    assert settlement.raw_artifact_draft.expected_checksum == settlement.source_checksum


@pytest.mark.parametrize(
    ("case", "error"),
    (
        ("mime", "SEC_RESPONSE_MIME_INVALID"),
        ("empty", "SEC_RESPONSE_SIZE_INVALID"),
        ("future", "SEC_FUTURE_DATA"),
        ("cik", "SEC_CIK_MISMATCH"),
    ),
)
def test_red_043_wrong_mime_empty_body_checksum_or_future_data_creates_no_artifact_draft(
    case: str,
    error: str,
) -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import validate_sec_response

    attempt = {
        "mime": _attempt(_body(), content_type="text/html"),
        "empty": _attempt(b""),
        "future": _attempt(_body(accepted="2026-08-21T10:00:00Z")),
        "cik": _attempt(_body(cik="0000000001")),
    }[case]
    with pytest.raises(ValueError, match=error):
        validate_sec_response(attempt, _resource(), _context(), _adapter(), artifact_id=ARTIFACT_ID)


class _Storage:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, draft: object, content: bytes) -> StoredProviderArtifact:
        del draft
        self.writes.append(content)
        return StoredProviderArtifact(
            blob_key="a" * 32,
            storage_uri="blob://provider/" + "a" * 32,
            checksum=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
            content_type="application/json",
        )


class _SettlementTransaction:
    def __init__(self, events: list[str], *, fail_artifact: bool = False) -> None:
        self.events = events
        self.fail_artifact = fail_artifact
        self.authoritative_artifacts: list[object] = []

    def __enter__(self) -> _SettlementTransaction:
        self.events.append("settlement_begin")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.events.append("settlement_rollback" if self.fail_artifact else "settlement_commit")

    def settle_attempt(self, value: object) -> object:
        self.events.append("attempt_settled")
        return value

    def settle_consumption(self, value: object) -> object:
        self.events.append("consumption_settled")
        return value

    def add_artifact(self, value: object) -> object:
        if self.fail_artifact:
            raise RuntimeError("injected database failure")
        self.events.append("artifact_persisted")
        self.authoritative_artifacts.append(value)
        return value

    def add_manifest(self, value: object) -> object:
        self.events.append("manifest_persisted")
        return type(
            "ManifestRecord",
            (),
            {"id": UUID("93000000-0000-0000-0000-000000000001")},
        )()


def _validated() -> object:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import validate_sec_response

    body = _body()
    return validate_sec_response(
        _attempt(body), _resource(), _context(), _adapter(), artifact_id=ARTIFACT_ID
    )


def test_red_043_validated_blob_settlement_commits_one_authoritative_artifact() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import (
        SecArtifactSettlementService,
    )

    events: list[str] = []
    storage = _Storage()
    transaction = _SettlementTransaction(events)
    result = SecArtifactSettlementService(
        storage=storage,
        transaction_factory=lambda: transaction,
    ).settle(_validated(), _attempt(_body()))

    assert len(storage.writes) == 1
    assert result.artifact_id == ARTIFACT_ID
    assert events == [
        "settlement_begin",
        "attempt_settled",
        "consumption_settled",
        "artifact_persisted",
        "manifest_persisted",
        "settlement_commit",
    ]


def test_red_045_blob_success_database_failure_rolls_back_authoritative_lineage() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import (
        SecArtifactSettlementService,
    )

    events: list[str] = []
    storage = _Storage()
    transaction = _SettlementTransaction(events, fail_artifact=True)
    with pytest.raises(RuntimeError, match="injected database failure"):
        SecArtifactSettlementService(
            storage=storage,
            transaction_factory=lambda: transaction,
        ).settle(_validated(), _attempt(_body()))

    assert len(storage.writes) == 1
    assert transaction.authoritative_artifacts == []
    assert events[-1] == "settlement_rollback"


def test_committed_pre_send_failure_is_abandoned_without_blob_or_refund() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import (
        SecArtifactSettlementService,
    )

    events: list[str] = []
    storage = _Storage()
    transaction = _SettlementTransaction(events)
    attempt = _attempt(_body()).model_copy(
        update={
            "response": None,
            "safe_error_code": "SEC_CONTACT_RESOLUTION_FAILED",
            "socket_opened": False,
        }
    )

    SecArtifactSettlementService(
        storage=storage,
        transaction_factory=lambda: transaction,
    ).settle_failure(attempt)

    assert storage.writes == []
    assert events == [
        "settlement_begin",
        "attempt_settled",
        "consumption_settled",
        "settlement_commit",
    ]


class _TerminalStore:
    def __init__(self) -> None:
        self.results: list[object] = []

    def commit(self, result: object, issues: tuple[object, ...]) -> UUID:
        self.results.append((result, issues))
        return UUID("90000000-0000-0000-0000-000000000001")


def test_red_049_data_quality_stop_is_committed_and_blocks_downstream() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import (
        CommittedSecSettlement,
        CompletedSecResource,
        SecDataQualityStopService,
        SecDocumentCitationResult,
    )

    terminal_store = _TerminalStore()
    validated = _validated()
    committed = CommittedSecSettlement(
        artifact_id=ARTIFACT_ID,
        manifest_id=UUID("93000000-0000-0000-0000-000000000001"),
        request_attempt_id=ATTEMPT_ID,
        storage_uri="blob://provider/" + "a" * 32,
        content_checksum=validated.source_checksum,
        manifest_checksum=validated.batch.manifest_checksum,
    )
    resources = (
        _resource(),
        _resource().model_copy(
            update={
                "slice_id": "SEC_FILING_INDEX",
                "ordinal": 1,
                "artifact_kind": SecArtifactKind.FILING_INDEX,
            }
        ),
        _resource().model_copy(
            update={
                "slice_id": "SEC_PRIMARY_DOCUMENT",
                "ordinal": 2,
                "artifact_kind": SecArtifactKind.PRIMARY_FILING_DOCUMENT,
            }
        ),
    )
    completed = tuple(
        CompletedSecResource(resource=resource, committed=committed, validated=validated)
        for resource in resources
    )
    result = SecDataQualityStopService(
        validator=ProviderDataQualityValidator(),
        terminal_store=terminal_store,
    ).evaluate(
        completed,
        SecDocumentCitationResult(
            document_version_id=UUID("91000000-0000-0000-0000-000000000001"),
            citation_ids=(UUID("92000000-0000-0000-0000-000000000001"),),
        ),
    )

    assert result.terminal_stage == "DATA_QUALITY"
    assert result.status == "PASSED"
    assert result.artifact_id == ARTIFACT_ID
    assert result.snapshot_created is False
    assert result.research_request_created is False
    assert result.agent_run_created is False
    assert result.claim_created is False
    assert result.report_created is False
    assert result.stage_11_started is False
    assert len(terminal_store.results) == 1


def test_red_045_network_window_has_no_open_ingestion_transaction_and_stops_at_dq() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import (
        SecArtifactSettlementService,
        SecDataQualityStopService,
        SecDocumentCitationResult,
        SecGateBPilotApplication,
    )
    from stock_research_agent.providers.sec_edgar.transport import SecTransportResult
    from tests.unit.test_gate_b_corrective_orchestration_red import (
        _context_for,
        _exact_plan,
        _RecordingTransport,
        _Reservations,
        _start,
    )
    from tests.unit.test_sec_gate_b_transport import _contact_reference

    events: list[str] = []
    transaction = _SettlementTransaction(events)
    start, plan = _start(), _exact_plan(include_artifact_kinds=False)

    class Transport(_RecordingTransport):
        def execute(self, *args: object, **kwargs: object) -> SecTransportResult:
            if self.calls:
                assert events[-1] == "settlement_commit"
            events.append("send_complete")
            return super().execute(*args, **kwargs)

    class Documents:
        def admit(self, committed: object, validated: object) -> SecDocumentCitationResult:
            del committed, validated
            events.append("document_citation_committed")
            return SecDocumentCitationResult(
                document_version_id=UUID("91000000-0000-0000-0000-000000000001"),
                citation_ids=(UUID("92000000-0000-0000-0000-000000000001"),),
            )

    result = SecGateBPilotApplication(
        transport=Transport(),
        adapter=_adapter(),
        settlement=SecArtifactSettlementService(
            storage=_Storage(), transaction_factory=lambda: transaction
        ),
        documents=Documents(),
        data_quality=SecDataQualityStopService(
            validator=ProviderDataQualityValidator(), terminal_store=_TerminalStore()
        ),
        artifact_id_factory=lambda: ARTIFACT_ID,
        reservations=_Reservations(),
        ingestion_context_factory=_context_for,
    ).execute_authorized(
        start,
        plan=plan,
        contact_reference=_contact_reference(),
    )

    assert events[0] == "send_complete"
    assert events[1] == "settlement_begin"
    assert events[-1] == "document_citation_committed"
    assert result.terminal_stage == "DATA_QUALITY"
    assert result.stage_11_started is False


def test_provider_artifact_document_bridge_rejects_uncommitted_lineage_before_factory() -> None:
    from stock_research_agent.domain.live_evidence.document_bridge import (
        ProviderArtifactDocumentBridge,
    )
    from stock_research_agent.domain.live_evidence.gate_b_pilot import CommittedSecSettlement

    calls: list[str] = []

    class Factory:
        def build(self, *args: object) -> object:
            calls.append("build")
            raise AssertionError("must not be called")

    class Citations:
        def add_citations(self, *args: object) -> tuple[UUID, ...]:
            calls.append("citations")
            return ()

    committed = CommittedSecSettlement(
        artifact_id=UUID("82000000-0000-0000-0000-000000000099"),
        manifest_id=UUID("93000000-0000-0000-0000-000000000001"),
        request_attempt_id=ATTEMPT_ID,
        storage_uri="blob://provider/" + "a" * 32,
        content_checksum=_validated().source_checksum,
        manifest_checksum=_validated().batch.manifest_checksum,
    )

    with pytest.raises(ValueError, match="DOCUMENT_ARTIFACT_MISMATCH"):
        ProviderArtifactDocumentBridge(
            request_factory=Factory(),  # type: ignore[arg-type]
            citation_publisher=Citations(),  # type: ignore[arg-type]
        ).admit(committed, _validated())
    assert calls == []
