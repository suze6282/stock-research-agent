"""SQLAlchemy persistence for controlled Research Agent audit records."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.research_agent import (
    ClaimEvidenceLink,
    ResearchAgentRun,
    ResearchClaim,
    ResearchEvidence,
    ResearchObservation,
    ResearchPackage,
    ResearchPlan,
    ResearchPolicy,
    ResearchRequest,
    ResearchRunEvent,
    ResearchStep,
    ResearchToolInvocation,
)
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ResearchRunStatus,
    ResearchStepStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ClaimEvidenceLinkWrite,
    Page,
    PageRequest,
    ResearchAgentRunRecord,
    ResearchAgentRunView,
    ResearchClaimCompletion,
    ResearchClaimRecord,
    ResearchClaimView,
    ResearchClaimWrite,
    ResearchEvidenceRecord,
    ResearchEvidenceView,
    ResearchEvidenceWrite,
    ResearchObservationRecord,
    ResearchObservationWrite,
    ResearchPackageRecord,
    ResearchPackageView,
    ResearchPackageWrite,
    ResearchPlanRecord,
    ResearchPlanView,
    ResearchPlanWrite,
    ResearchPolicyRecord,
    ResearchPolicyWrite,
    ResearchRequestRecord,
    ResearchRequestWrite,
    ResearchRunEventRecord,
    ResearchRunEventView,
    ResearchRunEventWrite,
    ResearchRunUpdate,
    ResearchRunWrite,
    ResearchStepDefinition,
    ResearchStepRecord,
    ResearchStepView,
    ResearchStepWrite,
    ResearchToolInvocationCompletion,
    ResearchToolInvocationRecord,
    ResearchToolInvocationView,
    ResearchToolInvocationWrite,
    RunBudget,
)

_TERMINAL_RUN_STATUSES = {
    ResearchRunStatus.COMPLETED,
    ResearchRunStatus.PARTIAL,
    ResearchRunStatus.BLOCKED,
    ResearchRunStatus.FAILED,
    ResearchRunStatus.CANCELLED,
}


def _json(model: Any) -> Any:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json")
    if isinstance(model, Enum):
        return model.value
    if isinstance(model, UUID):
        return str(model)
    if isinstance(model, Decimal):
        return str(model)
    if isinstance(model, dict):
        return {str(key): _json(value) for key, value in model.items()}
    if isinstance(model, (list, tuple)):
        return [_json(value) for value in model]
    return model


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _utc_optional(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


class SqlAlchemyResearchAgentRepository:
    """One transaction-neutral repository implementing the Stage 7 write ports."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_policy(self, version: str) -> ResearchPolicyRecord | None:
        row = self._session.scalar(select(ResearchPolicy).where(ResearchPolicy.version == version))
        return None if row is None else _policy_record(row)

    def add_policy(self, value: ResearchPolicyWrite) -> ResearchPolicyRecord:
        existing = self.get_policy(value.version)
        if existing is not None:
            if existing.model_dump(mode="python") != value.model_dump(mode="python"):
                raise ValueError("POLICY_VERSION_CONFLICT")
            return existing
        definition = value.model_dump(
            mode="json",
            exclude={"version", "checksum"},
        )
        row = ResearchPolicy(
            version=value.version,
            checksum=value.checksum,
            definition=definition,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            winner = self.get_policy(value.version)
            if winner is None:
                raise
            if winner.model_dump(mode="python") != value.model_dump(mode="python"):
                raise ValueError("POLICY_VERSION_CONFLICT") from None
            return winner
        return _policy_record(row)

    def add_request(self, value: ResearchRequestWrite) -> ResearchRequestRecord:
        row = ResearchRequest(
            id=value.id,
            security_id=value.resolved_security_id,
            snapshot_id=value.snapshot_id,
            security_query=value.security_query,
            normalized_security_query=value.normalized_security_query,
            research_type=value.research_type.value,
            research_mode=value.research_mode.value,
            research_as_of_time=value.research_as_of_time,
            requested_sections=_json(value.requested_sections),
            requested_budgets=_json(value.requested_budgets),
            policy_version=value.policy_version,
            planner_version=value.planner_version,
            tool_catalog_version=value.tool_catalog_version,
            tool_catalog_checksum=value.tool_catalog_checksum,
            request_checksum=value.request_checksum,
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _request_record(row)

    def get_request(self, request_id: UUID) -> ResearchRequestRecord | None:
        row = self._session.get(ResearchRequest, request_id)
        return None if row is None else _request_record(row)

    def create_run(self, value: ResearchRunWrite) -> ResearchAgentRunRecord:
        reusable = self.find_reusable_run(value.idempotency_key)
        if reusable is not None:
            return reusable
        request = self._session.get(ResearchRequest, value.request_id)
        if request is None:
            raise LookupError("RESEARCH_REQUEST_NOT_FOUND")
        row = ResearchAgentRun(
            id=value.id,
            research_request_id=value.request_id,
            security_id=value.security_id,
            snapshot_id=value.snapshot_id,
            research_as_of_time=value.research_as_of_time,
            research_type=request.research_type,
            status=value.status.value,
            policy_version=value.policy_version,
            planner_version=value.planner_version,
            tool_catalog_version=value.tool_catalog_version,
            tool_catalog_checksum=value.tool_catalog_checksum,
            idempotency_key=value.idempotency_key,
            budget=_json(value.budget),
            warning_codes=list(value.warning_codes),
            terminal_reason_code=value.terminal_reason_code,
            created_at=value.created_at,
            updated_at=value.updated_at,
            terminal_at=value.terminal_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            winner = self.find_reusable_run(value.idempotency_key)
            if winner is None:
                raise
            return winner
        return _run_record(row)

    def get_run(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> ResearchAgentRunRecord | None:
        statement = select(ResearchAgentRun).where(ResearchAgentRun.id == run_id)
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement)
        return None if row is None else _run_record(row)

    def find_reusable_run(self, idempotency_key: str) -> ResearchAgentRunRecord | None:
        row = self._session.scalar(
            select(ResearchAgentRun)
            .where(
                ResearchAgentRun.idempotency_key == idempotency_key,
                ResearchAgentRun.status.in_(
                    (
                        "CREATED",
                        "PLANNING",
                        "PLANNED",
                        "RUNNING",
                        "PAUSED",
                        "COMPLETED",
                    )
                ),
            )
            .order_by(ResearchAgentRun.created_at, ResearchAgentRun.id)
            .limit(1)
        )
        return None if row is None else _run_record(row)

    def update_run(
        self,
        run_id: UUID,
        value: ResearchRunUpdate,
    ) -> ResearchAgentRunRecord:
        row = self._session.scalar(
            select(ResearchAgentRun)
            .where(
                ResearchAgentRun.id == run_id,
                ResearchAgentRun.status == value.expected_status.value,
            )
            .with_for_update()
        )
        if row is None:
            raise LookupError("RESEARCH_RUN_STATE_MISMATCH")
        row.status = value.target_status.value
        row.budget = _json(value.budget)
        row.warning_codes = list(value.warning_codes)
        row.terminal_reason_code = value.terminal_reason_code
        row.updated_at = value.changed_at
        row.terminal_at = (
            value.changed_at if value.target_status in _TERMINAL_RUN_STATUSES else None
        )
        self._session.flush()
        return _run_record(row)

    def append_event(self, value: ResearchRunEventWrite) -> ResearchRunEventRecord:
        row = ResearchRunEvent(
            id=value.id,
            research_agent_run_id=value.run_id,
            sequence_number=value.sequence_number,
            event_type=value.event_type.value,
            from_status=None if value.from_status is None else value.from_status.value,
            to_status=None if value.to_status is None else value.to_status.value,
            reason_code=value.reason_code,
            step_id=None,
            invocation_id=None,
            safe_message=None,
            event_metadata=_json(value.safe_detail),
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _event_record(row)

    def add_plan(self, value: ResearchPlanWrite) -> ResearchPlanRecord:
        row = ResearchPlan(
            id=value.id,
            research_agent_run_id=value.run_id,
            planner_version=value.planner_version,
            plan_version=value.plan_version,
            tool_catalog_version=value.tool_catalog_version,
            status="VALIDATED",
            steps=_json(value.steps),
            plan_checksum=value.plan_checksum,
            completed_at=value.created_at,
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _plan_record(row)

    def add_steps(
        self,
        values: tuple[ResearchStepWrite, ...],
    ) -> tuple[ResearchStepRecord, ...]:
        rows = [_step_row(value) for value in values]
        self._session.add_all(rows)
        self._session.flush()
        return tuple(_step_record(row) for row in rows)

    def get_plan(self, run_id: UUID) -> ResearchPlanRecord | None:
        row = self._session.scalar(
            select(ResearchPlan).where(ResearchPlan.research_agent_run_id == run_id)
        )
        return None if row is None else _plan_record(row)

    def list_steps(self, plan_id: UUID) -> tuple[ResearchStepRecord, ...]:
        rows = self._session.scalars(
            select(ResearchStep)
            .where(ResearchStep.research_plan_id == plan_id)
            .order_by(ResearchStep.step_index, ResearchStep.id)
        ).all()
        return tuple(_step_record(row) for row in rows)

    def transition_step(
        self,
        step_id: UUID,
        *,
        expected_status: ResearchStepStatus,
        target_status: ResearchStepStatus,
        changed_at: datetime,
        skip_reason_code: str | None = None,
    ) -> ResearchStepRecord:
        row = self._session.scalar(
            select(ResearchStep)
            .where(
                ResearchStep.id == step_id,
                ResearchStep.status == expected_status.value,
            )
            .with_for_update()
        )
        if row is None:
            raise LookupError("RESEARCH_STEP_STATE_MISMATCH")
        row.status = target_status.value
        row.skip_reason_code = skip_reason_code
        row.updated_at = changed_at
        row.terminal_at = (
            changed_at
            if target_status
            in {
                ResearchStepStatus.PASS,
                ResearchStepStatus.PARTIAL,
                ResearchStepStatus.BLOCKED,
                ResearchStepStatus.FAIL,
                ResearchStepStatus.SKIPPED,
            }
            else None
        )
        self._session.flush()
        return _step_record(row)

    def update_run_budget(self, run_id: UUID, budget: RunBudget) -> ResearchAgentRunRecord:
        row = self._session.scalar(
            select(ResearchAgentRun)
            .where(
                ResearchAgentRun.id == run_id,
                ~ResearchAgentRun.status.in_(
                    tuple(status.value for status in _TERMINAL_RUN_STATUSES)
                ),
            )
            .with_for_update()
        )
        if row is None:
            raise LookupError("RESEARCH_RUN_NOT_MUTABLE")
        row.budget = _json(budget)
        row.updated_at = datetime.now(UTC)
        self._session.flush()
        return _run_record(row)

    def add_invocation(
        self,
        value: ResearchToolInvocationWrite,
    ) -> ResearchToolInvocationRecord:
        row = ResearchToolInvocation(
            id=value.id,
            research_agent_run_id=value.run_id,
            research_step_id=value.step_id,
            attempt_number=value.attempt_number,
            tool_name=value.tool_name,
            tool_version=value.tool_version,
            permission="READ_ONLY",
            redacted_input=_json(value.redacted_input),
            input_checksum=value.input_checksum,
            output_checksum=None,
            status=value.status.value,
            error_code=None,
            safe_error_message=None,
            started_at=value.started_at,
            completed_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return _invocation_record(row)

    def complete_invocation(
        self,
        invocation_id: UUID,
        value: ResearchToolInvocationCompletion,
    ) -> ResearchToolInvocationRecord:
        row = self._session.scalar(
            select(ResearchToolInvocation)
            .where(ResearchToolInvocation.id == invocation_id)
            .with_for_update()
        )
        if row is None:
            raise LookupError("RESEARCH_TOOL_INVOCATION_NOT_FOUND")
        row.status = value.status.value
        row.output_checksum = value.output_checksum
        row.error_code = value.error_code
        row.safe_error_message = value.safe_error_message
        row.completed_at = value.completed_at
        self._session.flush()
        return _invocation_record(row)

    def add_observation(
        self,
        value: ResearchObservationWrite,
    ) -> ResearchObservationRecord:
        row = ResearchObservation(
            id=value.id,
            research_agent_run_id=value.run_id,
            invocation_id=value.invocation_id,
            observation_type=value.observation_type.value,
            status=value.status.value,
            schema_version=value.schema_version,
            payload=_json(value.payload),
            output_checksum=value.output_checksum,
            security_id=value.security_id,
            snapshot_id=value.snapshot_id,
            research_as_of_time=value.research_as_of_time,
            synthetic_status=value.synthetic_status.value,
            warnings=list(value.warnings),
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _observation_record(row)

    def add_evidence(
        self,
        values: tuple[ResearchEvidenceWrite, ...],
    ) -> tuple[ResearchEvidenceRecord, ...]:
        rows = [_evidence_row(value) for value in values]
        self._session.add_all(rows)
        self._session.flush()
        return tuple(_evidence_record(row) for row in rows)

    def list_evidence(self, run_id: UUID) -> tuple[ResearchEvidenceRecord, ...]:
        rows = self._session.scalars(
            select(ResearchEvidence)
            .where(ResearchEvidence.research_agent_run_id == run_id)
            .order_by(ResearchEvidence.created_at, ResearchEvidence.id)
        ).all()
        return tuple(_evidence_record(row) for row in rows)

    def add_claim(self, value: ResearchClaimWrite) -> ResearchClaimRecord:
        basis = value.model_dump(
            mode="json",
            exclude={"id", "lifecycle_status", "support_status", "validator_version"},
        )
        row = ResearchClaim(
            id=value.id,
            research_agent_run_id=value.run_id,
            claim_key=stable_checksum(basis),
            claim_type=value.claim_type.value,
            lifecycle_status=value.lifecycle_status.value,
            support_status=(None if value.support_status is None else value.support_status.value),
            statement_code=value.statement_code,
            value=value.value,
            unit=value.unit,
            currency_code=value.currency_code,
            period=value.period,
            as_of_time=value.as_of_time,
            metric_basis=value.metric_basis,
            builder_version=value.builder_version,
            validator_version=value.validator_version,
            created_at=value.created_at,
            completed_at=value.completed_at,
        )
        self._session.add(row)
        self._session.flush()
        return _claim_record(row)

    def add_links(
        self,
        values: tuple[ClaimEvidenceLinkWrite, ...],
    ) -> tuple[ClaimEvidenceLinkRecord, ...]:
        rows = [
            ClaimEvidenceLink(
                id=value.id,
                research_agent_run_id=value.run_id,
                claim_id=value.claim_id,
                evidence_id=value.evidence_id,
                role=value.role.value,
                created_at=value.created_at,
            )
            for value in values
        ]
        self._session.add_all(rows)
        self._session.flush()
        return tuple(_link_record(row) for row in rows)

    def complete_claim(
        self,
        claim_id: UUID,
        value: ResearchClaimCompletion,
    ) -> ResearchClaimRecord:
        row = self._session.scalar(
            select(ResearchClaim).where(ResearchClaim.id == claim_id).with_for_update()
        )
        if row is None:
            raise LookupError("RESEARCH_CLAIM_NOT_FOUND")
        row.lifecycle_status = value.lifecycle_status.value
        row.support_status = value.support_status.value
        row.validator_version = value.validator_version
        row.completed_at = value.completed_at
        self._session.flush()
        return _claim_record(row)

    def add_package(self, value: ResearchPackageWrite) -> ResearchPackageRecord:
        row = ResearchPackage(
            research_agent_run_id=value.run_id,
            request_id=value.request_id,
            security_id=value.security_id,
            snapshot_id=value.snapshot_id,
            research_as_of_time=value.research_as_of_time,
            research_type=value.research_type.value,
            policy_version=value.policy_version,
            planner_version=value.planner_version,
            tool_catalog_version=value.tool_catalog_version,
            evidence_version=value.evidence_version,
            claim_version=value.claim_version,
            package_version=value.package_version,
            status=value.status.value,
            sections=_json(value.sections),
            evidence_ids=_json(value.evidence_ids),
            unsupported_claim_ids=_json(value.unsupported_claim_ids),
            conflicting_claim_ids=_json(value.conflicting_claim_ids),
            blocked_capabilities=list(value.blocked_capabilities),
            warnings=list(value.warnings),
            checksum=value.checksum,
        )
        self._session.add(row)
        self._session.flush()
        return _package_record(row)

    def get_run_view(self, run_id: UUID) -> ResearchAgentRunView | None:
        return self.get_run(run_id)

    def get_plan_view(self, run_id: UUID) -> ResearchPlanView | None:
        return self.get_plan(run_id)

    def list_step_views(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchStepView]:
        condition = ResearchStep.research_agent_run_id == run_id
        total = int(
            self._session.scalar(select(func.count()).select_from(ResearchStep).where(condition))
            or 0
        )
        rows = self._session.scalars(
            select(ResearchStep)
            .where(condition)
            .order_by(ResearchStep.step_index, ResearchStep.id)
            .offset(page.offset)
            .limit(page.limit)
        ).all()
        return Page(
            items=tuple(_step_record(row) for row in rows),
            limit=page.limit,
            offset=page.offset,
            total=total,
        )

    def list_invocation_views(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchToolInvocationView]:
        condition = ResearchToolInvocation.research_agent_run_id == run_id
        total = int(
            self._session.scalar(
                select(func.count()).select_from(ResearchToolInvocation).where(condition)
            )
            or 0
        )
        rows = self._session.scalars(
            select(ResearchToolInvocation)
            .where(condition)
            .order_by(
                ResearchToolInvocation.started_at,
                ResearchToolInvocation.attempt_number,
                ResearchToolInvocation.id,
            )
            .offset(page.offset)
            .limit(page.limit)
        ).all()
        return Page(
            items=tuple(_invocation_record(row) for row in rows),
            limit=page.limit,
            offset=page.offset,
            total=total,
        )

    def list_evidence_views(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchEvidenceView]:
        condition = ResearchEvidence.research_agent_run_id == run_id
        total = int(
            self._session.scalar(
                select(func.count()).select_from(ResearchEvidence).where(condition)
            )
            or 0
        )
        rows = self._session.scalars(
            select(ResearchEvidence)
            .where(condition)
            .order_by(ResearchEvidence.created_at, ResearchEvidence.id)
            .offset(page.offset)
            .limit(page.limit)
        ).all()
        return Page(
            items=tuple(_evidence_view(row) for row in rows),
            limit=page.limit,
            offset=page.offset,
            total=total,
        )

    def list_claim_views(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchClaimView]:
        condition = ResearchClaim.research_agent_run_id == run_id
        total = int(
            self._session.scalar(select(func.count()).select_from(ResearchClaim).where(condition))
            or 0
        )
        rows = self._session.scalars(
            select(ResearchClaim)
            .where(condition)
            .order_by(ResearchClaim.created_at, ResearchClaim.claim_key, ResearchClaim.id)
            .offset(page.offset)
            .limit(page.limit)
        ).all()
        return Page(
            items=tuple(_claim_record(row) for row in rows),
            limit=page.limit,
            offset=page.offset,
            total=total,
        )

    def get_package_view(self, run_id: UUID) -> ResearchPackageView | None:
        row = self._session.scalar(
            select(ResearchPackage).where(ResearchPackage.research_agent_run_id == run_id)
        )
        return None if row is None else _package_record(row)

    def list_event_views(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchRunEventView]:
        condition = ResearchRunEvent.research_agent_run_id == run_id
        total = int(
            self._session.scalar(
                select(func.count()).select_from(ResearchRunEvent).where(condition)
            )
            or 0
        )
        rows = self._session.scalars(
            select(ResearchRunEvent)
            .where(condition)
            .order_by(ResearchRunEvent.sequence_number, ResearchRunEvent.id)
            .offset(page.offset)
            .limit(page.limit)
        ).all()
        return Page(
            items=tuple(_event_record(row) for row in rows),
            limit=page.limit,
            offset=page.offset,
            total=total,
        )


def _policy_record(row: ResearchPolicy) -> ResearchPolicyRecord:
    return ResearchPolicyRecord.model_validate(
        {"version": row.version, "checksum": row.checksum, **row.definition},
        strict=False,
    )


def _request_record(row: ResearchRequest) -> ResearchRequestRecord:
    return ResearchRequestRecord.model_validate(
        {
            "id": row.id,
            "security_query": row.security_query,
            "resolved_security_id": row.security_id,
            "normalized_security_query": row.normalized_security_query,
            "research_type": row.research_type,
            "research_mode": row.research_mode,
            "snapshot_id": row.snapshot_id,
            "research_as_of_time": _utc(row.research_as_of_time),
            "requested_sections": row.requested_sections,
            "requested_budgets": row.requested_budgets,
            "policy_version": row.policy_version,
            "planner_version": row.planner_version,
            "tool_catalog_version": row.tool_catalog_version,
            "tool_catalog_checksum": row.tool_catalog_checksum,
            "request_checksum": row.request_checksum,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _run_record(row: ResearchAgentRun) -> ResearchAgentRunRecord:
    return ResearchAgentRunRecord.model_validate(
        {
            "id": row.id,
            "request_id": row.research_request_id,
            "security_id": row.security_id,
            "snapshot_id": row.snapshot_id,
            "research_as_of_time": _utc(row.research_as_of_time),
            "status": row.status,
            "policy_version": row.policy_version,
            "planner_version": row.planner_version,
            "tool_catalog_version": row.tool_catalog_version,
            "tool_catalog_checksum": row.tool_catalog_checksum,
            "idempotency_key": row.idempotency_key,
            "budget": row.budget,
            "warning_codes": row.warning_codes,
            "terminal_reason_code": row.terminal_reason_code,
            "created_at": _utc(row.created_at),
            "updated_at": _utc(row.updated_at),
            "terminal_at": _utc_optional(row.terminal_at),
        },
        strict=False,
    )


def _plan_record(row: ResearchPlan) -> ResearchPlanRecord:
    return ResearchPlanRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "planner_version": row.planner_version,
            "plan_version": row.plan_version,
            "tool_catalog_version": row.tool_catalog_version,
            "steps": row.steps,
            "plan_checksum": row.plan_checksum,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _step_row(value: ResearchStepWrite) -> ResearchStep:
    definition = value.definition
    return ResearchStep(
        id=value.id,
        research_agent_run_id=value.run_id,
        research_plan_id=value.plan_id,
        step_index=definition.step_index,
        step_key=definition.step_key,
        step_type=definition.step_type.value,
        title=definition.title,
        required=definition.required,
        dependency_keys=list(definition.dependency_keys),
        tool_name=definition.tool_name,
        tool_version=definition.tool_version,
        component_name=definition.component_name,
        input_binding=_json(definition.input_binding),
        fanout_limit=definition.fanout_limit,
        status=value.status.value,
        skip_reason_code=value.skip_reason_code,
        created_at=value.created_at,
        updated_at=value.created_at,
        terminal_at=None,
    )


def _step_record(row: ResearchStep) -> ResearchStepRecord:
    definition = ResearchStepDefinition.model_validate(
        {
            "step_index": row.step_index,
            "step_key": row.step_key,
            "step_type": row.step_type,
            "title": row.title,
            "required": row.required,
            "dependency_keys": row.dependency_keys,
            "tool_name": row.tool_name,
            "tool_version": row.tool_version,
            "component_name": row.component_name,
            "input_binding": row.input_binding,
            "fanout_limit": row.fanout_limit,
        },
        strict=False,
    )
    return ResearchStepRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "plan_id": row.research_plan_id,
            "definition": definition,
            "status": row.status,
            "skip_reason_code": row.skip_reason_code,
            "created_at": _utc(row.created_at),
            "updated_at": _utc(row.updated_at),
            "terminal_at": _utc_optional(row.terminal_at),
        },
        strict=False,
    )


def _invocation_record(row: ResearchToolInvocation) -> ResearchToolInvocationRecord:
    return ResearchToolInvocationRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "step_id": row.research_step_id,
            "attempt_number": row.attempt_number,
            "tool_name": row.tool_name,
            "tool_version": row.tool_version,
            "status": row.status,
            "redacted_input": row.redacted_input,
            "input_checksum": row.input_checksum,
            "output_checksum": row.output_checksum,
            "error_code": row.error_code,
            "safe_error_message": row.safe_error_message,
            "started_at": _utc(row.started_at),
            "completed_at": _utc_optional(row.completed_at),
        },
        strict=False,
    )


def _observation_record(row: ResearchObservation) -> ResearchObservationRecord:
    return ResearchObservationRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "invocation_id": row.invocation_id,
            "observation_type": row.observation_type,
            "status": row.status,
            "schema_version": row.schema_version,
            "payload": row.payload,
            "output_checksum": row.output_checksum,
            "security_id": row.security_id,
            "snapshot_id": row.snapshot_id,
            "research_as_of_time": _utc(row.research_as_of_time),
            "synthetic_status": row.synthetic_status,
            "warnings": row.warnings,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _evidence_row(value: ResearchEvidenceWrite) -> ResearchEvidence:
    return ResearchEvidence(
        id=value.id,
        research_agent_run_id=value.run_id,
        observation_id=value.observation_id,
        evidence_type=value.evidence_type.value,
        status=value.status.value,
        schema_version=value.schema_version,
        security_id=value.security_id,
        snapshot_id=value.snapshot_id,
        research_as_of_time=value.research_as_of_time,
        source_record_type=value.source_record_type,
        source_record_id=value.source_record_id,
        source_checksum=value.source_checksum,
        published_at=value.published_at,
        citation_id=value.citation_id,
        calculation_run_id=value.calculation_run_id,
        calculation_input_ids=_json(value.calculation_input_ids),
        formula_version=value.formula_version,
        synthetic_status=value.synthetic_status.value,
        payload=_json(value.payload),
        warning_codes=list(value.warning_codes),
        created_at=value.created_at,
    )


def _evidence_record(row: ResearchEvidence) -> ResearchEvidenceRecord:
    return ResearchEvidenceRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "observation_id": row.observation_id,
            "evidence_type": row.evidence_type,
            "status": row.status,
            "schema_version": row.schema_version,
            "security_id": row.security_id,
            "snapshot_id": row.snapshot_id,
            "research_as_of_time": _utc(row.research_as_of_time),
            "source_record_type": row.source_record_type,
            "source_record_id": row.source_record_id,
            "source_checksum": row.source_checksum,
            "published_at": _utc_optional(row.published_at),
            "citation_id": row.citation_id,
            "calculation_run_id": row.calculation_run_id,
            "calculation_input_ids": row.calculation_input_ids,
            "formula_version": row.formula_version,
            "synthetic_status": row.synthetic_status,
            "payload": row.payload,
            "warning_codes": row.warning_codes,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _claim_record(row: ResearchClaim) -> ResearchClaimRecord:
    return ResearchClaimRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "claim_type": row.claim_type,
            "lifecycle_status": row.lifecycle_status,
            "support_status": row.support_status,
            "statement_code": row.statement_code,
            "value": row.value,
            "unit": row.unit,
            "currency_code": row.currency_code,
            "period": row.period,
            "as_of_time": _utc_optional(row.as_of_time),
            "metric_basis": row.metric_basis,
            "builder_version": row.builder_version,
            "validator_version": row.validator_version,
            "created_at": _utc(row.created_at),
            "completed_at": _utc_optional(row.completed_at),
        },
        strict=False,
    )


def _evidence_view(row: ResearchEvidence) -> ResearchEvidenceView:
    values = _evidence_record(row).model_dump(mode="python", exclude={"payload"})
    return ResearchEvidenceView.model_validate(values)


def _link_record(row: ClaimEvidenceLink) -> ClaimEvidenceLinkRecord:
    return ClaimEvidenceLinkRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "claim_id": row.claim_id,
            "evidence_id": row.evidence_id,
            "role": row.role,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _package_record(row: ResearchPackage) -> ResearchPackageRecord:
    return ResearchPackageRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "request_id": row.request_id,
            "security_id": row.security_id,
            "snapshot_id": row.snapshot_id,
            "research_as_of_time": _utc(row.research_as_of_time),
            "research_type": row.research_type,
            "policy_version": row.policy_version,
            "planner_version": row.planner_version,
            "tool_catalog_version": row.tool_catalog_version,
            "evidence_version": row.evidence_version,
            "claim_version": row.claim_version,
            "package_version": row.package_version,
            "status": row.status,
            "sections": row.sections,
            "evidence_ids": row.evidence_ids,
            "unsupported_claim_ids": row.unsupported_claim_ids,
            "conflicting_claim_ids": row.conflicting_claim_ids,
            "blocked_capabilities": row.blocked_capabilities,
            "warnings": row.warnings,
            "checksum": row.checksum,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _event_record(row: ResearchRunEvent) -> ResearchRunEventRecord:
    return ResearchRunEventRecord.model_validate(
        {
            "id": row.id,
            "run_id": row.research_agent_run_id,
            "sequence_number": row.sequence_number,
            "event_type": row.event_type,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "reason_code": row.reason_code,
            "safe_detail": row.event_metadata,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )
