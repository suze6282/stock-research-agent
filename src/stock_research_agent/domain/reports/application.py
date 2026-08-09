"""Transaction-owned application commands for explicit report workflows."""

from __future__ import annotations

from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import model_validator

from stock_research_agent.domain.reports.enums import ReportLocale, ReportType
from stock_research_agent.domain.reports.schemas import FrozenReportContract


class ReportUnitOfWork(Protocol):
    """Small transaction boundary supplied by the composition root."""

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ReportWorkflow[CommandT](Protocol):
    """One bounded workflow operation with no transaction ownership."""

    def execute(self, command: CommandT) -> object: ...


class GenerateReportCommand(FrozenReportContract):
    research_package_id: UUID
    report_type: ReportType
    report_locale: ReportLocale


class ReflectReportCommand(FrozenReportContract):
    report_id: UUID
    round_number: Literal[1, 2]
    prior_reflection_run_id: UUID | None = None
    revision_run_id: UUID | None = None

    @model_validator(mode="after")
    def require_finite_predecessors(self) -> Self:
        if self.round_number == 1 and (
            self.prior_reflection_run_id is not None or self.revision_run_id is not None
        ):
            raise ValueError("round 1 cannot have Reflection or Revision predecessors")
        if self.round_number == 2 and self.prior_reflection_run_id is None:
            raise ValueError("round 2 requires an explicit round 1 predecessor")
        return self


class ReviseReportCommand(FrozenReportContract):
    report_id: UUID
    reflection_run_id: UUID


class ReleaseCheckCommand(FrozenReportContract):
    report_id: UUID
    reflection_run_id: UUID


class _TransactionalService[CommandT]:
    def __init__(
        self,
        workflow: ReportWorkflow[CommandT],
        unit_of_work: ReportUnitOfWork,
    ) -> None:
        self._workflow = workflow
        self._unit_of_work = unit_of_work

    def run(self, command: CommandT) -> object:
        try:
            result = self._workflow.execute(command)
            self._unit_of_work.commit()
        except BaseException:
            self._unit_of_work.rollback()
            raise
        return result


class ReportGenerationService(_TransactionalService[GenerateReportCommand]):
    def generate(self, command: GenerateReportCommand) -> object:
        return self.run(command)


class ReportReflectionService(_TransactionalService[ReflectReportCommand]):
    def reflect(self, command: ReflectReportCommand) -> object:
        return self.run(command)


class ReportRevisionService(_TransactionalService[ReviseReportCommand]):
    def revise(self, command: ReviseReportCommand) -> object:
        return self.run(command)


class ReportReleaseService(_TransactionalService[ReleaseCheckCommand]):
    def check(self, command: ReleaseCheckCommand) -> object:
        return self.run(command)


__all__ = [
    "GenerateReportCommand",
    "ReflectReportCommand",
    "ReleaseCheckCommand",
    "ReportGenerationService",
    "ReportReflectionService",
    "ReportReleaseService",
    "ReportRevisionService",
    "ReportUnitOfWork",
    "ReportWorkflow",
    "ReviseReportCommand",
]
