from pathlib import Path
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers.enums import ProviderRunStatus
from stock_research_agent.domain.providers.sync import (
    ProviderRunContext,
    ProviderRunStateMachine,
)

TERMINAL = {
    ProviderRunStatus.COMPLETED,
    ProviderRunStatus.PARTIAL,
    ProviderRunStatus.BLOCKED,
    ProviderRunStatus.FAILED,
    ProviderRunStatus.CANCELLED,
}


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ProviderRunStatus.PLANNED, ProviderRunStatus.QUEUED),
        (ProviderRunStatus.QUEUED, ProviderRunStatus.RUNNING),
        (ProviderRunStatus.RUNNING, ProviderRunStatus.PAUSED),
        (ProviderRunStatus.PAUSED, ProviderRunStatus.RUNNING),
        (ProviderRunStatus.RUNNING, ProviderRunStatus.COMPLETED),
        (ProviderRunStatus.RUNNING, ProviderRunStatus.PARTIAL),
        (ProviderRunStatus.QUEUED, ProviderRunStatus.BLOCKED),
    ],
)
def test_state_machine_allows_only_reviewed_transitions(
    current: ProviderRunStatus,
    target: ProviderRunStatus,
) -> None:
    assert ProviderRunStateMachine.transition(current, target) is target


@pytest.mark.parametrize("terminal", sorted(TERMINAL, key=str))
def test_terminal_run_cannot_transition_or_rewrite_same_status(
    terminal: ProviderRunStatus,
) -> None:
    with pytest.raises(ValueError, match="PROVIDER_RUN_TERMINAL"):
        ProviderRunStateMachine.transition(terminal, ProviderRunStatus.RUNNING)
    with pytest.raises(ValueError, match="PROVIDER_RUN_TERMINAL"):
        ProviderRunStateMachine.transition(terminal, terminal)


def test_invalid_recovery_and_budget_context_swap_are_rejected() -> None:
    with pytest.raises(ValueError, match="PROVIDER_RUN_TRANSITION_FORBIDDEN"):
        ProviderRunStateMachine.transition(
            ProviderRunStatus.PAUSED,
            ProviderRunStatus.PLANNED,
        )

    original = ProviderRunContext(
        sync_request_id=uuid4(),
        sync_plan_id=uuid4(),
        policy_id=uuid4(),
        license_policy_id=uuid4(),
        max_requests=10,
        max_bytes=1024,
    )
    changed = original.model_copy(update={"max_requests": 20})
    with pytest.raises(ValueError, match="PROVIDER_RUN_CONTEXT_IMMUTABLE"):
        ProviderRunStateMachine.validate_context_unchanged(original, changed)


def test_migration_transition_vocabulary_matches_domain_map() -> None:
    migration = Path("migrations/versions/0008_create_production_data_providers.py").read_text(
        encoding="utf-8"
    )
    for current, targets in ProviderRunStateMachine.allowed_transitions().items():
        assert current.value in migration
        for target in targets:
            assert target.value in migration
