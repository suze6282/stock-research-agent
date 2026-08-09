from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from stock_research_agent import cli
from stock_research_agent.domain.data_access.schemas import (
    DataSnapshotUpdate,
    DataSnapshotWrite,
)
from stock_research_agent.domain.data_access.snapshots import (
    SnapshotBuildError,
    SnapshotErrorCode,
)
from tests.fixtures.public_securities import add_public_synthetic_securities

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = "2026-12-31T00:00:00Z"
TRUNCATE_SQL = text(
    "TRUNCATE TABLE data_providers, security_aliases, security_identifiers, securities, "
    "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
)
runner = CliRunner()


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments) or any(
        argument == "integration" and index > 0 and arguments[index - 1] == "-m"
        for index, argument in enumerate(arguments)
    )


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def data_cli_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)
        engine.dispose()
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


@pytest.fixture
def seeded_data_cli(data_cli_engine: Engine, tmp_path: Path) -> Iterator[dict[str, str]]:
    assert TEST_DATABASE_URL is not None
    with data_cli_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    environment = {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "BLOB_STORAGE_ROOT": str(tmp_path / "raw-payloads"),
    }
    seed = runner.invoke(cli.app, ["securities", "seed-v0"], env=environment)
    assert seed.exit_code == 0, seed.stdout
    add_public_synthetic_securities(data_cli_engine)
    try:
        yield environment
    finally:
        with data_cli_engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)


def _ingest(
    environment: dict[str, str],
    query: str,
    category: str,
) -> tuple[int, dict[str, object]]:
    result = runner.invoke(
        cli.app,
        [
            "data",
            "ingest",
            query,
            "--category",
            category,
            "--as-of",
            AS_OF,
            "--fixture",
            "--json",
        ],
        env=environment,
    )
    return result.exit_code, json.loads(result.stdout)


def test_fixture_bootstrap_and_repeated_sample_ingestion_are_idempotent(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    first_sse_code, first_sse = _ingest(seeded_data_cli, "TEST001.SH", "DAILY_PRICES")
    second_sse_code, second_sse = _ingest(seeded_data_cli, "TEST001.SH", "DAILY_PRICES")
    first_mu_code, first_mu = _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    second_mu_code, second_mu = _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    filing_code, filing = _ingest(seeded_data_cli, "TSTX", "FILING_METADATA")
    facts_code, facts = _ingest(seeded_data_cli, "TSTX", "FINANCIAL_FACTS")

    assert [first_sse_code, second_sse_code, first_mu_code, second_mu_code] == [2, 2, 2, 2]
    assert [filing_code, facts_code] == [2, 2]
    assert first_sse["run_id"] == second_sse["run_id"]
    assert first_sse["idempotency_key"] == second_sse["idempotency_key"]
    assert first_mu["run_id"] == second_mu["run_id"]
    assert filing["records_stored"] == 3
    assert facts["records_stored"] == 0
    for payload in (first_sse, first_mu, filing, facts):
        assert payload["status"] == "PARTIAL"
        assert payload["data_origin"] == "FIXTURE"
        assert payload["access_mode"] == "OFFLINE"
        assert payload["live_status"] == "NOT_LIVE"

    with data_cli_engine.connect() as connection:
        counts = {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "data_providers",
                "provider_instrument_mappings",
                "ingestion_runs",
                "raw_payloads",
                "daily_price_bars",
                "source_documents",
                "provider_financial_facts",
            )
        }
    assert counts == {
        "data_providers": 3,
        "provider_instrument_mappings": 3,
        "ingestion_runs": 4,
        "raw_payloads": 4,
        "daily_price_bars": 2,
        "source_documents": 3,
        "provider_financial_facts": 0,
    }


def test_provider_and_mapping_lists_are_bounded_safe_and_marked(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    with data_cli_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO data_providers "
                "(id, code, name, provider_type, status, terms_status, capabilities) "
                "VALUES "
                "('92000000-0000-0000-0000-000000000001', "
                "'UNVERIFIED_LIVE', 'Unverified live source', 'MARKET_DATA', "
                "'EXPERIMENTAL', 'NEEDS_REVIEW', '[\"DAILY_PRICES\"]'::jsonb), "
                "('92000000-0000-0000-0000-000000000002', "
                "'VERIFIED_LIVE', 'Verified live source', 'MARKET_DATA', "
                "'APPROVED', 'VERIFIED', '[\"DAILY_PRICES\"]'::jsonb)"
            )
        )
    providers = runner.invoke(
        cli.app,
        ["data", "providers", "--json"],
        env=seeded_data_cli,
    )
    mappings = runner.invoke(
        cli.app,
        ["data", "mappings", "TSTX", "--json"],
        env=seeded_data_cli,
    )

    assert providers.exit_code == 2
    assert mappings.exit_code == 0
    provider_payload = json.loads(providers.stdout)
    mapping_payload = json.loads(mappings.stdout)
    providers_by_code = {provider["code"]: provider for provider in provider_payload["providers"]}
    assert providers_by_code["STAGE1_NASDAQ_FIXTURE"]["data_origin"] == "FIXTURE"
    assert providers_by_code["STAGE1_NASDAQ_FIXTURE"]["access_mode"] == "OFFLINE"
    assert providers_by_code["STAGE1_NASDAQ_FIXTURE"]["live_status"] == "NOT_LIVE"
    assert providers_by_code["UNVERIFIED_LIVE"]["data_origin"] == "UNKNOWN"
    assert providers_by_code["UNVERIFIED_LIVE"]["access_mode"] == "UNKNOWN"
    assert providers_by_code["UNVERIFIED_LIVE"]["live_status"] == "UNKNOWN"
    assert providers_by_code["UNVERIFIED_LIVE"]["warnings"] == ["PROVIDER_LIVE_STATUS_UNVERIFIED"]
    assert providers_by_code["VERIFIED_LIVE"]["data_origin"] == "LIVE"
    assert providers_by_code["VERIFIED_LIVE"]["access_mode"] == "ONLINE"
    assert providers_by_code["VERIFIED_LIVE"]["live_status"] == "LIVE"
    assert mapping_payload["mappings"][0]["access_mode"] == "OFFLINE"
    serialized = (providers.stdout + mappings.stdout).lower()
    for unsafe in ("password", "credential", "storage_uri", "fixture://", "\\\\", "select "):
        assert unsafe not in serialized


def test_live_attempt_is_blocked_without_database_writes(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    result = runner.invoke(
        cli.app,
        [
            "data",
            "ingest",
            "TSTX",
            "--category",
            "DAILY_PRICES",
            "--as-of",
            AS_OF,
            "--json",
        ],
        env=seeded_data_cli,
    )

    assert result.exit_code == 5
    assert "BLOCKED" in result.stdout
    with data_cli_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ingestion_runs")) == 0
        assert connection.scalar(text("SELECT count(*) FROM data_providers")) == 0


def test_sample_snapshots_replay_and_read_tools_return_fixture_envelopes(
    seeded_data_cli: dict[str, str],
) -> None:
    _ingest(seeded_data_cli, "TEST001.SH", "DAILY_PRICES")
    _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    _ingest(seeded_data_cli, "TSTX", "FILING_METADATA")
    _ingest(seeded_data_cli, "TSTX", "FINANCIAL_FACTS")

    sse_first = runner.invoke(
        cli.app,
        ["data", "snapshot", "create", "TEST001.SH", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )
    sse_replay = runner.invoke(
        cli.app,
        ["data", "snapshot", "create", "TEST001.SH", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )
    mu_snapshot = runner.invoke(
        cli.app,
        ["data", "snapshot", "create", "TSTX", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )

    assert [sse_first.exit_code, sse_replay.exit_code, mu_snapshot.exit_code] == [2, 2, 2]
    sse_payload = json.loads(sse_first.stdout)
    replay_payload = json.loads(sse_replay.stdout)
    mu_payload = json.loads(mu_snapshot.stdout)
    assert sse_payload["status"] == replay_payload["status"] == "PARTIAL"
    assert sse_payload["snapshot_id"] == replay_payload["snapshot_id"]
    assert sse_payload["checksum"] == replay_payload["checksum"]
    assert sse_payload["snapshot_version"] == replay_payload["snapshot_version"] == 1
    assert mu_payload["status"] == "PARTIAL"

    snapshot_show = runner.invoke(
        cli.app,
        ["data", "snapshot", "show", mu_payload["snapshot_id"], "--json"],
        env=seeded_data_cli,
    )
    latest = runner.invoke(
        cli.app,
        ["data", "latest-close", "TSTX", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )
    history = runner.invoke(
        cli.app,
        ["data", "price-history", "TSTX", "--snapshot", mu_payload["snapshot_id"], "--json"],
        env=seeded_data_cli,
    )
    facts = runner.invoke(
        cli.app,
        ["data", "financial-facts", "TSTX", "--snapshot", mu_payload["snapshot_id"], "--json"],
        env=seeded_data_cli,
    )
    documents = runner.invoke(
        cli.app,
        ["data", "documents", "TSTX", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )

    assert [snapshot_show.exit_code, latest.exit_code, history.exit_code] == [2, 2, 2]
    assert [facts.exit_code, documents.exit_code] == [2, 2]
    for result in (snapshot_show, latest, history, facts, documents):
        payload = json.loads(result.stdout)
        assert payload["provenance"] == {
            "data_origin": "FIXTURE",
            "access_mode": "OFFLINE",
            "live_status": "NOT_LIVE",
        } or payload["provenance"] == {
            "data_origin": "UNKNOWN",
            "access_mode": "UNKNOWN",
            "live_status": "UNKNOWN",
        }
    assert isinstance(json.loads(latest.stdout)["data"][0]["close"], str)
    assert json.loads(history.stdout)["source_record_ids"]
    assert json.loads(facts.stdout)["data"] == []
    assert len(json.loads(documents.stdout)["data"]) == 3


def test_tools_catalog_commands_need_no_database_configuration() -> None:
    listed = runner.invoke(cli.app, ["tools", "list", "--json"])
    described = runner.invoke(
        cli.app,
        ["tools", "describe", "get_data_snapshot", "--json"],
    )

    assert listed.exit_code == 0
    assert described.exit_code == 0
    assert len(json.loads(listed.stdout)) == 22
    assert json.loads(described.stdout)["name"] == "get_data_snapshot"


def test_write_commits_once_read_commits_zero_and_sessions_close(
    seeded_data_cli: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit_calls = 0
    close_calls = 0
    original_commit = Session.commit
    original_close = Session.close

    def recording_commit(session: Session) -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit(session)

    def recording_close(session: Session) -> None:
        nonlocal close_calls
        close_calls += 1
        original_close(session)

    monkeypatch.setattr(Session, "commit", recording_commit)
    monkeypatch.setattr(Session, "close", recording_close)

    write_code, _payload = _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    after_write = (commit_calls, close_calls)
    read = runner.invoke(cli.app, ["data", "providers", "--json"], env=seeded_data_cli)

    assert write_code == 2
    assert after_write == (1, 1)
    assert read.exit_code == 0
    assert (commit_calls, close_calls) == (1, 2)


def test_unsupported_fixture_combination_is_blocked_without_bootstrap(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    result = runner.invoke(
        cli.app,
        [
            "data",
            "ingest",
            "TEST001.SH",
            "--category",
            "FILING_METADATA",
            "--as-of",
            AS_OF,
            "--fixture",
            "--json",
        ],
        env=seeded_data_cli,
    )

    assert result.exit_code == 5
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["data_origin"] == "FIXTURE"
    with data_cli_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM data_providers")) == 0
        assert connection.scalar(text("SELECT count(*) FROM ingestion_runs")) == 0


def test_snapshot_category_change_uses_next_version_then_replays(
    seeded_data_cli: dict[str, str],
) -> None:
    _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    default = runner.invoke(
        cli.app,
        ["data", "snapshot", "create", "TSTX", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )
    changed = runner.invoke(
        cli.app,
        [
            "data",
            "snapshot",
            "create",
            "TSTX",
            "--as-of",
            AS_OF,
            "--category",
            "DAILY_PRICES",
            "--json",
        ],
        env=seeded_data_cli,
    )
    replay = runner.invoke(
        cli.app,
        [
            "data",
            "snapshot",
            "create",
            "TSTX",
            "--as-of",
            AS_OF,
            "--category",
            "DAILY_PRICES",
            "--json",
        ],
        env=seeded_data_cli,
    )

    assert [default.exit_code, changed.exit_code, replay.exit_code] == [2, 2, 2]
    default_payload = json.loads(default.stdout)
    changed_payload = json.loads(changed.stdout)
    replay_payload = json.loads(replay.stdout)
    assert default_payload["snapshot_version"] == 1
    assert changed_payload["snapshot_version"] == 2
    assert replay_payload["snapshot_id"] == changed_payload["snapshot_id"]
    assert replay_payload["checksum"] == changed_payload["checksum"]


def test_fixture_bootstrap_uses_exact_active_mapping_beyond_first_hundred(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    first_code, _first = _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")
    assert first_code == 2
    with data_cli_engine.begin() as connection:
        security_id = connection.scalar(
            text(
                "SELECT s.id FROM securities s "
                "JOIN exchanges e ON e.id = s.exchange_id "
                "WHERE s.normalized_symbol = 'TSTX' AND e.mic = 'XNAS'"
            )
        )
        assert security_id is not None
        for index in range(1, 102):
            provider_id = f"00000000-0000-0000-0001-{index:012d}"
            connection.execute(
                text(
                    "INSERT INTO data_providers "
                    "(id, code, name, provider_type, status, terms_status, capabilities) "
                    "VALUES (:id, :code, :name, 'MARKET_DATA', 'EXPERIMENTAL', "
                    "'NEEDS_REVIEW', '[\"DAILY_PRICES\"]'::jsonb)"
                ),
                {
                    "id": provider_id,
                    "code": f"UNRELATED_{index:03d}",
                    "name": f"Unrelated {index:03d}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO provider_instrument_mappings "
                    "(id, provider_id, security_id, provider_symbol, "
                    "provider_exchange_code, is_primary, metadata, source_name) "
                    "VALUES (gen_random_uuid(), :provider_id, :security_id, :symbol, "
                    "'XNAS', false, '{}'::jsonb, 'test unrelated mapping')"
                ),
                {
                    "provider_id": provider_id,
                    "security_id": security_id,
                    "symbol": f"UNRELATED-{index:03d}",
                },
            )

    replay_code, replay = _ingest(seeded_data_cli, "TSTX", "DAILY_PRICES")

    assert replay_code == 2
    assert replay["status"] == "PARTIAL"
    with data_cli_engine.connect() as connection:
        target_count = connection.scalar(
            text(
                "SELECT count(*) FROM provider_instrument_mappings m "
                "JOIN data_providers p ON p.id = m.provider_id "
                "WHERE m.security_id = :security_id "
                "AND p.code = 'STAGE1_NASDAQ_FIXTURE'"
            ),
            {"security_id": security_id},
        )
    assert target_count == 1


def test_sec_fixture_ingestion_persists_metadata_only_without_body_or_storage(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    filing_code, filing = _ingest(seeded_data_cli, "TSTX", "FILING_METADATA")

    assert filing_code == 2
    assert filing["records_stored"] == 3
    with data_cli_engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT d.published_at, d.document_status, d.storage_uri, "
                    "p.source_published_at "
                    "FROM source_documents d "
                    "JOIN raw_payloads p ON p.id = d.source_payload_id "
                    "ORDER BY d.filed_at, d.id"
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 3
    assert all(row["source_published_at"] is None for row in rows)
    assert all(row["published_at"] is None for row in rows)
    assert all(row["document_status"] == "METADATA_ONLY" for row in rows)
    assert all(row["storage_uri"] is None for row in rows)


def test_version_conflict_retry_persists_failed_terminal_once_after_session_close(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stock_research_agent.cli_data as cli_data

    with data_cli_engine.begin() as connection:
        security_id = connection.scalar(
            text(
                "SELECT s.id FROM securities s "
                "JOIN exchanges e ON e.id = s.exchange_id "
                "WHERE s.normalized_symbol = 'TSTX' AND e.mic = 'XNAS'"
            )
        )
        assert security_id is not None
        connection.execute(
            text(
                "INSERT INTO data_snapshots "
                "(id, security_id, research_as_of_time, snapshot_version, status, "
                "completed_at, checksum, formula_version) "
                "VALUES "
                "('93000000-0000-0000-0000-000000000001', :security_id, :as_of, "
                "1, 'BUILDING', NULL, NULL, 'raw-data-v1')"
            ),
            {"security_id": security_id, "as_of": AS_OF},
        )
        connection.execute(
            text(
                "UPDATE data_snapshots SET status = 'PARTIAL', completed_at = :as_of, "
                "checksum = :checksum "
                "WHERE id = '93000000-0000-0000-0000-000000000001'"
            ),
            {"as_of": AS_OF, "checksum": "1" * 64},
        )

    class VersionConflictThenFailedBuilder:
        calls = 0

        def __init__(self, repository: object) -> None:
            self.repository = repository

        def build(self, request: object) -> object:
            type(self).calls += 1
            if type(self).calls == 1:
                raise SnapshotBuildError(SnapshotErrorCode.VERSION_CONFLICT)
            snapshot, created = self.repository.get_or_create_snapshot(
                DataSnapshotWrite(
                    security_id=request.security_id,
                    research_as_of_time=request.research_as_of_time,
                    snapshot_version=request.snapshot_version,
                    status="BUILDING",
                    formula_version="raw-data-v1",
                )
            )
            assert created
            self.repository.update_snapshot(
                snapshot.id,
                DataSnapshotUpdate(
                    status="FAILED",
                    completed_at=request.research_as_of_time,
                    notes="safe test failure",
                ),
            )
            raise SnapshotBuildError(SnapshotErrorCode.BUILD_FAILED)

    commit_calls = 0
    original_commit = Session.commit

    def recording_commit(session: Session) -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit(session)

    monkeypatch.setattr(cli_data, "SnapshotBuilder", VersionConflictThenFailedBuilder)
    monkeypatch.setattr(Session, "commit", recording_commit)

    result = runner.invoke(
        cli.app,
        ["data", "snapshot", "create", "TSTX", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )

    assert result.exit_code == 6
    assert json.loads(result.stdout) == {
        "status": "FAIL",
        "message": "Snapshot creation failed safely",
    }
    assert VersionConflictThenFailedBuilder.calls == 2
    assert commit_calls == 1
    with data_cli_engine.connect() as connection:
        failed = (
            connection.execute(
                text(
                    "SELECT snapshot_version, status, checksum "
                    "FROM data_snapshots "
                    "WHERE security_id = :security_id AND research_as_of_time = :as_of "
                    "ORDER BY snapshot_version"
                ),
                {"security_id": security_id, "as_of": AS_OF},
            )
            .mappings()
            .all()
        )
    assert failed == [
        {"snapshot_version": 1, "status": "PARTIAL", "checksum": "1" * 64},
        {"snapshot_version": 2, "status": "FAILED", "checksum": None},
    ]


def test_version_conflict_retry_without_terminal_row_rolls_back_and_commits_zero(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stock_research_agent.cli_data as cli_data

    with data_cli_engine.begin() as connection:
        security_id = connection.scalar(
            text(
                "SELECT s.id FROM securities s "
                "JOIN exchanges e ON e.id = s.exchange_id "
                "WHERE s.normalized_symbol = 'TSTX' AND e.mic = 'XNAS'"
            )
        )
        assert security_id is not None
        connection.execute(
            text(
                "INSERT INTO data_snapshots "
                "(id, security_id, research_as_of_time, snapshot_version, status, "
                "completed_at, checksum, formula_version) "
                "VALUES "
                "('93000000-0000-0000-0000-000000000002', :security_id, :as_of, "
                "1, 'BUILDING', NULL, NULL, 'raw-data-v1')"
            ),
            {"security_id": security_id, "as_of": AS_OF},
        )
        connection.execute(
            text(
                "UPDATE data_snapshots SET status = 'PARTIAL', completed_at = :as_of, "
                "checksum = :checksum "
                "WHERE id = '93000000-0000-0000-0000-000000000002'"
            ),
            {"as_of": AS_OF, "checksum": "2" * 64},
        )

    class VersionConflictThenPersistenceFailureBuilder:
        calls = 0

        def __init__(self, repository: object) -> None:
            self.repository = repository

        def build(self, _request: object) -> object:
            type(self).calls += 1
            code = (
                SnapshotErrorCode.VERSION_CONFLICT
                if type(self).calls == 1
                else SnapshotErrorCode.PERSISTENCE_FAILED
            )
            raise SnapshotBuildError(code)

    commit_calls = 0

    def recording_commit(_session: Session) -> None:
        nonlocal commit_calls
        commit_calls += 1

    monkeypatch.setattr(cli_data, "SnapshotBuilder", VersionConflictThenPersistenceFailureBuilder)
    monkeypatch.setattr(Session, "commit", recording_commit)

    result = runner.invoke(
        cli.app,
        ["data", "snapshot", "create", "TSTX", "--as-of", AS_OF, "--json"],
        env=seeded_data_cli,
    )

    assert result.exit_code == 6
    assert VersionConflictThenPersistenceFailureBuilder.calls == 2
    assert commit_calls == 0
    with data_cli_engine.connect() as connection:
        versions = connection.scalars(
            text(
                "SELECT snapshot_version FROM data_snapshots "
                "WHERE security_id = :security_id AND research_as_of_time = :as_of "
                "ORDER BY snapshot_version"
            ),
            {"security_id": security_id, "as_of": AS_OF},
        ).all()
    assert versions == [1]


def test_incompatible_provider_bootstrap_conflict_rolls_back_safely(
    seeded_data_cli: dict[str, str],
    data_cli_engine: Engine,
) -> None:
    with data_cli_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO data_providers "
                "(id, code, name, provider_type, status, terms_status, capabilities) "
                "VALUES "
                "('91000000-0000-0000-0000-000000000001', "
                "'STAGE1_NASDAQ_FIXTURE', 'Incompatible', 'FIXTURE', "
                "'EXPERIMENTAL', 'NEEDS_REVIEW', '[\"DAILY_PRICES\"]'::jsonb)"
            )
        )

    result = runner.invoke(
        cli.app,
        [
            "data",
            "ingest",
            "TSTX",
            "--category",
            "DAILY_PRICES",
            "--as-of",
            AS_OF,
            "--fixture",
            "--json",
        ],
        env=seeded_data_cli,
    )

    assert result.exit_code == 6
    assert json.loads(result.stdout)["status"] == "FAIL"
    with data_cli_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM provider_instrument_mappings")) == 0
        assert connection.scalar(text("SELECT count(*) FROM ingestion_runs")) == 0


@pytest.mark.parametrize(
    ("query", "expected_code", "expected_status"),
    [
        ("Definitely Missing", 3, "NOT_FOUND"),
        ("...", 4, "INVALID_QUERY"),
    ],
)
def test_data_commands_preserve_resolution_status_and_exit_codes(
    seeded_data_cli: dict[str, str],
    query: str,
    expected_code: int,
    expected_status: str,
) -> None:
    result = runner.invoke(
        cli.app,
        ["data", "mappings", query, "--json"],
        env=seeded_data_cli,
    )

    assert result.exit_code == expected_code
    assert json.loads(result.stdout)["status"] == expected_status
