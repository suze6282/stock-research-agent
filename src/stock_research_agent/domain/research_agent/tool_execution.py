"""Finite, policy-gated execution of approved read-only Research Tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import NoReturn, Protocol
from uuid import UUID

from pydantic import BaseModel

from stock_research_agent.domain.research_agent.budgets import (
    ResearchBudgetError,
    RunBudgetTracker,
)
from stock_research_agent.domain.research_agent.enums import (
    ObservationStatus,
    ObservationType,
    SyntheticStatus,
    ToolInvocationStatus,
)
from stock_research_agent.domain.research_agent.invocations import (
    complete_invocation,
    start_invocation,
)
from stock_research_agent.domain.research_agent.observations import (
    ResearchObservationBuilder,
)
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchObservationRecord,
    ResearchPolicyRecord,
    ResearchStepRecord,
    ResearchToolInvocationRecord,
    RunBudget,
    ToolExecutionResult,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot
from stock_research_agent.domain.research_agent.tool_context import (
    ResearchToolContextError,
    bind_tool_input,
    validate_output_scope,
)
from stock_research_agent.domain.research_agent.tool_policy import (
    ResearchToolAuthorizationError,
    ResearchToolPolicy,
)
from stock_research_agent.tools.registry import ToolErrorCode, ToolRegistryError


class ToolInvoker(Protocol):
    def execute(
        self,
        name: str,
        version: str,
        payload: Mapping[str, object],
    ) -> BaseModel: ...


class ResearchToolExecutionError(RuntimeError):
    """Safe execution failure with a stable non-echoing code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_BLOCKED_CODES = frozenset(
    {
        "BLOCKED",
        "FUTURE_DATA",
        "INVALID_CITATION",
        "INVALID_QUERY",
        "NOT_FOUND",
        "PERMISSION_DENIED",
        "SCHEMA_ERROR",
    }
)


class ResearchToolExecutor:
    """Compose deterministic guards around one finite Tool Step."""

    def __init__(
        self,
        *,
        registry: ToolInvoker,
        id_factory: Callable[[], UUID],
        clock: Callable[[], datetime],
    ) -> None:
        self._registry = registry
        self._id_factory = id_factory
        self._clock = clock
        self._policy = ResearchToolPolicy()
        self._budgets = RunBudgetTracker()
        self._observations = ResearchObservationBuilder()

    def execute(
        self,
        *,
        context: ControlledRunContext,
        step: ResearchStepRecord,
        catalog: ToolCatalogSnapshot,
        policy: ResearchPolicyRecord,
        budget: RunBudget,
        arguments: Mapping[str, object],
        observation_type: ObservationType,
        synthetic_status: SyntheticStatus,
    ) -> ToolExecutionResult:
        try:
            authorized = self._policy.authorize(context, step, catalog, policy)
            bound = bind_tool_input(context, authorized, arguments)
            current_budget = self._budgets.consume_tool_call(
                budget,
                authorized.tool_name,
            )
        except (
            ResearchBudgetError,
            ResearchToolAuthorizationError,
            ResearchToolContextError,
        ) as error:
            _reject(error.code)

        attempt = 1
        while True:
            started_at = self._clock()
            invocation = start_invocation(
                invocation_id=self._id_factory(),
                context=context,
                step_id=step.id,
                authorized_call=authorized,
                bound_input=bound,
                attempt_number=attempt,
                started_at=started_at,
            )
            try:
                output = self._registry.execute(
                    authorized.tool_name,
                    authorized.tool_version,
                    bound,
                )
                validate_output_scope(context, output)
            except ResearchToolExecutionError as error:
                if error.code == "TRANSIENT_INTERNAL" and attempt == 1:
                    try:
                        current_budget = self._budgets.consume_retry(
                            current_budget,
                            step.definition.step_key,
                        )
                        current_budget = self._budgets.consume_tool_call(
                            current_budget,
                            authorized.tool_name,
                        )
                    except ResearchBudgetError as budget_error:
                        return self._failed_result(
                            invocation,
                            current_budget,
                            budget_error.code,
                        )
                    attempt = 2
                    continue
                return self._failed_result(invocation, current_budget, error.code)
            except ToolRegistryError as error:
                return self._failed_result(
                    invocation,
                    current_budget,
                    _registry_error_code(error.code),
                )
            except ResearchToolContextError as error:
                return self._failed_result(invocation, current_budget, error.code)

            payload = output.model_dump(mode="python")
            observation_status = _observation_status(payload.get("status"))
            completion = complete_invocation(
                invocation=invocation,
                status=ToolInvocationStatus.PASS,
                completed_at=self._clock(),
                output=payload,
            )
            record = _invocation_record(invocation, completion)
            observation = self._observations.build(
                observation_id=self._id_factory(),
                context=context,
                research_step_id=step.id,
                invocation_id=record.id,
                observation_type=observation_type,
                status=observation_status,
                schema_version="observation-v1",
                payload=payload,
                synthetic_status=synthetic_status,
                warnings=(),
                created_at=self._clock(),
            )
            return ToolExecutionResult(
                status=observation_status,
                invocation=record,
                observation=ResearchObservationRecord.model_validate(
                    observation.model_dump(mode="python")
                ),
                budget=current_budget,
                retryable=False,
            )

    def _failed_result(
        self,
        invocation: object,
        budget: RunBudget,
        error_code: str,
    ) -> ToolExecutionResult:
        from stock_research_agent.domain.research_agent.schemas import (
            ResearchToolInvocationWrite,
        )

        if not isinstance(invocation, ResearchToolInvocationWrite):
            _reject("INVALID_INVOCATION")
        blocked = error_code in _BLOCKED_CODES
        invocation_status = ToolInvocationStatus.BLOCKED if blocked else ToolInvocationStatus.FAIL
        completion = complete_invocation(
            invocation=invocation,
            status=invocation_status,
            completed_at=self._clock(),
            error_code=error_code,
            safe_error_message=error_code,
        )
        return ToolExecutionResult(
            status=ObservationStatus.BLOCKED if blocked else ObservationStatus.FAIL,
            invocation=_invocation_record(invocation, completion),
            observation=None,
            budget=budget,
            retryable=False,
        )


def _invocation_record(
    invocation: object,
    completion: object,
) -> ResearchToolInvocationRecord:
    from stock_research_agent.domain.research_agent.schemas import (
        ResearchToolInvocationCompletion,
        ResearchToolInvocationWrite,
    )

    if not isinstance(invocation, ResearchToolInvocationWrite) or not isinstance(
        completion,
        ResearchToolInvocationCompletion,
    ):
        _reject("INVALID_INVOCATION")
    return ResearchToolInvocationRecord.model_validate(
        {
            **invocation.model_dump(mode="python"),
            **completion.model_dump(mode="python"),
        }
    )


def _registry_error_code(code: ToolErrorCode) -> str:
    if code in {ToolErrorCode.INVALID_INPUT, ToolErrorCode.INVALID_OUTPUT}:
        return "SCHEMA_ERROR"
    if code is ToolErrorCode.TOOL_NOT_FOUND:
        return "PERMISSION_DENIED"
    return "TOOL_EXECUTION_FAILED"


def _observation_status(value: object) -> ObservationStatus:
    try:
        return ObservationStatus(str(value))
    except ValueError:
        return ObservationStatus.PASS


def _reject(code: str) -> NoReturn:
    raise ResearchToolExecutionError(code)
