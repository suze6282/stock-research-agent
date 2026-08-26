from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import ResearchSection, ResearchType
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    RequestedBudgets,
    ResearchRequestCreate,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

MODULE = "stock_research_agent.domain.research_agent.requests"
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_SECURITY_ID = UUID("99999999-9999-4999-8999-999999999999")
SNAPSHOT_ID = UUID("22222222-2222-4222-8222-222222222222")
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
AS_OF = datetime(2026, 7, 23, 4, 5, 6, tzinfo=UTC)


class FakeRequestRepository:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add_request(self, value: object) -> object:
        self.added.append(value)
        return value


class FakeResolver:
    def __init__(self, status: str = "RESOLVED") -> None:
        self.status = status

    def resolve(self, query: str) -> object:
        candidates = (
            (SimpleNamespace(security_id=SECURITY_ID),) if self.status == "RESOLVED" else ()
        )
        return SimpleNamespace(
            status=self.status,
            normalized_query=query.upper(),
            candidates=candidates,
        )


class FakeSnapshots:
    def __init__(
        self,
        *,
        status: str = "COMPLETE",
        security_id: UUID = SECURITY_ID,
        snapshot_as_of: datetime = AS_OF,
    ) -> None:
        self.snapshot = SimpleNamespace(
            id=SNAPSHOT_ID,
            status=status,
            security_id=security_id,
            research_as_of_time=snapshot_as_of,
            completed_at=(AS_OF if status in {"COMPLETE", "PARTIAL", "SUPERSEDED"} else None),
            checksum=("a" * 64 if status in {"COMPLETE", "PARTIAL", "SUPERSEDED"} else None),
        )
        self.requested: list[UUID] = []

    def get_snapshot(self, snapshot_id: UUID) -> object:
        self.requested.append(snapshot_id)
        return self.snapshot


class FakePolicies:
    def __init__(self) -> None:
        self.policy = build_controlled_offline_policy()

    def require(self, version: str) -> object:
        assert version == self.policy.version
        return self.policy


def _requests() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _command(**updates: object) -> ResearchRequestCreate:
    values = {
        "security_query": "601138.SH",
        "research_type": ResearchType.COMPANY_OVERVIEW,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": AS_OF,
        "requested_sections": (ResearchSection.SECURITY_IDENTITY,),
        "policy_version": "controlled-offline-v1",
        "planner_version": "deterministic-template-v1",
    }
    values.update(updates)
    return ResearchRequestCreate.model_validate(values)


def _service(
    *,
    resolver: object | None = None,
    snapshots: object | None = None,
    repository: FakeRequestRepository | None = None,
) -> object:
    requests = _requests()
    return requests.ResearchRequestService(
        resolver=resolver or FakeResolver(),
        snapshots=snapshots or FakeSnapshots(),
        policies=FakePolicies(),
        catalog_provider=lambda: build_tool_catalog_snapshot(create_tool_metadata_registry()),
        repository=repository or FakeRequestRepository(),
        id_factory=lambda: REQUEST_ID,
        now=lambda: AS_OF,
    )


def test_preflight_persists_exact_security_snapshot_policy_and_catalog() -> None:
    repository = FakeRequestRepository()
    snapshots = FakeSnapshots()

    result = _service(repository=repository, snapshots=snapshots).create(_command())

    assert result.id == REQUEST_ID
    assert result.resolved_security_id == SECURITY_ID
    assert result.snapshot_id == SNAPSHOT_ID
    assert result.normalized_security_query == "601138.SH"
    assert result.tool_catalog_checksum == (
        "89b3ac1b0b8ca248e9f94385e9eeb08cad4b0f31c4627092298afc02db7e3163"
    )
    assert len(result.request_checksum) == 64
    assert snapshots.requested == [SNAPSHOT_ID]
    assert repository.added == [result]


def test_preflight_accepts_sealed_partial_snapshot_for_controlled_degraded_execution() -> None:
    repository = FakeRequestRepository()

    result = _service(
        repository=repository,
        snapshots=FakeSnapshots(status="PARTIAL"),
    ).create(_command())

    assert result.snapshot_id == SNAPSHOT_ID
    assert repository.added == [result]


@pytest.mark.parametrize("status", ["AMBIGUOUS", "NOT_FOUND", "INVALID_QUERY"])
def test_preflight_rejects_non_unique_security_resolution(status: str) -> None:
    requests = _requests()

    with pytest.raises(requests.ResearchRequestError) as raised:
        _service(resolver=FakeResolver(status)).create(_command())

    assert raised.value.code == "SECURITY_NOT_RESOLVED"


@pytest.mark.parametrize(
    ("snapshots", "code"),
    [
        (
            FakeSnapshots(security_id=OTHER_SECURITY_ID),
            "SNAPSHOT_SECURITY_MISMATCH",
        ),
        (
            FakeSnapshots(snapshot_as_of=AS_OF + timedelta(seconds=1)),
            "SNAPSHOT_AFTER_RESEARCH_AS_OF",
        ),
    ],
)
def test_preflight_rejects_ineligible_snapshot(snapshots: object, code: str) -> None:
    requests = _requests()

    with pytest.raises(requests.ResearchRequestError) as raised:
        _service(snapshots=snapshots).create(_command())

    assert raised.value.code == code


@pytest.mark.parametrize("status", ["BUILDING", "FAILED", "SUPERSEDED"])
def test_preflight_rejects_unsealed_or_historical_snapshot_for_new_request(
    status: str,
) -> None:
    requests = _requests()

    with pytest.raises(requests.ResearchRequestError):
        _service(snapshots=FakeSnapshots(status=status)).create(_command())


def test_preflight_rejects_budget_expansion_instead_of_clamping() -> None:
    requests = _requests()
    command = _command(requested_budgets=RequestedBudgets(max_steps=13))

    with pytest.raises(requests.ResearchRequestError) as raised:
        _service().create(command)

    assert raised.value.code == "REQUESTED_BUDGET_EXCEEDS_POLICY"
