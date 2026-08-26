"""Production composition for exact-Snapshot offline research execution."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from stock_research_agent.cli_agent import (
    _command,
    _create_planned_run,
    _execution_service,
    _resources,
)
from stock_research_agent.domain.research_agent.enums import ResearchRunStatus, ResearchType
from stock_research_agent.domain.research_agent.schemas import PageRequest


class SqlAlchemyResearchPipelineCliApplication:
    """Run the existing deterministic Agent composition from one exact Snapshot."""

    def run(
        self,
        snapshot_id: UUID,
        research_type: str,
        policy_version: str,
        as_of: datetime,
    ) -> dict[str, object]:
        with _resources() as resources:
            snapshot = resources.data.get_snapshot(snapshot_id)
            if snapshot is None:
                raise LookupError("SNAPSHOT_NOT_FOUND")
            security = resources.securities.get_security(snapshot.security_id)
            if security is None:
                raise LookupError("SECURITY_NOT_FOUND")
            security_query = f"{security.exchange.mic}:{security.security.symbol}"
            run, request, policy, catalog = _create_planned_run(
                resources,
                _command(
                    security_query,
                    ResearchType(research_type),
                    snapshot_id,
                    as_of,
                    policy_version,
                ),
            )
            plan = resources.research.get_plan(run.id)
            if plan is None:
                raise LookupError("RESEARCH_PLAN_NOT_FOUND")
            if run.status is ResearchRunStatus.PLANNED:
                run, package = _execution_service(resources).execute(
                    run=run,
                    request=request,
                    policy=policy,
                    catalog=catalog,
                )
                package_id = package.id
            else:
                package_view = resources.research.get_package_view(run.id)
                if package_view is None:
                    raise LookupError("RESEARCH_PACKAGE_NOT_FOUND")
                package_id = package_view.id
            steps = resources.research.list_steps(plan.id)
            invocation_count = resources.research.list_invocation_views(
                run.id,
                PageRequest(limit=1, offset=0),
            ).total
            resources.session.commit()
            return {
                "status": run.status.value,
                "request_id": str(request.id),
                "run_id": str(run.id),
                "plan_id": str(plan.id),
                "step_count": len(steps),
                "tool_invocation_count": invocation_count,
                "package_id": str(package_id),
            }


def create_research_pipeline_cli_application() -> SqlAlchemyResearchPipelineCliApplication:
    return SqlAlchemyResearchPipelineCliApplication()


__all__ = [
    "SqlAlchemyResearchPipelineCliApplication",
    "create_research_pipeline_cli_application",
]
