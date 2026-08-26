from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
)

MODULE_NAME = "stock_research_agent.providers.sec_edgar.bootstrap"
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
    with engine.begin() as connection:
        definition_ids = text(
            "SELECT id FROM provider_definitions "
            "WHERE code = 'SEC_EDGAR_PUBLIC_V1' AND definition_version = '1.0.0'"
        )
        connection.execute(
            text(
                "DELETE FROM provider_policies WHERE provider_definition_id IN ("
                + definition_ids.text
                + ")"
            )
        )
        connection.execute(
            text(
                "DELETE FROM provider_capabilities WHERE provider_definition_id IN ("
                + definition_ids.text
                + ")"
            )
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


def _api() -> ModuleType:
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as error:
        if error.name == MODULE_NAME:
            pytest.fail("SEC Provider bootstrap application is not implemented", pytrace=False)
        raise
    required = {
        "SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP",
        "SecProviderControlPlaneBootstrapApplication",
        "SecProviderControlPlaneBootstrapConflict",
    }
    if any(not hasattr(module, name) for name in required):
        pytest.fail("SEC Provider bootstrap application is not implemented", pytrace=False)
    return module


def _application(api: ModuleType, engine: Engine, manifest: object | None = None) -> object:
    return api.SecProviderControlPlaneBootstrapApplication(
        session_factory=lambda: Session(engine),
        manifest=manifest or api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP,
    )


def _status(result: object) -> str:
    value = result.status
    return value.value if hasattr(value, "value") else value


def _control_plane_counts(engine: Engine) -> tuple[int, int, int]:
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
                    "WHERE d.code = 'SEC_EDGAR_PUBLIC_V1' "
                    "AND c.code = 'FETCH_SEC_FILING_DOCUMENTS' "
                    "AND c.capability_version = '1.0.0'"
                )
            ),
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_policies p "
                    "JOIN provider_definitions d ON d.id = p.provider_definition_id "
                    "WHERE d.code = 'SEC_EDGAR_PUBLIC_V1' AND p.policy_version = '1.0.0'"
                )
            ),
        )


def _forbidden_counts(engine: Engine) -> dict[str, int]:
    tables = (
        "provider_credential_references",
        "provider_license_policies",
        "provider_sync_requests",
        "provider_sync_plans",
        "live_authorization_grants",
        "live_execution_approvals",
        "provider_sync_runs",
        "provider_request_attempts",
        "provider_raw_artifacts",
        "provider_live_validation_runs",
    )
    with engine.connect() as connection:
        return {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"')) for table in tables
        }


def _seed_definition(api: ModuleType, engine: Engine, *, conflicting: bool = False) -> object:
    definition = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.definition
    if conflicting:
        definition = definition.model_copy(update={"display_name": "Conflicting SEC Provider"})
    with Session(engine) as session, session.begin():
        return SqlAlchemyProviderDefinitionRepository(session).add_definition(definition)


def _seed_capability(api: ModuleType, engine: Engine, definition: object) -> object:
    value = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.capability.materialize(definition.id)
    with Session(engine) as session, session.begin():
        return SqlAlchemyProviderGovernanceRepository(session).add_capability(value)


def _seed_policy(api: ModuleType, engine: Engine, definition: object) -> object:
    value = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.policy.materialize(definition.id)
    with Session(engine) as session, session.begin():
        return SqlAlchemyProviderGovernanceRepository(session).add_policy(value)


def test_postgres_empty_bootstrap_creates_exact_three_rows(engine: Engine) -> None:
    api = _api()

    result = _application(api, engine).bootstrap()

    assert _status(result) == "CREATED"
    assert _control_plane_counts(engine) == (1, 1, 1)


def test_postgres_second_equivalent_bootstrap_reuses_all_ids(engine: Engine) -> None:
    api = _api()
    application = _application(api, engine)

    first = application.bootstrap()
    second = application.bootstrap()

    assert _status(first) == "CREATED"
    assert _status(second) == "REUSED"
    assert (second.definition_id, second.capability_id, second.policy_id) == (
        first.definition_id,
        first.capability_id,
        first.policy_id,
    )
    assert _control_plane_counts(engine) == (1, 1, 1)


def test_postgres_definition_only_state_completes_atomically(engine: Engine) -> None:
    api = _api()
    definition = _seed_definition(api, engine)

    result = _application(api, engine).bootstrap()

    assert _status(result) == "CREATED"
    assert result.definition_id == definition.id
    assert _control_plane_counts(engine) == (1, 1, 1)


def test_postgres_definition_capability_state_completes_policy(engine: Engine) -> None:
    api = _api()
    definition = _seed_definition(api, engine)
    capability = _seed_capability(api, engine, definition)

    result = _application(api, engine).bootstrap()

    assert result.definition_id == definition.id
    assert result.capability_id == capability.id
    assert _control_plane_counts(engine) == (1, 1, 1)


def test_postgres_definition_policy_state_completes_capability(engine: Engine) -> None:
    api = _api()
    definition = _seed_definition(api, engine)
    policy = _seed_policy(api, engine, definition)

    result = _application(api, engine).bootstrap()

    assert result.definition_id == definition.id
    assert result.policy_id == policy.id
    assert _control_plane_counts(engine) == (1, 1, 1)


def test_postgres_conflicting_definition_rolls_back_every_new_row(engine: Engine) -> None:
    api = _api()
    _seed_definition(api, engine, conflicting=True)

    with pytest.raises(
        api.SecProviderControlPlaneBootstrapConflict,
        match="SEC_PROVIDER_BOOTSTRAP_DEFINITION_CONFLICT",
    ):
        _application(api, engine).bootstrap()

    assert _control_plane_counts(engine) == (1, 0, 0)


def test_postgres_conflicting_capability_rolls_back_every_new_row(engine: Engine) -> None:
    api = _api()
    definition = _seed_definition(api, engine)
    capability = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.capability.materialize(
        definition.id
    ).model_copy(update={"data_domain": "CONFLICTING_DOMAIN"})
    with Session(engine) as session, session.begin():
        SqlAlchemyProviderGovernanceRepository(session).add_capability(capability)

    with pytest.raises(
        api.SecProviderControlPlaneBootstrapConflict,
        match="SEC_PROVIDER_BOOTSTRAP_CAPABILITY_CONFLICT",
    ):
        _application(api, engine).bootstrap()

    assert _control_plane_counts(engine) == (1, 1, 0)


def test_postgres_conflicting_policy_rolls_back_every_new_row(engine: Engine) -> None:
    api = _api()
    definition = _seed_definition(api, engine)
    policy = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP.policy.materialize(
        definition.id
    ).model_copy(update={"retention_days": 29})
    with Session(engine) as session, session.begin():
        SqlAlchemyProviderGovernanceRepository(session).add_policy(policy)

    with pytest.raises(
        api.SecProviderControlPlaneBootstrapConflict,
        match="SEC_PROVIDER_BOOTSTRAP_POLICY_CONFLICT",
    ):
        _application(api, engine).bootstrap()

    assert _control_plane_counts(engine) == (1, 0, 1)


def test_postgres_failure_before_commit_leaves_no_partial_bootstrap(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()

    def fail_capability(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("induced pre-commit failure")

    monkeypatch.setattr(SqlAlchemyProviderGovernanceRepository, "add_capability", fail_capability)
    with pytest.raises(RuntimeError, match="induced pre-commit failure"):
        _application(api, engine).bootstrap()

    assert _control_plane_counts(engine) == (0, 0, 0)


def test_postgres_concurrent_identical_bootstrap_creates_one_triplet(engine: Engine) -> None:
    api = _api()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(lambda _index: _application(api, engine).bootstrap(), range(2))
        )

    assert sorted(_status(result) for result in results) == ["CREATED", "REUSED"]
    assert _control_plane_counts(engine) == (1, 1, 1)


def test_postgres_concurrent_conflicting_bootstrap_has_one_winner_one_conflict(
    engine: Engine,
) -> None:
    api = _api()
    approved = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP
    changed_definition = approved.definition.model_copy(update={"display_name": "Conflicting SEC"})
    conflicting = approved.model_copy(update={"definition": changed_definition})

    def invoke(manifest: object) -> str:
        try:
            return _status(_application(api, engine, manifest).bootstrap())
        except api.SecProviderControlPlaneBootstrapConflict:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(invoke, (approved, conflicting)))

    assert sorted(results) == ["CONFLICT", "CREATED"]
    assert _control_plane_counts(engine) in {(1, 1, 1), (1, 0, 0)}


def test_postgres_readback_matches_manifest_and_record_checksums(engine: Engine) -> None:
    api = _api()
    manifest = api.SEC_EDGAR_PUBLIC_V1_CONTROL_PLANE_BOOTSTRAP

    result = _application(api, engine).bootstrap()

    assert result.manifest_checksum == manifest.manifest_checksum
    with Session(engine) as session:
        definition = SqlAlchemyProviderDefinitionRepository(session).get_definition(
            "SEC_EDGAR_PUBLIC_V1", "1.0.0"
        )
        assert definition is not None
        governance = SqlAlchemyProviderGovernanceRepository(session)
        capability = governance.get_capability(definition.id, "FETCH_SEC_FILING_DOCUMENTS", "1.0.0")
        policy = governance.get_policy(definition.id, "1.0.0")
    assert (result.definition_checksum, result.capability_checksum, result.policy_checksum) == (
        definition.checksum,
        capability.checksum,
        policy.checksum,
    )


def test_postgres_bootstrap_changes_no_forbidden_table_counts(engine: Engine) -> None:
    api = _api()
    before = _forbidden_counts(engine)

    _application(api, engine).bootstrap()

    assert _forbidden_counts(engine) == before
