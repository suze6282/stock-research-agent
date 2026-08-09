from __future__ import annotations

import importlib
import importlib.util
from decimal import Decimal

import pytest

from stock_research_agent.domain.research_agent.schemas import RunBudget

MODULE = "stock_research_agent.domain.research_agent.budgets"


def _budgets() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _budget(**updates: object) -> RunBudget:
    values = {
        "max_steps": 2,
        "max_tool_calls": 2,
        "max_calls_per_tool": 1,
        "max_retries_per_step": 1,
        "max_duration_seconds": 10,
        "model_token_budget": 0,
        "consumed_steps": 0,
        "consumed_tool_calls": 0,
        "consumed_model_tokens": 0,
        "elapsed_seconds": Decimal("0"),
        "calls_per_tool": {},
        "retries_per_step": {},
    }
    values.update(updates)
    return RunBudget.model_validate(values)


def test_budget_consumption_is_immutable_and_cumulative() -> None:
    tracker = _budgets().RunBudgetTracker()
    original = _budget()

    after_step = tracker.consume_step(original)
    after_call = tracker.consume_tool_call(after_step, "get_data_snapshot")
    after_retry = tracker.consume_retry(after_call, "load_snapshot")

    assert original.consumed_steps == 0
    assert after_retry.consumed_steps == 1
    assert after_retry.consumed_tool_calls == 1
    assert after_retry.calls_per_tool == {"get_data_snapshot": 1}
    assert after_retry.retries_per_step == {"load_snapshot": 1}
    assert after_retry.consumed_model_tokens == 0


@pytest.mark.parametrize(
    ("method", "budget", "args", "code"),
    [
        ("consume_step", _budget(consumed_steps=2), (), "STEP_BUDGET_EXCEEDED"),
        (
            "consume_tool_call",
            _budget(consumed_tool_calls=2),
            ("get_data_snapshot",),
            "TOOL_CALL_BUDGET_EXCEEDED",
        ),
        (
            "consume_tool_call",
            _budget(calls_per_tool={"get_data_snapshot": 1}),
            ("get_data_snapshot",),
            "TOOL_LIMIT_EXCEEDED",
        ),
        (
            "consume_retry",
            _budget(retries_per_step={"load_snapshot": 1}),
            ("load_snapshot",),
            "RETRY_BUDGET_EXCEEDED",
        ),
        (
            "ensure_duration",
            _budget(),
            (Decimal("10.0001"),),
            "DURATION_BUDGET_EXCEEDED",
        ),
    ],
)
def test_every_hard_limit_fails_closed(
    method: str,
    budget: RunBudget,
    args: tuple[object, ...],
    code: str,
) -> None:
    budgets = _budgets()
    tracker = budgets.RunBudgetTracker()

    with pytest.raises(budgets.ResearchBudgetError) as raised:
        getattr(tracker, method)(budget, *args)

    assert raised.value.code == code
