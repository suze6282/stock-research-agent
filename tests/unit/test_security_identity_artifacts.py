from __future__ import annotations

import importlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from stock_research_agent.domain.research_agent.canonical import canonical_json, stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    EvidenceStatus,
    ObservationStatus,
    ObservationType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.evidence import EvidenceLedgerService
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchObservationRecord,
)
from stock_research_agent.domain.securities.schemas import (
    ExchangeRecord,
    IssuerRecord,
    MarketRecord,
    SecurityDetail,
    SecurityRecord,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
    SECURITY_MASTER_SEED_V0,
)

NOW = datetime(2026, 7, 10, 12, tzinfo=UTC)
RUN_ID = UUID("91000000-0000-4000-8000-000000000001")
STEP_ID = UUID("91000000-0000-4000-8000-000000000002")
SNAPSHOT_ID = UUID("91000000-0000-4000-8000-000000000003")
REQUEST_ID = UUID("91000000-0000-4000-8000-000000000004")


def _detail(security_id: UUID = INDUSTRIAL_FII_SECURITY_ID) -> SecurityDetail:
    security_seed = next(
        item for item in SECURITY_MASTER_SEED_V0.securities if item.id == security_id
    )
    issuer_seed = next(
        item for item in SECURITY_MASTER_SEED_V0.issuers if item.id == security_seed.issuer_id
    )
    exchange_seed = next(
        item for item in SECURITY_MASTER_SEED_V0.exchanges if item.id == security_seed.exchange_id
    )
    market_seed = next(
        item for item in SECURITY_MASTER_SEED_V0.markets if item.id == exchange_seed.market_id
    )
    timestamps = {"created_at": NOW, "updated_at": NOW}
    return SecurityDetail(
        security=SecurityRecord(**security_seed.model_dump(mode="python"), **timestamps),
        issuer=IssuerRecord(**issuer_seed.model_dump(mode="python"), **timestamps),
        exchange=ExchangeRecord(**exchange_seed.model_dump(mode="python"), **timestamps),
        market=MarketRecord(**market_seed.model_dump(mode="python"), **timestamps),
    )


def _projection(detail: SecurityDetail | None = None) -> dict[str, str]:
    item = detail or _detail()
    return {
        "security_id": str(item.security.id),
        "issuer_id": str(item.issuer.id),
        "issuer": item.issuer.legal_name,
        "symbol": item.security.symbol,
        "exchange_mic": item.exchange.mic,
        "exchange": item.exchange.mic,
    }


def _context() -> ControlledRunContext:
    return ControlledRunContext(
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        research_agent_run_id=RUN_ID,
        research_request_id=REQUEST_ID,
        policy_version="controlled-offline-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
    )


def _observation(**updates: object) -> ResearchObservationRecord:
    payload = _projection()
    values: dict[str, object] = {
        "id": uuid4(),
        "run_id": RUN_ID,
        "research_step_id": STEP_ID,
        "invocation_id": None,
        "observation_type": ObservationType.SECURITY_IDENTITY,
        "status": ObservationStatus.PASS,
        "schema_version": "research-observation-v1",
        "payload": payload,
        "output_checksum": stable_checksum(payload),
        "security_id": INDUSTRIAL_FII_SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "warnings": (),
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchObservationRecord.model_validate(values)


class _SecurityMaster:
    def __init__(self, detail: SecurityDetail | None = None) -> None:
        self.detail = detail or _detail()
        self.load_count = 0

    def get_security(self, security_id: UUID) -> SecurityDetail:
        self.load_count += 1
        return self.detail


class _LedgerSpy(EvidenceLedgerService):
    def __init__(self) -> None:
        self.admit_count = 0

    def admit(self, **kwargs: object):  # type: ignore[no-untyped-def, override]
        self.admit_count += 1
        return super().admit(**kwargs)  # type: ignore[arg-type]


def test_security_master_identity_v1_projection_and_checksum_are_deterministic() -> None:
    """RED-026: production projection uses canonical JSON and a versioned digest."""
    module = importlib.import_module("stock_research_agent.domain.research_agent.evidence_adapters")
    project = module.security_master_identity_projection
    checksum = module.security_master_identity_checksum

    first = project(_detail())
    reordered = dict(reversed(tuple(first.items())))
    second = project(_detail())

    assert first == second == _projection()
    assert canonical_json(first).encode("utf-8") == canonical_json(reordered).encode("utf-8")
    assert checksum(first) == checksum(reordered)
    assert checksum(first) == stable_checksum(
        {
            "source_record_type": "SECURITY_MASTER_IDENTITY_V1",
            "projection": first,
        }
    )
    for field in ("security_id", "issuer_id", "symbol", "exchange_mic"):
        changed = {**first, field: f"changed-{field}"}
        assert checksum(changed) != checksum(first)


@pytest.mark.parametrize(
    ("attack", "expected_warning"),
    [
        ("cross_security", "OBSERVATION_SECURITY_MISMATCH"),
        ("cross_issuer", "SOURCE_CHECKSUM_MISMATCH"),
        ("invalid_checksum", "SOURCE_CHECKSUM_MISMATCH"),
        ("modified_projection", "SOURCE_CHECKSUM_MISMATCH"),
        ("synthetic", "SYNTHETIC_EVIDENCE_FOR_REAL_RUN"),
        ("source_record_id", "SOURCE_CHECKSUM_MISMATCH"),
        ("payload_security", "SOURCE_CHECKSUM_MISMATCH"),
    ],
)
def test_identity_adapter_fails_closed_for_corrupt_or_synthetic_identity(
    attack: str,
    expected_warning: str,
) -> None:
    """RED-014: production identity admission never promotes corrupted identity."""
    module = importlib.import_module("stock_research_agent.domain.research_agent.evidence_adapters")
    ledger = _LedgerSpy()
    adapter = module.ProductionObservationEvidenceAdapter(
        snapshots=object(),
        ledger=ledger,
        id_factory=uuid4,
        clock=lambda: NOW,
    )
    observation = _observation()
    source = _SecurityMaster()

    if attack == "cross_security":
        observation = observation.model_copy(update={"security_id": MICRON_SECURITY_ID})
    elif attack == "cross_issuer":
        payload = {**observation.payload, "issuer_id": str(UUID(int=999))}
        observation = observation.model_copy(
            update={"payload": payload, "output_checksum": stable_checksum(payload)}
        )
    elif attack == "invalid_checksum":
        observation = observation.model_copy(update={"output_checksum": "f" * 64})
    elif attack == "modified_projection":
        observation = observation.model_copy(
            update={"payload": {**observation.payload, "symbol": "ALTERED"}}
        )
    elif attack == "synthetic":
        observation = observation.model_copy(
            update={"synthetic_status": SyntheticStatus.SYNTHETIC_TEST_ONLY}
        )
    elif attack == "source_record_id":
        source = _SecurityMaster(_detail(MICRON_SECURITY_ID))
    elif attack == "payload_security":
        payload = {**observation.payload, "security_id": str(MICRON_SECURITY_ID)}
        observation = observation.model_copy(
            update={"payload": payload, "output_checksum": stable_checksum(payload)}
        )

    evidence = adapter.admit_security_identity(
        context=_context(),
        observation=observation,
        security_master=source,
        real_research=True,
    )

    assert ledger.admit_count == 1
    assert source.load_count == 1
    assert evidence.status is EvidenceStatus.INVALID
    assert evidence.warning_codes == (expected_warning,)
