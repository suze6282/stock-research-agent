from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from typer.testing import CliRunner

from stock_research_agent.cli import app
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage
from tests.fixtures.public_securities import add_public_synthetic_securities

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = "2026-12-31T00:00:00Z"
TRUNCATE_SQL = text(
    "TRUNCATE TABLE data_providers, security_aliases, security_identifiers, securities, "
    "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
)
runner = CliRunner()


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 4 acceptance tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def acceptance_engine() -> Iterator[Engine]:
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
def acceptance_environment(acceptance_engine: Engine, tmp_path: Path) -> Iterator[dict[str, str]]:
    assert TEST_DATABASE_URL is not None
    with acceptance_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    environment = {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "BLOB_STORAGE_ROOT": str(tmp_path / "raw-payloads"),
    }
    seed = runner.invoke(app, ["securities", "seed-v0"], env=environment)
    assert seed.exit_code == 0, seed.stdout
    add_public_synthetic_securities(acceptance_engine)
    try:
        yield environment
    finally:
        with acceptance_engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)


def test_raw_payload_blob_is_reopenable_after_cli_resource_scope(
    acceptance_environment: dict[str, str],
    acceptance_engine: Engine,
) -> None:
    blob_root = Path(acceptance_environment["BLOB_STORAGE_ROOT"])
    _ingest(acceptance_environment, "TSTX", "DAILY_PRICES")
    with acceptance_engine.connect() as connection:
        storage_uri = connection.scalar(text("SELECT storage_uri FROM raw_payloads LIMIT 1"))

    assert isinstance(storage_uri, str)
    assert storage_uri.startswith("blob://local/")
    storage = LocalBlobStorage(blob_root, max_blob_bytes=1024 * 1024)
    try:
        stored = storage.get(storage_uri)
    finally:
        storage.close()
    fixture = (
        PROJECT_ROOT
        / "src"
        / "stock_research_agent"
        / "providers"
        / "fixtures"
        / "data"
        / "tstx_nasdaq_public.json"
    ).read_bytes()
    assert stored == fixture


def _partial_json(environment: dict[str, str], arguments: list[str]) -> dict[str, object]:
    result = runner.invoke(app, arguments, env=environment)
    assert result.exit_code == 2, result.stdout
    return json.loads(result.stdout)


def _ingest(
    environment: dict[str, str], query: str, category: str, *, as_of: str = AS_OF
) -> dict[str, object]:
    return _partial_json(
        environment,
        [
            "data",
            "ingest",
            query,
            "--category",
            category,
            "--as-of",
            as_of,
            "--fixture",
            "--json",
        ],
    )


@pytest.mark.parametrize(
    ("query", "symbol", "provider_code", "manifest", "categories", "expected_items"),
    [
        (
            "TEST001.SH",
            "TEST001",
            "STAGE1_SSE_FIXTURE",
            "test001_sse_public.json",
            ("DAILY_PRICES",),
            1,
        ),
        (
            "TSTX",
            "TSTX",
            "STAGE1_NASDAQ_FIXTURE",
            "tstx_nasdaq_public.json",
            ("DAILY_PRICES", "FILING_METADATA", "FINANCIAL_FACTS"),
            4,
        ),
    ],
)
def test_required_sample_has_full_fixture_lineage_and_stable_snapshot(
    acceptance_environment: dict[str, str],
    acceptance_engine: Engine,
    query: str,
    symbol: str,
    provider_code: str,
    manifest: str,
    categories: tuple[str, ...],
    expected_items: int,
) -> None:
    resolution = runner.invoke(
        app, ["securities", "resolve", query, "--json"], env=acceptance_environment
    )
    assert resolution.exit_code == 0
    assert json.loads(resolution.stdout)["status"] == "RESOLVED"

    ingestions = [_ingest(acceptance_environment, query, category) for category in categories]
    replay = _ingest(acceptance_environment, query, "DAILY_PRICES")
    assert replay["run_id"] == ingestions[0]["run_id"]
    assert replay["idempotency_key"] == ingestions[0]["idempotency_key"]
    assert all(
        (item["data_origin"], item["access_mode"], item["live_status"])
        == ("FIXTURE", "OFFLINE", "NOT_LIVE")
        for item in ingestions
    )

    snapshot = _partial_json(
        acceptance_environment,
        ["data", "snapshot", "create", query, "--as-of", AS_OF, "--json"],
    )
    snapshot_replay = _partial_json(
        acceptance_environment,
        ["data", "snapshot", "create", query, "--as-of", AS_OF, "--json"],
    )
    assert snapshot["snapshot_id"] == snapshot_replay["snapshot_id"]
    assert snapshot["checksum"] == snapshot_replay["checksum"]
    assert snapshot["item_count"] == expected_items
    assert snapshot["status"] == "PARTIAL"
    assert any("UNKNOWN_PUBLICATION" in warning for warning in snapshot["warnings"])

    latest = _partial_json(
        acceptance_environment,
        ["data", "latest-close", query, "--snapshot", str(snapshot["snapshot_id"]), "--json"],
    )
    assert latest["data"][0]["provider_symbol"] == symbol  # type: ignore[index]
    assert latest["source_record_ids"]
    assert latest["provenance"] == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }

    fixture_path = (
        PROJECT_ROOT / "src" / "stock_research_agent" / "providers" / "fixtures" / "data" / manifest
    )
    fixture_checksum = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    with acceptance_engine.connect() as connection:
        lineage = connection.execute(
            text(
                "SELECT p.code, m.provider_symbol, rp.checksum, count(si.id) OVER () "
                "FROM data_providers p "
                "JOIN provider_instrument_mappings m ON m.provider_id = p.id "
                "JOIN raw_payloads rp ON rp.provider_id = p.id AND rp.security_id = m.security_id "
                "JOIN snapshot_items si ON si.provider_id = p.id "
                "JOIN data_snapshots ds ON ds.id = si.snapshot_id "
                "WHERE p.code = :provider_code AND ds.id = :snapshot_id "
                "ORDER BY rp.created_at LIMIT 1"
            ),
            {"provider_code": provider_code, "snapshot_id": snapshot["snapshot_id"]},
        ).one()
    assert lineage[0] == provider_code
    assert lineage[1] == symbol
    assert lineage[2] == fixture_checksum
    assert lineage[3] >= 1


def test_future_fixture_data_is_excluded_and_no_action_is_not_invented(
    acceptance_environment: dict[str, str], acceptance_engine: Engine
) -> None:
    early = _ingest(
        acceptance_environment,
        "TSTX",
        "DAILY_PRICES",
        as_of="2026-01-15T03:59:00Z",
    )
    blocked_action = runner.invoke(
        app,
        [
            "data",
            "ingest",
            "TSTX",
            "--category",
            "CORPORATE_ACTIONS",
            "--as-of",
            AS_OF,
            "--fixture",
            "--json",
        ],
        env=acceptance_environment,
    )

    assert early["records_stored"] == 0
    assert "NO_RECORDS_AS_OF" in early["warnings"]
    assert blocked_action.exit_code == 5
    assert json.loads(blocked_action.stdout)["status"] == "BLOCKED"
    with acceptance_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_price_bars")) == 0
        assert connection.scalar(text("SELECT count(*) FROM corporate_actions")) == 0


def test_provider_revision_preserves_original_payload_and_creates_new_snapshot_version(
    acceptance_environment: dict[str, str], acceptance_engine: Engine
) -> None:
    _ingest(acceptance_environment, "TSTX", "DAILY_PRICES")
    first = _partial_json(
        acceptance_environment,
        ["data", "snapshot", "create", "TSTX", "--as-of", AS_OF, "--json"],
    )
    with acceptance_engine.begin() as connection:
        original_payload = connection.scalar(
            text("SELECT id FROM raw_payloads WHERE category = 'DAILY_PRICES' LIMIT 1")
        )
        revised_payload = connection.scalar(
            text(
                "INSERT INTO raw_payloads "
                "(id, ingestion_run_id, provider_request_log_id, provider_id, security_id, "
                "category, content_type, storage_uri, inline_json, checksum_algorithm, checksum, "
                "source_published_at, retrieved_at, provider_version, parser_version, "
                "schema_version, byte_size) "
                "SELECT gen_random_uuid(), ingestion_run_id, provider_request_log_id, "
                "provider_id, security_id, category, content_type, storage_uri, inline_json, "
                "checksum_algorithm, checksum, source_published_at, retrieved_at, "
                "'1.0.1', parser_version, schema_version, byte_size "
                "FROM raw_payloads WHERE id = :payload_id RETURNING id"
            ),
            {"payload_id": original_payload},
        )
        connection.execute(
            text(
                "INSERT INTO daily_price_bars "
                "(id, security_id, provider_id, source_payload_id, provider_symbol, "
                "trading_date, market_timestamp, open, high, low, close, volume, "
                "currency_code, adjustment_type, provider_adjusted_close, "
                "source_published_at, retrieved_at) "
                "SELECT gen_random_uuid(), security_id, provider_id, :revised_payload, "
                "provider_symbol, trading_date, market_timestamp, open, high, low, close, "
                "volume, currency_code, adjustment_type, provider_adjusted_close, "
                "source_published_at, retrieved_at FROM daily_price_bars "
                "WHERE source_payload_id = :original_payload"
            ),
            {"revised_payload": revised_payload, "original_payload": original_payload},
        )

    second = _partial_json(
        acceptance_environment,
        ["data", "snapshot", "create", "TSTX", "--as-of", AS_OF, "--json"],
    )
    assert second["snapshot_version"] == 2
    assert second["snapshot_id"] != first["snapshot_id"]
    assert second["checksum"] != first["checksum"]
    with acceptance_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM raw_payloads")) == 2
        assert (
            connection.scalar(
                text("SELECT count(*) FROM raw_payloads WHERE id = :id"), {"id": original_payload}
            )
            == 1
        )
