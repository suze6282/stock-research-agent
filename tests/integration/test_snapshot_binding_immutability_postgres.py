from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from stock_research_agent.config import AppEnvironment, Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("a1000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("a2000000-0000-4000-8000-000000000001")
BINDING_ID = UUID("a3000000-0000-4000-8000-000000000001")
ISSUER_ID = UUID("a6000000-0000-4000-8000-000000000001")
PROVIDER_ID = UUID("a7000000-0000-4000-8000-000000000001")
INGESTION_RUN_ID = UUID("a8000000-0000-4000-8000-000000000001")
REQUEST_LOG_ID = UUID("a9000000-0000-4000-8000-000000000001")
RAW_PAYLOAD_ID = UUID("aa000000-0000-4000-8000-000000000001")
MANIFEST_ID = UUID("ab000000-0000-4000-8000-000000000001")


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments)


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def binding_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=TEST_DATABASE_URL,
    )
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_building_snapshot(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO markets
                    (id, code, name, country_code, default_currency_code, status)
                VALUES
                    (:id, 'US_EQUITY', 'US Equity', 'US', 'USD', 'ACTIVE')
                """
            ),
            {"id": UUID("a4000000-0000-4000-8000-000000000001")},
        )
        connection.execute(
            text(
                """
                INSERT INTO exchanges
                    (id, market_id, mic, name, short_name, country_code, timezone,
                     default_currency_code, status)
                VALUES
                    (:id, :market_id, 'XNAS', 'Nasdaq', 'Nasdaq', 'US',
                     'America/New_York', 'USD', 'ACTIVE')
                """
            ),
            {
                "id": UUID("a5000000-0000-4000-8000-000000000001"),
                "market_id": UUID("a4000000-0000-4000-8000-000000000001"),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO issuers
                    (id, legal_name, normalized_legal_name, display_name,
                     normalized_display_name, country_code, issuer_status)
                VALUES
                    (:id, 'Synthetic Issuer', 'SYNTHETIC ISSUER',
                     'Synthetic Issuer', 'SYNTHETIC ISSUER', 'US', 'ACTIVE')
                """
            ),
            {"id": ISSUER_ID},
        )
        connection.execute(
            text(
                """
                INSERT INTO securities
                    (id, issuer_id, exchange_id, symbol, normalized_symbol,
                     display_name, security_type, currency_code, listing_status)
                VALUES
                    (:id, :issuer_id, :exchange_id, 'SYNTHIMM', 'SYNTHIMM',
                     'Synthetic Immutable Security', 'COMMON_STOCK', 'USD', 'ACTIVE')
                """
            ),
            {
                "id": SECURITY_ID,
                "issuer_id": ISSUER_ID,
                "exchange_id": UUID("a5000000-0000-4000-8000-000000000001"),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO data_providers
                    (id, code, name, provider_type, status, terms_status, capabilities)
                VALUES
                    (:id, 'SYNTH_IMMUTABILITY', 'Synthetic Immutability Fixture',
                     'FIXTURE', 'APPROVED', 'VERIFIED', '["SOURCE_DOCUMENTS"]'::jsonb)
                """
            ),
            {"id": PROVIDER_ID},
        )
        connection.execute(
            text(
                """
                INSERT INTO ingestion_runs
                    (id, provider_id, security_id, category, status, research_as_of_time,
                     idempotency_key, requested_at, started_at, completed_at, request_count,
                     records_received, records_stored, warning_count)
                VALUES
                    (:id, :provider_id, :security_id, 'SOURCE_DOCUMENTS', 'PASS', :as_of,
                     'synthetic:immutability:lineage', :as_of, :as_of, :as_of, 1, 1, 1, 0)
                """
            ),
            {
                "id": INGESTION_RUN_ID,
                "provider_id": PROVIDER_ID,
                "security_id": SECURITY_ID,
                "as_of": NOW,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO provider_request_logs
                    (id, ingestion_run_id, provider_id, caller_request_id,
                     provider_request_id, endpoint_name, method, safe_url,
                     request_started_at, response_received_at, http_status, attempt,
                     cache_status, response_size)
                VALUES
                    (:id, :run_id, :provider_id, :caller_request_id,
                     'synthetic-request', 'synthetic-fixture', 'GET',
                     'https://example.invalid/synthetic', :as_of, :as_of, 200, 1,
                     'NOT_APPLICABLE', 2)
                """
            ),
            {
                "id": REQUEST_LOG_ID,
                "run_id": INGESTION_RUN_ID,
                "provider_id": PROVIDER_ID,
                "caller_request_id": uuid4(),
                "as_of": NOW,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO raw_payloads
                    (id, ingestion_run_id, provider_request_log_id, provider_id, security_id,
                     category, content_type, inline_json, checksum_algorithm, checksum,
                     source_published_at, retrieved_at, provider_version, parser_version,
                     schema_version, byte_size)
                VALUES
                    (:id, :run_id, :request_id, :provider_id, :security_id,
                     'SOURCE_DOCUMENTS', 'application/json', '{}'::jsonb, 'sha256',
                     :checksum, :as_of, :as_of, 'fixture-v1', 'fixture-v1', 'fixture-v1', 2)
                """
            ),
            {
                "id": RAW_PAYLOAD_ID,
                "run_id": INGESTION_RUN_ID,
                "request_id": REQUEST_LOG_ID,
                "provider_id": PROVIDER_ID,
                "security_id": SECURITY_ID,
                "checksum": "f" * 64,
                "as_of": NOW,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO evidence_ingestion_manifests
                    (id, source_type, artifact_id, security_id, issuer_id, status,
                     manifest_checksum, manifest)
                VALUES
                    (:id, 'FIXTURE', :artifact_id, :security_id, :issuer_id, 'COMPLETE',
                     :checksum,
                     '{"synthetic_status":"SYNTHETIC_TEST_ONLY",'
                     '"evidence_status":"NOT_COMPANY_EVIDENCE",'
                     '"network_status":"OFFLINE","live_status":"NOT_LIVE"}'::jsonb)
                """
            ),
            {
                "id": MANIFEST_ID,
                "artifact_id": RAW_PAYLOAD_ID,
                "security_id": SECURITY_ID,
                "issuer_id": ISSUER_ID,
                "checksum": "a" * 64,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO data_snapshots
                    (id, security_id, research_as_of_time, snapshot_version,
                     status, formula_version)
                VALUES
                    (:id, :security_id, :as_of, 1, 'BUILDING', 'raw-data-v1')
                """
            ),
            {"id": SNAPSHOT_ID, "security_id": SECURITY_ID, "as_of": NOW},
        )
        connection.execute(
            text(
                """
                INSERT INTO ingestion_to_snapshot_bindings
                    (id, ingestion_manifest_id, manifest_checksum, security_id,
                     snapshot_id, snapshot_checksum, binding_checksum,
                     research_as_of_time, source_published_at)
                VALUES
                    (:id, :manifest_id, :manifest_checksum, :security_id,
                     :snapshot_id, :snapshot_checksum, :binding_checksum,
                     :as_of, :as_of)
                """
            ),
            {
                "id": BINDING_ID,
                "manifest_id": MANIFEST_ID,
                "manifest_checksum": "a" * 64,
                "security_id": SECURITY_ID,
                "snapshot_id": SNAPSHOT_ID,
                "snapshot_checksum": "b" * 64,
                "binding_checksum": "c" * 64,
                "as_of": NOW,
            },
        )
        connection.execute(
            text(
                """
                UPDATE data_snapshots
                   SET status = 'FAILED', completed_at = :completed_at
                 WHERE id = :id
                """
            ),
            {"completed_at": NOW, "id": SNAPSHOT_ID},
        )


@pytest.mark.parametrize(
    ("statement", "error_code"),
    [
        (
            "UPDATE ingestion_to_snapshot_bindings SET manifest_checksum = :checksum "
            "WHERE id = :binding_id",
            "STAGE10_HISTORY_IMMUTABLE",
        ),
        (
            "DELETE FROM ingestion_to_snapshot_bindings WHERE id = :binding_id",
            "STAGE10_HISTORY_IMMUTABLE",
        ),
        (
            "INSERT INTO ingestion_to_snapshot_bindings "
            "(id, ingestion_manifest_id, manifest_checksum, security_id, snapshot_id, "
            "snapshot_checksum, binding_checksum, research_as_of_time) VALUES "
            "(:new_id, :new_manifest_id, :checksum, :security_id, :snapshot_id, "
            ":snapshot_checksum, :new_binding_checksum, :as_of)",
            "SNAPSHOT_BINDING_IMMUTABLE",
        ),
    ],
)
def test_binding_update_delete_and_late_insert_are_rejected(
    binding_engine: Engine,
    statement: str,
    error_code: str,
) -> None:
    _seed_building_snapshot(binding_engine)
    with pytest.raises(DBAPIError, match=error_code):
        with binding_engine.begin() as connection:
            connection.execute(
                text(statement),
                {
                    "binding_id": BINDING_ID,
                    "new_id": uuid4(),
                    "new_manifest_id": uuid4(),
                    "checksum": "d" * 64,
                    "security_id": SECURITY_ID,
                    "snapshot_id": SNAPSHOT_ID,
                    "snapshot_checksum": "b" * 64,
                    "new_binding_checksum": "e" * 64,
                    "as_of": NOW,
                },
            )

    with binding_engine.connect() as connection:
        count = connection.scalar(text("SELECT count(*) FROM ingestion_to_snapshot_bindings"))
    assert count == 1
