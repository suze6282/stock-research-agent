from uuid import uuid4

import pytest

from stock_research_agent.domain.providers.sync import (
    CheckpointAdvance,
    CheckpointScope,
)


def test_checkpoint_scope_is_exact_and_checksum_is_stable() -> None:
    provider_id = uuid4()
    capability_id = uuid4()
    first = CheckpointScope(
        provider_definition_id=provider_id,
        provider_capability_id=capability_id,
        universe_code="US_EQUITY",
        security_id=None,
        scope_version="1.0.0",
    )
    second = CheckpointScope(
        provider_definition_id=provider_id,
        provider_capability_id=capability_id,
        universe_code="US_EQUITY",
        security_id=None,
        scope_version="1.0.0",
    )

    assert first.checksum() == second.checksum()
    assert len(first.checksum()) == 64


def test_checkpoint_scope_rejects_ambiguous_or_missing_identity() -> None:
    common = {
        "provider_definition_id": uuid4(),
        "provider_capability_id": uuid4(),
        "scope_version": "1.0.0",
    }
    with pytest.raises(ValueError, match="exactly one"):
        CheckpointScope(**common, universe_code=None, security_id=None)
    with pytest.raises(ValueError, match="exactly one"):
        CheckpointScope(
            **common,
            universe_code="US_EQUITY",
            security_id=uuid4(),
        )


def test_checkpoint_advance_requires_a_finite_expected_revision() -> None:
    scope = CheckpointScope(
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        universe_code="US_EQUITY",
        security_id=None,
        scope_version="1.0.0",
    )
    with pytest.raises(ValueError):
        CheckpointAdvance(
            scope=scope,
            expected_revision=-1,
            watermark={"cursor": "one"},
        )
