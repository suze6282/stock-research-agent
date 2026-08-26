from __future__ import annotations

import os
import sys
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)
from stock_research_agent.providers.sec_edgar.bootstrap import (
    SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP,
    SecProviderControlPlaneBootstrapApplication,
    SecProviderControlPlaneBootstrapConflict,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for SEC Provider bootstrap tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    value = create_engine(TEST_DATABASE_URL)
    with value.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) != "stock_research"
    yield value
    value.dispose()


def _delete_bootstrap_rows(engine: Engine) -> None:
    identity = (
        "SELECT id FROM provider_definitions "
        "WHERE code = 'SEC_EDGAR_PUBLIC_V1' AND definition_version = '1.0.0'"
    )
    with engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM provider_policies WHERE provider_definition_id IN ({identity})")
        )
        connection.execute(
            text(f"DELETE FROM provider_capabilities WHERE provider_definition_id IN ({identity})")
        )
        connection.execute(
            text(
                "DELETE FROM provider_definitions "
                "WHERE code = 'SEC_EDGAR_PUBLIC_V1' AND definition_version = '1.0.0'"
            )
        )


@pytest.fixture(autouse=True)
def clean_sec_bootstrap_state(engine: Engine) -> Iterator[None]:
    _delete_bootstrap_rows(engine)
    yield
    _delete_bootstrap_rows(engine)


def _application(engine: Engine) -> SecProviderControlPlaneBootstrapApplication:
    return SecProviderControlPlaneBootstrapApplication(
        lambda: Session(engine), SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP
    )


def _component_statuses(result: object) -> dict[str, str]:
    return {component.component: component.status.value for component in result.components}


def _counts(engine: Engine) -> tuple[int, int, int]:
    with engine.connect() as connection:
        return (
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_definitions "
                    "WHERE code = 'SEC_EDGAR_PUBLIC_V1' AND definition_version = '1.0.0'"
                )
            ),
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_capabilities c "
                    "JOIN provider_definitions d ON d.id = c.provider_definition_id "
                    "WHERE d.code = 'SEC_EDGAR_PUBLIC_V1'"
                )
            ),
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_policies p "
                    "JOIN provider_definitions d ON d.id = p.provider_definition_id "
                    "WHERE d.code = 'SEC_EDGAR_PUBLIC_V1'"
                )
            ),
        )


def _seed_definition(engine: Engine) -> object:
    with Session(engine) as session, session.begin():
        return SqlAlchemyProviderDefinitionRepository(session).add_definition(
            SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.definition
        )


def _seed_capability(engine: Engine, definition_id: object) -> object:
    value = SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.capability.materialize(definition_id)
    with Session(engine) as session, session.begin():
        return SqlAlchemyProviderGovernanceRepository(session).add_capability(value)


def test_red_bootstrap_corr_002_definition_only_projects_reused_definition(
    engine: Engine,
) -> None:
    definition = _seed_definition(engine)

    result = _application(engine).bootstrap()

    assert result.status.value == "CREATED"
    assert result.definition_id == definition.id
    assert _component_statuses(result) == {
        "definition": "REUSED",
        "capability": "CREATED",
        "policy": "CREATED",
    }


def test_red_bootstrap_corr_003_definition_capability_projects_only_policy_created(
    engine: Engine,
) -> None:
    definition = _seed_definition(engine)
    capability = _seed_capability(engine, definition.id)

    result = _application(engine).bootstrap()

    assert result.status.value == "CREATED"
    assert result.definition_id == definition.id
    assert result.capability_id == capability.id
    assert _component_statuses(result) == {
        "definition": "REUSED",
        "capability": "REUSED",
        "policy": "CREATED",
    }


def test_red_bootstrap_corr_004_full_equivalent_projects_all_reused(engine: Engine) -> None:
    first = _application(engine).bootstrap()

    result = _application(engine).bootstrap()

    assert result.status.value == "REUSED"
    assert (result.definition_id, result.capability_id, result.policy_id) == (
        first.definition_id,
        first.capability_id,
        first.policy_id,
    )
    assert _component_statuses(result) == {
        "definition": "REUSED",
        "capability": "REUSED",
        "policy": "REUSED",
    }


def test_red_bootstrap_corr_005_empty_state_projects_all_created(engine: Engine) -> None:
    result = _application(engine).bootstrap()

    assert result.status.value == "CREATED"
    assert _component_statuses(result) == {
        "definition": "CREATED",
        "capability": "CREATED",
        "policy": "CREATED",
    }


def test_red_bootstrap_corr_006_readback_mismatch_rolls_back(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = SqlAlchemyProviderGovernanceRepository.get_policy
    calls = 0

    def mismatched_readback(
        repository: SqlAlchemyProviderGovernanceRepository,
        provider_id: object,
        version: str,
    ) -> object:
        nonlocal calls
        calls += 1
        record = original(repository, provider_id, version)
        if calls >= 2 and record is not None:
            return record.model_copy(update={"checksum": "0" * 64})
        return record

    monkeypatch.setattr(
        SqlAlchemyProviderGovernanceRepository,
        "get_policy",
        mismatched_readback,
    )

    with pytest.raises(
        SecProviderControlPlaneBootstrapConflict,
        match="SEC_PROVIDER_BOOTSTRAP_READBACK_MISMATCH",
    ):
        _application(engine).bootstrap()

    assert _counts(engine) == (0, 0, 0)


def test_red_bootstrap_corr_007_commit_failure_suppresses_success(engine: Engine) -> None:
    def failing_session_factory() -> Session:
        session = Session(engine)

        def fail_commit(_session: Session) -> None:
            raise RuntimeError("INJECTED_BOOTSTRAP_COMMIT_FAILURE")

        event.listen(session, "before_commit", fail_commit, once=True)
        return session

    application = SecProviderControlPlaneBootstrapApplication(
        failing_session_factory,
        SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP,
    )

    with pytest.raises(RuntimeError, match="INJECTED_BOOTSTRAP_COMMIT_FAILURE"):
        application.bootstrap()

    assert _counts(engine) == (0, 0, 0)
