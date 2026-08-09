from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.providers import (
    ProviderRepositoryConflict,
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderProductionStatus,
)
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite
from stock_research_agent.domain.providers.sync import (
    CheckpointAdvance,
    CheckpointScope,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    return any("tests/integration" in value.replace("\\", "/").casefold() for value in sys.argv[1:])


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for checkpoint tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def test_concurrent_checkpoint_compare_and_swap_has_one_winner() -> None:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_DATABASE_URL)
    suffix = datetime.now(tz=UTC).strftime("%H%M%S%f")
    with Session(engine) as session, session.begin():
        definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
            ProviderDefinitionWrite(
                code=f"CAS_{suffix}",
                definition_version="1.0.0",
                adapter_version="1.0.0",
                display_name="CAS Test",
                data_domain="MARKET_DATA",
                definition_status=ProviderDefinitionStatus.ACTIVE,
                production_status=ProviderProductionStatus.TEST_ONLY,
                official_domains=("example.com",),
                policy_version="1.0.0",
                license_policy_version="1.0.0",
                credential_reference_id=None,
                source_register_version="1.0.0",
            )
        )
        capability = SqlAlchemyProviderGovernanceRepository(session).add_capability(
            ProviderCapabilityWrite(
                provider_definition_id=definition.id,
                code="CHECKPOINT_TEST",
                capability_version="1.0.0",
                status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
                data_domain="MARKET_DATA",
                market_codes=("US_EQUITY",),
                security_types=("COMMON_STOCK",),
                operations=("READ_OFFLINE_FIXTURE",),
            )
        )
        scope = CheckpointScope(
            provider_definition_id=definition.id,
            provider_capability_id=capability.id,
            universe_code="US_EQUITY",
            security_id=None,
            scope_version="1.0.0",
        )
        created = SqlAlchemyProviderSyncRepository(session).compare_and_swap_checkpoint(
            CheckpointAdvance(
                scope=scope,
                expected_revision=0,
                watermark={"cursor": "initial"},
            )
        )
        assert created.revision == 0

    barrier = Barrier(2)

    def advance(cursor: str) -> str:
        with Session(engine) as session, session.begin():
            barrier.wait()
            try:
                result = SqlAlchemyProviderSyncRepository(session).compare_and_swap_checkpoint(
                    CheckpointAdvance(
                        scope=scope,
                        expected_revision=0,
                        watermark={"cursor": cursor},
                    )
                )
            except ProviderRepositoryConflict:
                return "CONFLICT"
            return f"REVISION_{result.revision}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(advance, ("one", "two")))

    assert sorted(results) == ["CONFLICT", "REVISION_1"]
    with Session(engine) as session:
        final = SqlAlchemyProviderSyncRepository(session).get_checkpoint(scope)
        assert final is not None
        assert final.revision == 1
        assert final.watermark in ({"cursor": "one"}, {"cursor": "two"})
    engine.dispose()
