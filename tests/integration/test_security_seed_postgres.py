from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.models import (
    Exchange,
    ExchangeAlias,
    Issuer,
    IssuerIdentifier,
    Market,
    Security,
    SecurityAlias,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import create_session_factory, session_scope
from stock_research_agent.domain.securities.exceptions import SeedConflictError
from stock_research_agent.domain.securities.seed import (
    SECURITY_MASTER_SEED_V0,
    SecurityMasterSeedService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TRUNCATE_SQL = text(
    "TRUNCATE TABLE security_aliases, security_identifiers, securities, "
    "issuer_identifiers, issuers, exchange_aliases, exchanges, markets CASCADE"
)


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


def test_non_test_database_is_rejected_before_seed_engine_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine_creation_attempted = False

    def fail_if_called(_database_url: str) -> Engine:
        nonlocal engine_creation_attempted
        engine_creation_attempted = True
        raise AssertionError("create_engine must not run for a non-test database")

    monkeypatch.setattr(sys.modules[__name__], "create_engine", fail_if_called)
    with pytest.raises(ValueError, match="database name must end with '_test'"):
        _create_test_engine(
            "postgresql+psycopg://stock_user:password@127.0.0.1:55432/stock_research"
        )
    assert engine_creation_attempted is False


@pytest.fixture(scope="module")
def seed_engine() -> Iterator[Engine]:
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
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env


@pytest.fixture
def clean_seed_engine(seed_engine: Engine) -> Iterator[Engine]:
    with seed_engine.begin() as connection:
        connection.execute(TRUNCATE_SQL)
    try:
        yield seed_engine
    finally:
        with seed_engine.begin() as connection:
            connection.execute(TRUNCATE_SQL)


def _run_seed(engine: Engine):
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        result = SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        session.commit()
        return result


def _manifest_record_count() -> int:
    manifest = SECURITY_MASTER_SEED_V0
    return sum(
        len(records)
        for records in (
            manifest.markets,
            manifest.exchanges,
            manifest.exchange_aliases,
            manifest.issuers,
            manifest.issuer_identifiers,
            manifest.securities,
            manifest.security_aliases,
        )
    )


def test_first_and_second_seed_are_idempotent(clean_seed_engine: Engine) -> None:
    expected_count = _manifest_record_count()

    first = _run_seed(clean_seed_engine)
    second = _run_seed(clean_seed_engine)

    assert (first.inserted_count, first.existing_count) == (expected_count, 0)
    assert (second.inserted_count, second.existing_count) == (0, expected_count)
    with clean_seed_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Security)) == 2
        assert connection.scalar(select(func.count()).select_from(Issuer)) == 2
        assert connection.scalar(select(func.count()).select_from(IssuerIdentifier)) == 1


def test_seed_persists_only_confirmed_sample_values(clean_seed_engine: Engine) -> None:
    _run_seed(clean_seed_engine)

    with clean_seed_engine.connect() as connection:
        securities = connection.execute(
            select(Security.symbol, Security.listing_status).order_by(Security.symbol)
        ).all()
        identifiers = connection.execute(
            select(IssuerIdentifier.scheme, IssuerIdentifier.normalized_value)
        ).all()

    assert securities == [("601138", "UNKNOWN"), ("MU", "UNKNOWN")]
    assert identifiers == [("SEC_CIK", "0000723125")]


def test_incompatible_existing_data_fails_without_partial_seed_write(
    clean_seed_engine: Engine,
) -> None:
    _run_seed(clean_seed_engine)
    with clean_seed_engine.begin() as connection:
        connection.execute(text("DELETE FROM exchange_aliases WHERE normalized_alias = 'SSE'"))
        connection.execute(
            text("UPDATE security_aliases SET alias = 'Tampered' WHERE normalized_alias = 'MICRON'")
        )

    factory = create_session_factory(clean_seed_engine)
    with pytest.raises(SeedConflictError):
        with session_scope(factory) as session:
            SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
            session.commit()

    with clean_seed_engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(ExchangeAlias)
                .where(ExchangeAlias.normalized_alias == "SSE")
            )
            == 0
        )
        assert (
            connection.scalar(
                select(SecurityAlias.alias).where(SecurityAlias.normalized_alias == "MICRON")
            )
            == "Tampered"
        )


def test_seed_preserves_unrelated_user_rows(clean_seed_engine: Engine) -> None:
    _run_seed(clean_seed_engine)
    user_issuer_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    with clean_seed_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO issuers
                    (id, legal_name, normalized_legal_name, display_name,
                     normalized_display_name, country_code, issuer_status)
                VALUES (:id, 'User Company', 'USER COMPANY', 'User Company',
                        'USER COMPANY', 'US', 'UNKNOWN')
                """
            ),
            {"id": user_issuer_id},
        )

    _run_seed(clean_seed_engine)

    with clean_seed_engine.connect() as connection:
        assert connection.scalar(select(Issuer.legal_name).where(Issuer.id == user_issuer_id)) == (
            "User Company"
        )


def test_concurrent_seed_attempts_serialize_without_duplicates(clean_seed_engine: Engine) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: _run_seed(clean_seed_engine), range(2)))

    expected_count = _manifest_record_count()
    assert sorted((result.inserted_count, result.existing_count) for result in results) == [
        (0, expected_count),
        (expected_count, 0),
    ]
    with clean_seed_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Market)) == 2
        assert connection.scalar(select(func.count()).select_from(Exchange)) == 2
        assert connection.scalar(select(func.count()).select_from(Security)) == 2


@pytest.mark.parametrize("collision_kind", ["uuid", "natural", "both"])
def test_seed_rejects_uuid_and_natural_key_collisions_without_partial_writes(
    clean_seed_engine: Engine,
    collision_kind: str,
) -> None:
    seed_market_id = SECURITY_MASTER_SEED_V0.markets[0].id
    with clean_seed_engine.begin() as connection:
        if collision_kind in {"uuid", "both"}:
            connection.execute(
                text(
                    """
                    INSERT INTO markets
                        (id, code, name, country_code, default_currency_code, status)
                    VALUES (:id, 'OTHER_MARKET', 'Other', 'CN', 'CNY', 'UNKNOWN')
                    """
                ),
                {"id": seed_market_id},
            )
        if collision_kind in {"natural", "both"}:
            connection.execute(
                text(
                    """
                    INSERT INTO markets
                        (id, code, name, country_code, default_currency_code, status)
                    VALUES (:id, 'CN_A', 'Collision', 'CN', 'CNY', 'UNKNOWN')
                    """
                ),
                {"id": UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")},
            )

    factory = create_session_factory(clean_seed_engine)
    with pytest.raises(SeedConflictError):
        with session_scope(factory) as session:
            SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
            session.commit()

    expected_existing = 2 if collision_kind == "both" else 1
    with clean_seed_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Market)) == expected_existing
        assert (
            connection.scalar(
                select(func.count()).select_from(Market).where(Market.code == "US_EQUITY")
            )
            == 0
        )
