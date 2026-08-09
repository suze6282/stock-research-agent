from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event, text

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import create_session_factory, session_scope
from stock_research_agent.domain.securities.enums import MatchType, ResolutionStatus
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
    XNAS_EXCHANGE_ID,
    XSHG_EXCHANGE_ID,
    SecurityMasterSeedService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TRUNCATE_SQL = text(
    "TRUNCATE TABLE security_aliases, security_identifiers, securities, "
    "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 14, 12, tzinfo=UTC)


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


def _create_test_engine(database_url: str) -> Engine:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=database_url,
    )
    assert settings.database_url is not None
    return create_engine(settings.database_url)


@pytest.fixture(scope="module")
def resolution_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    engine = _create_test_engine(TEST_DATABASE_URL)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)
        command.upgrade(config, "head")
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
def seeded_resolution(resolution_engine: Engine) -> Iterator[SecurityResolutionService]:
    with resolution_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    factory = create_session_factory(resolution_engine)
    with session_scope(factory) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        session.commit()
    session = factory()
    try:
        yield SecurityResolutionService(
            SqlAlchemySecurityMasterRepository(session), clock=FixedClock()
        )
    finally:
        session.close()
        with resolution_engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)


def _insert_security(
    connection: Connection,
    number: int,
    *,
    symbol: str,
    exchange_id: UUID = XNAS_EXCHANGE_ID,
    listing_status: str = "ACTIVE",
) -> tuple[UUID, UUID]:
    issuer_id = UUID(f"90000000-0000-0000-0000-{number:012d}")
    security_id = UUID(f"91000000-0000-0000-0000-{number:012d}")
    country_code = "US" if exchange_id == XNAS_EXCHANGE_ID else "CN"
    currency_code = "USD" if exchange_id == XNAS_EXCHANGE_ID else "CNY"
    connection.execute(
        text(
            "INSERT INTO issuers "
            "(id, legal_name, normalized_legal_name, display_name, "
            "normalized_display_name, country_code, issuer_status) "
            "VALUES (:id, :legal_name, :normalized_name, :display_name, "
            ":normalized_name, :country_code, 'ACTIVE')"
        ),
        {
            "id": issuer_id,
            "legal_name": f"Resolution Test Issuer {number}",
            "normalized_name": f"RESOLUTION TEST ISSUER {number}",
            "display_name": f"Resolution Test {number}",
            "country_code": country_code,
        },
    )
    connection.execute(
        text(
            "INSERT INTO securities "
            "(id, issuer_id, exchange_id, symbol, normalized_symbol, display_name, "
            "security_type, currency_code, listing_status) "
            "VALUES (:id, :issuer_id, :exchange_id, :symbol, :symbol, :display_name, "
            "'COMMON_STOCK', :currency_code, :listing_status)"
        ),
        {
            "id": security_id,
            "issuer_id": issuer_id,
            "exchange_id": exchange_id,
            "symbol": symbol,
            "display_name": f"Resolution Security {number}",
            "currency_code": currency_code,
            "listing_status": listing_status,
        },
    )
    return issuer_id, security_id


def _insert_alias(
    connection: Connection,
    number: int,
    *,
    security_id: UUID,
    alias: str,
    normalized_alias: str,
    alias_type: str = "FORMER_NAME",
    is_active: bool = True,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> None:
    connection.execute(
        text(
            "INSERT INTO security_aliases "
            "(id, security_id, alias, normalized_alias, alias_type, source_name, "
            "valid_from, valid_to, is_active) "
            "VALUES (:id, :security_id, :alias, :normalized_alias, :alias_type, "
            "'resolution integration test', :valid_from, :valid_to, :is_active)"
        ),
        {
            "id": UUID(f"92000000-0000-0000-0000-{number:012d}"),
            "security_id": security_id,
            "alias": alias,
            "normalized_alias": normalized_alias,
            "alias_type": alias_type,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "is_active": is_active,
        },
    )


@pytest.mark.parametrize(
    ("query", "symbol", "match_type"),
    [
        ("601138", "601138", MatchType.EXACT_SYMBOL),
        ("601138.SH", "601138", MatchType.EXACT_EXCHANGE_SYMBOL),
        ("工业富联", "601138", MatchType.EXACT_ALIAS),
        ("富士康工业互联网股份有限公司", "601138", MatchType.EXACT_ALIAS),
        ("MU", "MU", MatchType.EXACT_SYMBOL),
        ("NASDAQ:MU", "MU", MatchType.EXACT_EXCHANGE_SYMBOL),
        ("Micron", "MU", MatchType.EXACT_ALIAS),
        ("Micron Technology", "MU", MatchType.EXACT_ALIAS),
        ("Micron Technology, Inc.", "MU", MatchType.EXACT_ALIAS),
        ("SEC_CIK:723125", "MU", MatchType.EXACT_IDENTIFIER),
    ],
)
def test_seeded_samples_resolve_deterministically(
    seeded_resolution: SecurityResolutionService,
    query: str,
    symbol: str,
    match_type: MatchType,
) -> None:
    result = seeded_resolution.resolve(query)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.match_type is match_type
    assert result.candidates[0].symbol == symbol


def test_prefix_is_only_a_suggestion_and_misspelling_is_not_fuzzy_matched(
    seeded_resolution: SecurityResolutionService,
) -> None:
    prefix = seeded_resolution.resolve("MICR")
    misspelled = seeded_resolution.resolve("Micorn")

    assert prefix.status is ResolutionStatus.AMBIGUOUS
    assert prefix.match_type is MatchType.PREFIX_SUGGESTION
    assert prefix.candidate_count == 1
    assert misspelled.status is ResolutionStatus.NOT_FOUND


def test_same_ticker_across_exchanges_is_ambiguous_but_explicit_exchange_wins(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        _insert_security(connection, 1, symbol="MU", exchange_id=XSHG_EXCHANGE_ID)

    bare = seeded_resolution.resolve("MU")
    explicit = seeded_resolution.resolve("NASDAQ:MU")

    assert bare.status is ResolutionStatus.AMBIGUOUS
    assert [candidate.exchange_mic for candidate in bare.candidates] == ["XNAS", "XSHG"]
    assert explicit.status is ResolutionStatus.RESOLVED
    assert explicit.match_type is MatchType.EXACT_EXCHANGE_SYMBOL
    assert explicit.candidates[0].exchange_mic == "XNAS"


def test_recognized_exchange_missing_symbol_does_not_fall_through_to_alias(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        _insert_alias(
            connection,
            1,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="NASDAQ:XYZ",
            normalized_alias="NASDAQ:XYZ",
        )

    result = seeded_resolution.resolve("NASDAQ:XYZ")

    assert result.status is ResolutionStatus.NOT_FOUND
    assert result.candidate_count == 0


def test_explicit_exchange_lookup_uses_one_postgres_snapshot_statement(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    statements: list[str] = []

    def record_statement(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(resolution_engine, "before_cursor_execute", record_statement)
    try:
        result = seeded_resolution.resolve("NASDAQ:MU")
    finally:
        event.remove(resolution_engine, "before_cursor_execute", record_statement)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.match_type is MatchType.EXACT_EXCHANGE_SYMBOL
    assert len(statements) == 1
    assert "exchange_aliases" in statements[0]
    assert "securities" in statements[0]


def test_shared_current_alias_returns_ambiguous(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        _insert_alias(
            connection,
            1,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="Micron",
            normalized_alias="MICRON",
        )

    result = seeded_resolution.resolve("Micron")

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.match_type is MatchType.EXACT_ALIAS
    assert result.candidate_count == 2


def test_inactive_alias_is_not_resolved_or_suggested(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        _insert_alias(
            connection,
            1,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="Dormant Name",
            normalized_alias="DORMANT NAME",
            is_active=False,
        )

    result = seeded_resolution.resolve("Dormant")

    assert result.status is ResolutionStatus.NOT_FOUND


def test_alias_validity_boundaries_use_the_injected_clock_date(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        _insert_alias(
            connection,
            1,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="Future Alias",
            normalized_alias="FUTURE ALIAS",
            valid_from=date(2026, 7, 15),
        )
        _insert_alias(
            connection,
            2,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="Expired Alias",
            normalized_alias="EXPIRED ALIAS",
            valid_to=date(2026, 7, 13),
        )
        _insert_alias(
            connection,
            3,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="Boundary Alias",
            normalized_alias="BOUNDARY ALIAS",
            valid_from=date(2026, 7, 14),
            valid_to=date(2026, 7, 14),
        )

    assert seeded_resolution.resolve("Future").status is ResolutionStatus.NOT_FOUND
    assert seeded_resolution.resolve("Expired").status is ResolutionStatus.NOT_FOUND
    boundary = seeded_resolution.resolve("Boundary Alias")
    assert boundary.status is ResolutionStatus.RESOLVED
    assert boundary.match_type is MatchType.EXACT_ALIAS


def test_delisted_security_remains_resolvable_with_warning(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        connection.execute(
            text("UPDATE securities SET listing_status = 'DELISTED' WHERE id = :id"),
            {"id": MICRON_SECURITY_ID},
        )

    result = seeded_resolution.resolve("MU")

    assert result.status is ResolutionStatus.RESOLVED
    assert result.candidates[0].listing_status.value == "DELISTED"
    assert any("delisted" in warning.lower() for warning in result.warnings)


def test_prefix_query_escapes_sql_like_wildcards(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        _insert_alias(
            connection,
            1,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="M%MATCH",
            normalized_alias="M%MATCH",
        )

    result = seeded_resolution.resolve("M%M")

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.match_type is MatchType.PREFIX_SUGGESTION
    assert result.candidate_count == 1
    assert result.candidates[0].security_id == INDUSTRIAL_FII_SECURITY_ID


def test_postgres_candidate_query_is_stable_and_bounded_to_ten(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    with resolution_engine.begin() as connection:
        for number in range(1, 12):
            _, security_id = _insert_security(
                connection,
                number,
                symbol=f"PX{number:02d}",
            )
            _insert_alias(
                connection,
                number,
                security_id=security_id,
                alias=f"Bounded Candidate {number:02d}",
                normalized_alias=f"BOUNDED CANDIDATE {number:02d}",
            )

    first = seeded_resolution.resolve("Bounded")
    second = seeded_resolution.resolve("Bounded")

    assert first.status is ResolutionStatus.AMBIGUOUS
    assert first.match_type is MatchType.PREFIX_SUGGESTION
    assert first.candidate_count == 10
    assert [candidate.symbol for candidate in first.candidates] == [
        f"PX{number:02d}" for number in range(1, 11)
    ]
    assert first.model_dump_json() == second.model_dump_json()


def test_exact_alias_is_deduplicated_in_postgres_before_limit(
    seeded_resolution: SecurityResolutionService,
    resolution_engine: Engine,
) -> None:
    alias_types = (
        "SYMBOL",
        "SYMBOL_WITH_EXCHANGE",
        "COMPANY_SHORT_NAME",
        "LEGAL_NAME",
        "ENGLISH_NAME",
        "PROVIDER_SYMBOL",
        "FORMER_NAME",
    )
    with resolution_engine.begin() as connection:
        for number, alias_type in enumerate(alias_types, start=101):
            _insert_alias(
                connection,
                number,
                security_id=MICRON_SECURITY_ID,
                alias="Crowded",
                normalized_alias="CROWDED",
                alias_type=alias_type,
            )
        for number in range(1, 12):
            _, security_id = _insert_security(
                connection,
                number,
                symbol=f"ZZ{number:02d}",
            )
            _insert_alias(
                connection,
                number + 200,
                security_id=security_id,
                alias="Crowded",
                normalized_alias="CROWDED",
            )

    result = seeded_resolution.resolve("Crowded")

    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.match_type is MatchType.EXACT_ALIAS
    assert result.candidate_count == 10
    assert len({candidate.security_id for candidate in result.candidates}) == 10
