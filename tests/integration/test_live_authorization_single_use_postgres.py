from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

from stock_research_agent.db.repositories.live_evidence import consume_authorization
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@contextmanager
def _isolated_event_schema() -> Iterator[tuple[Engine, str, UUID]]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    engine = create_engine(TEST_DATABASE_URL)
    schema = f"stage10_single_{uuid4().hex}"
    authorization_id = uuid4()
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "stock_research_test"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".live_authorization_grants (
                    id uuid PRIMARY KEY
                )'''
            )
        )
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".live_authorization_events (
                    id uuid PRIMARY KEY,
                    authorization_id uuid NOT NULL REFERENCES
                        "{schema}".live_authorization_grants(id),
                    sequence integer NOT NULL,
                    event_type varchar(16) NOT NULL,
                    UNIQUE (authorization_id, sequence)
                )'''
            )
        )
        connection.execute(
            text(f'INSERT INTO "{schema}".live_authorization_grants (id) VALUES (:id)'),
            {"id": authorization_id},
        )
        connection.execute(
            text(
                f'''INSERT INTO "{schema}".live_authorization_events
                    (id, authorization_id, sequence, event_type)
                    VALUES (:first, :authorization_id, 1, 'APPROVE'),
                           (:second, :authorization_id, 2, 'ACTIVATE')'''
            ),
            {"first": uuid4(), "second": uuid4(), "authorization_id": authorization_id},
        )
    try:
        yield engine, schema, authorization_id
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_grant_can_be_consumed_only_once_atomically() -> None:
    with _isolated_event_schema() as (engine, schema, authorization_id):
        sessions = sessionmaker(engine, expire_on_commit=False)
        barrier = Barrier(2)

        def consume_once() -> str:
            try:
                with sessions.begin() as session:
                    session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                    barrier.wait(timeout=5)
                    return consume_authorization(session, authorization_id).value
            except LiveEvidenceValidationError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _index: consume_once(), range(2)))

        assert sorted(results) == ["AUTHORIZATION_ALREADY_CONSUMED", "CONSUMED"]
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    f'''SELECT sequence, event_type
                        FROM "{schema}".live_authorization_events
                        WHERE authorization_id = :authorization_id
                        ORDER BY sequence'''
                ),
                {"authorization_id": authorization_id},
            ).all()
        assert rows == [(1, "APPROVE"), (2, "ACTIVATE"), (3, "CONSUME")]
