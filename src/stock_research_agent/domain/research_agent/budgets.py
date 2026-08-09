"""Hard cumulative execution budgets."""

from decimal import Decimal

from stock_research_agent.domain.research_agent.schemas import RunBudget


class ResearchBudgetError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RunBudgetTracker:
    def consume_step(self, budget: RunBudget) -> RunBudget:
        if budget.consumed_steps >= budget.max_steps:
            raise ResearchBudgetError("STEP_BUDGET_EXCEEDED")
        return budget.model_copy(update={"consumed_steps": budget.consumed_steps + 1})

    def consume_tool_call(self, budget: RunBudget, tool_name: str) -> RunBudget:
        if budget.consumed_tool_calls >= budget.max_tool_calls:
            raise ResearchBudgetError("TOOL_CALL_BUDGET_EXCEEDED")
        calls = dict(budget.calls_per_tool)
        current = calls.get(tool_name, 0)
        if current >= budget.max_calls_per_tool:
            raise ResearchBudgetError("TOOL_LIMIT_EXCEEDED")
        calls[tool_name] = current + 1
        return budget.model_copy(
            update={
                "consumed_tool_calls": budget.consumed_tool_calls + 1,
                "calls_per_tool": calls,
            }
        )

    def consume_retry(self, budget: RunBudget, step_key: str) -> RunBudget:
        retries = dict(budget.retries_per_step)
        current = retries.get(step_key, 0)
        if current >= budget.max_retries_per_step:
            raise ResearchBudgetError("RETRY_BUDGET_EXCEEDED")
        retries[step_key] = current + 1
        return budget.model_copy(update={"retries_per_step": retries})

    def ensure_duration(
        self,
        budget: RunBudget,
        elapsed_seconds: Decimal,
    ) -> None:
        if elapsed_seconds > Decimal(budget.max_duration_seconds):
            raise ResearchBudgetError("DURATION_BUDGET_EXCEEDED")

    def consume_model_tokens(self, budget: RunBudget, token_count: int) -> RunBudget:
        if token_count != 0 or budget.model_token_budget == 0:
            raise ResearchBudgetError("MODEL_BUDGET_UNAVAILABLE")
        return budget
