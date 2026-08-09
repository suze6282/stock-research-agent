"""Explicit CLI for controlled, offline Research Agent operations."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import typer
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from stock_research_agent.config import Settings
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.financials import SqlAlchemyFinancialRepository
from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.db.repositories.research_agent import (
    SqlAlchemyResearchAgentRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.domain.research_agent.application import (
    DeterministicResearchExecutionService,
)
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchRunStatus,
    ResearchSection,
    ResearchStepStatus,
    ResearchType,
)
from stock_research_agent.domain.research_agent.idempotency import (
    research_run_idempotency_key,
)
from stock_research_agent.domain.research_agent.plan_validation import ResearchPlanValidator
from stock_research_agent.domain.research_agent.planning import (
    PLANNER_VERSION,
    DeterministicTemplatePlanner,
)
from stock_research_agent.domain.research_agent.policies import (
    CONTROLLED_OFFLINE_POLICY_VERSION,
    ResearchPolicySeedService,
    ResearchPolicyService,
)
from stock_research_agent.domain.research_agent.queries import (
    ResearchAgentQueryService,
    ResearchQueryNotFoundError,
)
from stock_research_agent.domain.research_agent.requests import ResearchRequestService
from stock_research_agent.domain.research_agent.resume import ResearchRunControlService
from stock_research_agent.domain.research_agent.schemas import (
    PageRequest,
    ResearchAgentRunRecord,
    ResearchPlanWrite,
    ResearchPolicyRecord,
    ResearchRequestCreate,
    ResearchRequestRecord,
    ResearchRunWrite,
    ResearchStepWrite,
    RunBudget,
)
from stock_research_agent.domain.research_agent.state_machine import ResearchRunStateMachine
from stock_research_agent.domain.research_agent.tool_catalog import (
    ToolCatalogSnapshot,
    build_tool_catalog_snapshot,
)
from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.tools.registry import (
    create_financial_tool_registry,
    create_rag_tool_registry,
    create_tool_metadata_registry,
    create_tool_registry,
)

EXIT_PARTIAL = 2
EXIT_BLOCKED = 3
EXIT_INVALID_OR_FAILED = 4

agent_app = typer.Typer(
    help="Explicitly plan, execute, control, or read deterministic research runs.",
    no_args_is_help=True,
)
policy_app = typer.Typer(help="Manage explicit versioned Research Policies.", no_args_is_help=True)
catalog_app = typer.Typer(help="Inspect the fixed read-only Tool Catalog.", no_args_is_help=True)
agent_app.add_typer(policy_app, name="policy")
agent_app.add_typer(catalog_app, name="tools")
settings_factory: Callable[[], Settings] = Settings


@dataclass(frozen=True, slots=True)
class _Resources:
    session: Session
    research: SqlAlchemyResearchAgentRepository
    data: SqlAlchemyDataAccessRepository
    financials: SqlAlchemyFinancialRepository
    knowledge: SqlAlchemyKnowledgeRepository
    securities: SqlAlchemySecurityMasterRepository


@contextmanager
def _resources() -> Iterator[_Resources]:
    engine: Engine | None = None
    try:
        source = settings_factory()
        settings = Settings.model_validate(source.model_dump(warnings=False))
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            yield _Resources(
                session=session,
                research=SqlAlchemyResearchAgentRepository(session),
                data=SqlAlchemyDataAccessRepository(session),
                financials=SqlAlchemyFinancialRepository(session),
                knowledge=SqlAlchemyKnowledgeRepository(session),
                securities=SqlAlchemySecurityMasterRepository(session),
            )
    finally:
        if engine is not None:
            engine.dispose()


def _now() -> datetime:
    return datetime.now(UTC)


def _catalog() -> ToolCatalogSnapshot:
    return build_tool_catalog_snapshot(create_tool_metadata_registry())


def _render(value: object, json_output: bool) -> None:
    payload: object
    if isinstance(value, BaseModel):
        if json_output:
            typer.echo(value.model_dump_json(indent=2))
            return
        payload = value.model_dump(mode="json")
    elif is_dataclass(value) and not isinstance(value, type):
        payload = asdict(value)
    else:
        payload = value
    if json_output:
        typer.echo(json.dumps(payload, default=str, ensure_ascii=False, indent=2))
    elif isinstance(payload, dict):
        for key, item in payload.items():
            typer.echo(f"{key}: {item}")
    else:
        typer.echo(str(payload))


def _state_machine(resources: _Resources) -> ResearchRunStateMachine:
    def next_sequence(run_id: UUID) -> int:
        return (
            resources.research.list_event_views(
                run_id,
                PageRequest(limit=1, offset=0),
            ).total
            + 1
        )

    return ResearchRunStateMachine(
        resources.research,
        event_id_factory=uuid4,
        next_sequence=next_sequence,
        now=_now,
    )


def _budget(policy: ResearchPolicyRecord) -> RunBudget:
    return RunBudget(
        max_steps=policy.max_steps,
        max_tool_calls=policy.max_tool_calls,
        max_calls_per_tool=policy.max_calls_per_tool,
        max_retries_per_step=policy.max_retries_per_step,
        max_duration_seconds=policy.max_duration_seconds,
        model_token_budget=0,
        consumed_steps=0,
        consumed_tool_calls=0,
        consumed_model_tokens=0,
        elapsed_seconds=Decimal("0"),
    )


def _create_planned_run(
    resources: _Resources,
    command: ResearchRequestCreate,
) -> tuple[
    ResearchAgentRunRecord,
    ResearchRequestRecord,
    ResearchPolicyRecord,
    ToolCatalogSnapshot,
]:
    policies = ResearchPolicyService(resources.research)
    catalog = _catalog()
    request = ResearchRequestService(
        resolver=SecurityResolutionService(resources.securities),
        snapshots=resources.data,
        policies=policies,
        catalog_provider=lambda: catalog,
        repository=resources.research,
        id_factory=uuid4,
        now=_now,
    ).create(command)
    policy = policies.require(command.policy_version)
    idempotency_key = research_run_idempotency_key(
        normalized_request=request.normalized_security_query,
        security_id=request.resolved_security_id,
        snapshot_id=request.snapshot_id,
        research_as_of_time=request.research_as_of_time,
        research_type=request.research_type,
        requested_sections=request.requested_sections,
        policy_version=request.policy_version,
        planner_version=request.planner_version,
        tool_catalog_checksum=request.tool_catalog_checksum,
    )
    now = _now()
    run = resources.research.create_run(
        ResearchRunWrite(
            id=uuid4(),
            request_id=request.id,
            security_id=request.resolved_security_id,
            snapshot_id=request.snapshot_id,
            research_as_of_time=request.research_as_of_time,
            status=ResearchRunStatus.CREATED,
            policy_version=request.policy_version,
            planner_version=request.planner_version,
            tool_catalog_version=request.tool_catalog_version,
            tool_catalog_checksum=request.tool_catalog_checksum,
            idempotency_key=idempotency_key,
            budget=_budget(policy),
            created_at=now,
            updated_at=now,
        )
    )
    if run.status is not ResearchRunStatus.CREATED:
        original_request = resources.research.get_request(run.request_id)
        if original_request is None:
            raise LookupError("RESEARCH_REQUEST_NOT_FOUND")
        return run, original_request, policy, catalog
    state = _state_machine(resources)
    state.transition(run.id, ResearchRunStatus.PLANNING, "PLAN_STARTED")
    draft = DeterministicTemplatePlanner().create_plan(request, policy, catalog)
    validated = ResearchPlanValidator().validate(draft, policy, catalog)
    plan_id = uuid4()
    created_at = _now()
    resources.research.add_plan(
        ResearchPlanWrite(
            **validated.model_dump(mode="python"),
            id=plan_id,
            run_id=run.id,
            created_at=created_at,
        )
    )
    resources.research.add_steps(
        tuple(
            ResearchStepWrite(
                id=uuid4(),
                run_id=run.id,
                plan_id=plan_id,
                definition=definition,
                status=ResearchStepStatus.PENDING,
                created_at=created_at,
            )
            for definition in validated.steps
        )
    )
    planned = state.transition(run.id, ResearchRunStatus.PLANNED, "PLAN_VALIDATED")
    return planned, request, policy, catalog


def _execution_service(
    resources: _Resources,
) -> DeterministicResearchExecutionService:
    return DeterministicResearchExecutionService(
        repository=resources.research,
        state_machine=_state_machine(resources),
        registries=(
            create_tool_registry(DataAccessQueryService(resources.data)),
            create_financial_tool_registry(FinancialQueryService(resources.financials)),
            create_rag_tool_registry(PrecomputedRetrievalQueryService(resources.knowledge)),
        ),
        id_factory=uuid4,
        clock=_now,
    )


def _command(
    security_query: str,
    research_type: ResearchType,
    snapshot_id: UUID,
    as_of: datetime,
    policy_version: str,
) -> ResearchRequestCreate:
    sections = (
        ResearchSection.SECURITY_IDENTITY,
        ResearchSection.DATA_QUALITY,
        ResearchSection.LIMITATIONS,
    )
    return ResearchRequestCreate(
        security_query=security_query,
        research_type=research_type,
        snapshot_id=snapshot_id,
        research_as_of_time=as_of,
        requested_sections=sections,
        policy_version=policy_version,
        planner_version=PLANNER_VERSION,
        research_mode=ResearchMode.REAL_RESEARCH,
    )


def _fail(message: str, code: int = EXIT_INVALID_OR_FAILED) -> None:
    typer.echo(message)
    raise typer.Exit(code=code)


@policy_app.command("seed-v1")
def policy_seed_v1(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explicitly seed the immutable controlled-offline-v1 Policy."""
    try:
        with _resources() as resources:
            result = ResearchPolicySeedService(resources.research).seed_v1()
            resources.session.commit()
    except Exception:
        _fail("Research Policy seed failed")
    _render(
        {
            "version": result.policy.version,
            "checksum": result.policy.checksum,
            "created": result.created,
        },
        json_output,
    )


@policy_app.command("list")
def policy_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List the approved default Policy when it is persisted."""
    try:
        with _resources() as resources:
            policy = resources.research.get_policy(CONTROLLED_OFFLINE_POLICY_VERSION)
    except Exception:
        _fail("Research Policy query failed")
    _render([] if policy is None else [policy.model_dump(mode="json")], json_output)


@catalog_app.command("list")
def tools_list(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List the exact 22-Tool production execution catalog."""
    _render(_catalog(), json_output)


def _plan_or_run(
    *,
    execute: bool,
    security_query: str,
    research_type: ResearchType,
    snapshot_id: UUID,
    as_of: datetime,
    policy_version: str,
    json_output: bool,
) -> None:
    try:
        with _resources() as resources:
            run, request, policy, catalog = _create_planned_run(
                resources,
                _command(security_query, research_type, snapshot_id, as_of, policy_version),
            )
            if execute and run.status is ResearchRunStatus.PLANNED:
                run, _package = _execution_service(resources).execute(
                    run=run,
                    request=request,
                    policy=policy,
                    catalog=catalog,
                )
            resources.session.commit()
    except Exception:
        _fail("Research request invalid or execution failed")
    _render(run, json_output)
    if run.status is ResearchRunStatus.PARTIAL:
        raise typer.Exit(code=EXIT_PARTIAL)
    if run.status is ResearchRunStatus.BLOCKED:
        raise typer.Exit(code=EXIT_BLOCKED)


@agent_app.command("plan")
def plan(
    security_query: Annotated[str, typer.Argument()],
    research_type: Annotated[ResearchType, typer.Option("--type")],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    as_of: Annotated[datetime, typer.Option("--as-of")],
    policy_version: Annotated[str, typer.Option("--policy")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Persist a finite deterministic Plan with fully explicit context."""
    _plan_or_run(
        execute=False,
        security_query=security_query,
        research_type=research_type,
        snapshot_id=snapshot_id,
        as_of=as_of,
        policy_version=policy_version,
        json_output=json_output,
    )


@agent_app.command("run")
def run(
    security_query: Annotated[str, typer.Argument()],
    research_type: Annotated[ResearchType, typer.Option("--type")],
    snapshot_id: Annotated[UUID, typer.Option("--snapshot")],
    as_of: Annotated[datetime, typer.Option("--as-of")],
    policy_version: Annotated[str, typer.Option("--policy")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Execute only persisted offline inputs with fully explicit context."""
    _plan_or_run(
        execute=True,
        security_query=security_query,
        research_type=research_type,
        snapshot_id=snapshot_id,
        as_of=as_of,
        policy_version=policy_version,
        json_output=json_output,
    )


def _control(run_id: UUID, target: str, json_output: bool) -> None:
    try:
        with _resources() as resources:
            current = resources.research.get_run(run_id)
            if current is None:
                raise ResearchQueryNotFoundError
            policy = ResearchPolicyService(resources.research).require(current.policy_version)
            catalog = _catalog()

            def snapshot_validator(
                security_id: UUID,
                snapshot_id: UUID,
                research_as_of_time: object,
            ) -> bool:
                snapshot = resources.data.get_snapshot(snapshot_id)
                return (
                    snapshot is not None
                    and snapshot.status == "COMPLETE"
                    and snapshot.security_id == security_id
                    and isinstance(research_as_of_time, datetime)
                    and snapshot.research_as_of_time <= research_as_of_time
                )

            control = ResearchRunControlService(
                run_repository=resources.research,
                planning_repository=resources.research,
                state_machine=_state_machine(resources),
                snapshot_validator=snapshot_validator,
            )
            if target == "pause":
                result = control.pause(run_id)
            elif target == "cancel":
                result = control.cancel(run_id)
            else:
                resumed = control.resume(run_id, policy, catalog)
                request = resources.research.get_request(current.request_id)
                if request is None:
                    raise LookupError("RESEARCH_REQUEST_NOT_FOUND")
                result, _package = _execution_service(resources).execute(
                    run=resumed.run,
                    request=request,
                    policy=policy,
                    catalog=catalog,
                )
            resources.session.commit()
    except ResearchQueryNotFoundError:
        _fail("Research resource not found")
    except Exception:
        _fail("Research run control failed")
    _render(result, json_output)


@agent_app.command("pause")
def pause(
    run_id: Annotated[UUID, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _control(run_id, "pause", json_output)


@agent_app.command("resume")
def resume(
    run_id: Annotated[UUID, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _control(run_id, "resume", json_output)


@agent_app.command("cancel")
def cancel(
    run_id: Annotated[UUID, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    _control(run_id, "cancel", json_output)


def _read(
    method: str,
    run_id: UUID,
    json_output: bool,
    limit: int = 50,
    offset: int = 0,
) -> None:
    try:
        with _resources() as resources:
            service = ResearchAgentQueryService(resources.research)
            if method.startswith("list_"):
                value = getattr(service, method)(run_id, PageRequest(limit=limit, offset=offset))
            else:
                value = getattr(service, method)(run_id)
    except ResearchQueryNotFoundError:
        _fail("Research resource not found")
    except Exception:
        _fail("Research query failed")
    _render(value, json_output)


def _read_command(method: str) -> Callable[..., None]:
    def command(
        run_id: Annotated[UUID, typer.Argument()],
        json_output: Annotated[bool, typer.Option("--json")] = False,
        limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 50,
        offset: Annotated[int, typer.Option("--offset", min=0, max=10_000)] = 0,
    ) -> None:
        _read(method, run_id, json_output, limit, offset)

    return command


agent_app.command("run-show")(_read_command("get_run"))
agent_app.command("plan-show")(_read_command("get_plan"))
agent_app.command("steps")(_read_command("list_steps"))
agent_app.command("tool-calls")(_read_command("list_invocations"))
agent_app.command("evidence")(_read_command("list_evidence"))
agent_app.command("claims")(_read_command("list_claims"))
agent_app.command("package")(_read_command("get_package"))
agent_app.command("events")(_read_command("list_events"))
