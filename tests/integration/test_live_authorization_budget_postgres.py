from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from stock_research_agent.db.repositories.live_evidence import (
    reserve_consumption,
    settle_consumption,
)
from stock_research_agent.domain.live_evidence.enums import ConsumptionState
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import (
    ConsumptionReservationRequest,
    ConsumptionSettlementRequest,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@contextmanager
def _isolated_budget_schema() -> Iterator[tuple[Engine, str]]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    engine = create_engine(TEST_DATABASE_URL)
    schema = f"stage10_budget_{uuid4().hex}"
    with engine.begin() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
        assert database_name == "stock_research_test"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".live_authorization_grants (
                    id uuid PRIMARY KEY,
                    request_limit integer NOT NULL CHECK (request_limit > 0),
                    byte_limit integer NOT NULL CHECK (byte_limit > 0)
                )'''
            )
        )
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".live_authorization_consumptions (
                    id uuid PRIMARY KEY,
                    authorization_id uuid NOT NULL REFERENCES
                        "{schema}".live_authorization_grants(id),
                    request_attempt_id uuid NOT NULL,
                    reserved_bytes integer NOT NULL CHECK (reserved_bytes > 0),
                    actual_bytes integer,
                    socket_opened boolean,
                    state varchar(16) NOT NULL,
                    reserved_at timestamptz NOT NULL,
                    settled_at timestamptz,
                    UNIQUE (authorization_id, request_attempt_id)
                )'''
            )
        )
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_request_budget_is_atomic() -> None:
    with _isolated_budget_schema() as (engine, schema):
        authorization_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'INSERT INTO "{schema}".live_authorization_grants '
                    "(id, request_limit, byte_limit) VALUES (:id, 1, 4096)"
                ),
                {"id": authorization_id},
            )

        sessions = sessionmaker(engine, expire_on_commit=False)
        barrier = Barrier(2)

        def reserve_once() -> str:
            try:
                with sessions.begin() as session:
                    session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                    request = ConsumptionReservationRequest(
                        authorization_id=authorization_id,
                        request_attempt_id=uuid4(),
                        reserved_bytes=1024,
                        reserved_at=datetime(2026, 8, 1, 3, 0, tzinfo=UTC),
                    )
                    barrier.wait(timeout=5)
                    reserve_consumption(session, request)
                return "RESERVED"
            except LiveEvidenceValidationError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _index: reserve_once(), range(2)))

        assert sorted(results) == ["AUTH_REQUEST_BUDGET_EXCEEDED", "RESERVED"]
        with Session(engine) as session:
            count = session.scalar(
                text(f'SELECT count(*) FROM "{schema}".live_authorization_consumptions')
            )
        assert count == 1


def test_byte_budget_is_atomic_and_settlement_is_idempotent() -> None:
    with _isolated_budget_schema() as (engine, schema):
        authorization_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'INSERT INTO "{schema}".live_authorization_grants '
                    "(id, request_limit, byte_limit) VALUES (:id, 2, 1500)"
                ),
                {"id": authorization_id},
            )

        sessions = sessionmaker(engine, expire_on_commit=False)
        reserved_at = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)
        with sessions.begin() as session:
            session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            reservations = tuple(
                reserve_consumption(
                    session,
                    ConsumptionReservationRequest(
                        authorization_id=authorization_id,
                        request_attempt_id=uuid4(),
                        reserved_bytes=1000,
                        reserved_at=reserved_at,
                    ),
                )
                for _index in range(2)
            )

        barrier = Barrier(2)

        def settle_once(index: int) -> str:
            settlement = ConsumptionSettlementRequest(
                authorization_id=authorization_id,
                request_attempt_id=reservations[index].request_attempt_id,
                actual_bytes=(1000, 600)[index],
                socket_opened=True,
                state=ConsumptionState.SETTLED,
                settled_at=reserved_at,
            )
            try:
                with sessions.begin() as session:
                    session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                    barrier.wait(timeout=5)
                    record = settle_consumption(session, settlement)
                return record.state.value
            except LiveEvidenceValidationError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(settle_once, range(2)))

        assert sorted(results) == ["AUTH_BYTE_BUDGET_EXCEEDED", "SETTLED"]
        with Session(engine) as session:
            settled_count, actual_total = session.execute(
                text(
                    f'''SELECT count(*) FILTER (WHERE state = 'SETTLED'),
                        coalesce(sum(actual_bytes), 0)
                        FROM "{schema}".live_authorization_consumptions'''
                )
            ).one()
        assert settled_count == 1
        assert actual_total in {600, 1000}

        successful_index = 0 if results[0] == "SETTLED" else 1
        successful = reservations[successful_index]
        repeated = ConsumptionSettlementRequest(
            authorization_id=authorization_id,
            request_attempt_id=successful.request_attempt_id,
            actual_bytes=(1000, 600)[successful_index],
            socket_opened=True,
            state=ConsumptionState.SETTLED,
            settled_at=reserved_at,
        )
        with sessions.begin() as session:
            session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            assert settle_consumption(session, repeated).actual_bytes == repeated.actual_bytes

        with pytest.raises(LiveEvidenceValidationError) as exc_info:
            with sessions.begin() as session:
                session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                settle_consumption(
                    session,
                    repeated.model_copy(update={"actual_bytes": repeated.actual_bytes - 1}),
                )
        assert exc_info.value.code == "AUTH_SETTLEMENT_CONFLICT"
