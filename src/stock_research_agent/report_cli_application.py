"""Production composition root for explicit, offline Stage 8 CLI operations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_research_agent.config import Settings
from stock_research_agent.db.models.reports import (
    ReportPolicy,
    ReportTemplateVersion,
    RuntimeReflectionPolicy,
)
from stock_research_agent.db.repositories.reports import (
    SqlAlchemyReportGenerationRepository,
    SqlAlchemyReportReflectionRepository,
    SqlAlchemyReportReleaseGateRepository,
    SqlAlchemyReportRepository,
    SqlAlchemyReportRevisionRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.reports.application import (
    GenerateReportCommand,
    ReflectReportCommand,
    ReleaseCheckCommand,
    ReviseReportCommand,
)
from stock_research_agent.domain.reports.composition import (
    DeterministicReportCompositionService,
)
from stock_research_agent.domain.reports.enums import ReportSection
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunWrite,
    ReportGenerationStatus,
    ReportGenerationTransition,
)
from stock_research_agent.domain.reports.input_verification import (
    validate_report_input_manifest,
)
from stock_research_agent.domain.reports.policies import (
    REPORT_POLICY_VERSION,
    ReportPolicySeedService,
)
from stock_research_agent.domain.reports.queries import ReportQueryService
from stock_research_agent.domain.reports.reflection import (
    CandidateReflectionFinding,
    DeterministicReportReflectionEngine,
    ReportReflectionCompletion,
    ReportReflectionFindingWrite,
    ReportReflectionRunWrite,
    ReportReflectionStatus,
    count_findings_by_severity,
)
from stock_research_agent.domain.reports.reflection_policy import (
    RUNTIME_REFLECTION_POLICY_VERSION,
    RuntimeReflectionPolicySeedService,
)
from stock_research_agent.domain.reports.release_gate import (
    RELEASE_GATE_VERSION,
    ReportReleaseGate,
    ReportReleaseGateWrite,
)
from stock_research_agent.domain.reports.rendering import RENDERER_VERSION
from stock_research_agent.domain.reports.requests import (
    CreateReportRequest,
    ReportRequestService,
)
from stock_research_agent.domain.reports.revision import (
    REVISION_ENGINE_NAME,
    REVISION_ENGINE_VERSION,
    DeterministicReportRevisionEngine,
    ReportRevisionCompletion,
    ReportRevisionRunWrite,
    ReportRevisionStatus,
)
from stock_research_agent.domain.reports.schemas import ReportRequestRecord
from stock_research_agent.domain.reports.templates import (
    ReportTemplateSeedService,
    build_default_template_writes,
)
from stock_research_agent.domain.research_agent.schemas import PageRequest


def _now() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyReportCliApplication:
    """Open one bounded transaction for each explicit CLI invocation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._engine = create_engine_from_settings(self._settings)
        self._sessions = create_session_factory(self._engine)
        self.export_root = Path.cwd().resolve()

    def invoke(self, operation: str, value: object | None = None) -> object:
        try:
            with session_scope(self._sessions) as session:
                result = self._invoke(session, operation, value)
                session.commit()
                return result
        finally:
            self._engine.dispose()

    def _invoke(
        self,
        session: Session,
        operation: str,
        value: object | None,
    ) -> object:
        repository = SqlAlchemyReportRepository(session)
        if operation == "policy-seed-v1":
            return ReportPolicySeedService(repository).seed_v1()
        if operation == "reflection-policy-seed-v1":
            return RuntimeReflectionPolicySeedService(repository).seed_v1()
        if operation == "template-seed-v1":
            return ReportTemplateSeedService(repository).seed_v1()
        if operation == "policy-list":
            return self._list_rows(session, ReportPolicy, ReportPolicy.version)
        if operation == "reflection-policy-list":
            return self._list_rows(
                session,
                RuntimeReflectionPolicy,
                RuntimeReflectionPolicy.version,
            )
        if operation == "template-list":
            return self._list_rows(
                session,
                ReportTemplateVersion,
                ReportTemplateVersion.name,
                ReportTemplateVersion.locale,
            )
        if operation == "generate" and isinstance(value, GenerateReportCommand):
            return self._generate(repository, session, value)
        if operation == "reflect" and isinstance(value, ReflectReportCommand):
            return self._reflect(repository, session, value)
        if operation == "revise" and isinstance(value, ReviseReportCommand):
            return self._revise(repository, session, value)
        if operation == "release-check" and isinstance(value, ReleaseCheckCommand):
            return self._release(repository, session, value)
        if not isinstance(value, UUID):
            raise ValueError("REPORT_CLI_OPERATION_INVALID")
        return self._read(repository, operation, value)

    @staticmethod
    def _list_rows(
        session: Session,
        model: Any,
        *ordering: Any,
    ) -> tuple[dict[str, object], ...]:
        rows = session.scalars(select(model).order_by(*ordering)).all()
        return tuple(
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in rows
        )

    def _generate(
        self,
        repository: SqlAlchemyReportRepository,
        session: Session,
        command: GenerateReportCommand,
    ) -> object:
        policy = repository.get_policy(REPORT_POLICY_VERSION)
        reflection_policy = repository.get_runtime_reflection_policy(
            RUNTIME_REFLECTION_POLICY_VERSION
        )
        template_write = next(
            item
            for item in build_default_template_writes()
            if item.report_type is command.report_type and item.locale is command.report_locale
        )
        template = repository.get_template(
            template_write.name,
            template_write.version,
            command.report_locale,
        )
        if policy is None or reflection_policy is None or template is None:
            raise LookupError("REPORT_REFERENCE_DATA_NOT_SEEDED")
        request = ReportRequestService(
            inputs=repository,
            requests=repository,
            id_factory=uuid4,
            now=_now,
        ).create(
            CreateReportRequest(
                research_package_id=command.research_package_id,
                report_type=command.report_type,
                report_locale=command.report_locale,
                template_name=template.name,
                template_version=template.version,
                report_policy_version=policy.version,
                reflection_policy_version=reflection_policy.version,
                requested_sections=tuple(ReportSection),
                include_evidence_appendix=True,
                include_claim_index=True,
                max_excerpt_length=policy.max_excerpt_length,
            )
        )
        persisted = repository.get_package_bundle(command.research_package_id)
        if persisted is None:
            raise LookupError("RESEARCH_PACKAGE_NOT_FOUND")
        verified = validate_report_input_manifest(request.manifest, persisted)
        created_at = _now()
        run_id = uuid4()
        generation = SqlAlchemyReportGenerationRepository(session)
        run = generation.create_run(
            ReportGenerationRunWrite(
                id=run_id,
                report_request_id=request.id,
                research_package_id=request.manifest.research_package_id,
                research_agent_run_id=request.manifest.research_agent_run_id,
                security_id=request.manifest.security_id,
                snapshot_id=request.manifest.snapshot_id,
                research_as_of_time=request.manifest.research_as_of_time,
                report_type=request.report_type,
                report_locale=request.report_locale,
                report_policy_version=request.report_policy_version,
                template_name=request.template_name,
                template_version=request.template_version,
                renderer_version=RENDERER_VERSION,
                manifest_schema_version=request.manifest.manifest_schema_version,
                manifest_checksum=request.manifest.canonical_payload_checksum,
                package_checksum=request.manifest.package_checksum,
                claims_checksum=request.manifest.claims_checksum,
                evidence_checksum=request.manifest.evidence_checksum,
                links_checksum=request.manifest.links_checksum,
                citations_checksum=request.manifest.citations_checksum,
                lineage_checksum=request.manifest.lineage_checksum,
                idempotency_key=request.idempotency_key,
                status=ReportGenerationStatus.CREATED,
                warning_count=0,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        run = generation.transition(
            run.id,
            ReportGenerationTransition(
                expected_status=ReportGenerationStatus.CREATED,
                target_status=ReportGenerationStatus.RUNNING,
                warning_count=0,
                changed_at=created_at,
            ),
        )
        report = DeterministicReportCompositionService().compose(
            verified,
            request,
            policy,
            template,
            report_id=uuid4(),
            generation_run_id=run.id,
            created_at=created_at,
        )
        persisted_report = repository.add_report(report)
        terminal_status, reason = _generation_outcome(persisted_report.report.status.value)
        run = generation.transition(
            run.id,
            ReportGenerationTransition(
                expected_status=ReportGenerationStatus.RUNNING,
                target_status=terminal_status,
                warning_count=len(request.manifest.warnings),
                blocked_reason_code=reason,
                changed_at=_now(),
            ),
        )
        return {
            "status": run.status.value,
            "report_id": str(persisted_report.report.id),
            "generation_run_id": str(run.id),
        }

    def _reflect(
        self,
        repository: SqlAlchemyReportRepository,
        session: Session,
        command: ReflectReportCommand,
    ) -> object:
        report = repository.get_report(command.report_id)
        if report is None:
            raise LookupError("RESEARCH_REPORT_NOT_FOUND")
        request = _request_for_report(repository, session, report.report.report_generation_run_id)
        policy = repository.get_runtime_reflection_policy(request.reflection_policy_version)
        if policy is None:
            raise LookupError("RUNTIME_REFLECTION_POLICY_NOT_FOUND")
        draft = DeterministicReportReflectionEngine().reflect(
            report,
            request.manifest,
            policy,
            command.round_number,
        )
        run_id = uuid4()
        started_at = _now()
        reflections = SqlAlchemyReportReflectionRepository(session)
        reflections.create_run(
            ReportReflectionRunWrite(
                id=run_id,
                research_report_id=report.report.id,
                reflection_policy_version=policy.version,
                engine_name=draft.engine_name,
                engine_version=draft.engine_version,
                round_number=command.round_number,
                input_report_checksum=report.report.content_checksum,
                status=ReportReflectionStatus.RUNNING,
                started_at=started_at,
            )
        )
        findings = tuple(
            _finding_write(
                report.report.id,
                run_id,
                index,
                candidate,
                started_at,
            )
            for index, candidate in enumerate(draft.findings)
        )
        counts = count_findings_by_severity(findings)
        result = reflections.complete_run(
            run_id,
            ReportReflectionCompletion(
                target_status=draft.status,
                total_finding_count=counts.total,
                critical_count=counts.critical,
                high_count=counts.high,
                medium_count=counts.medium,
                low_count=counts.low,
                completed_at=_now(),
            ),
            findings,
        )
        return result.model_dump(mode="json")

    def _revise(
        self,
        repository: SqlAlchemyReportRepository,
        session: Session,
        command: ReviseReportCommand,
    ) -> object:
        source = repository.get_report(command.report_id)
        reflection = SqlAlchemyReportReflectionRepository(session).get_result(
            command.reflection_run_id
        )
        if source is None or reflection is None:
            raise LookupError("REPORT_REVISION_INPUT_NOT_FOUND")
        policy = repository.get_policy(REPORT_POLICY_VERSION)
        if policy is None:
            raise LookupError("REPORT_POLICY_NOT_FOUND")
        draft = DeterministicReportRevisionEngine().revise(
            source,
            reflection,
            policy,
        )
        run_id = uuid4()
        started_at = _now()
        revisions = SqlAlchemyReportRevisionRepository(
            session,
            repository,
        )
        revisions.create_run(
            ReportRevisionRunWrite(
                id=run_id,
                source_report_id=source.report.id,
                source_reflection_run_id=reflection.run.id,
                report_policy_version=policy.version,
                engine_name=REVISION_ENGINE_NAME,
                engine_version=REVISION_ENGINE_VERSION,
                revision_round=1,
                status=ReportRevisionStatus.RUNNING,
                started_at=started_at,
            )
        )
        status = (
            ReportRevisionStatus.COMPLETED
            if not draft.unresolved_finding_ids
            else ReportRevisionStatus.PARTIAL
        )
        result = revisions.complete_run(
            run_id,
            ReportRevisionCompletion(
                target_status=status,
                target_report_id=draft.target.report.id,
                actions=draft.actions,
                applied_finding_ids=draft.applied_finding_ids,
                unresolved_finding_ids=draft.unresolved_finding_ids,
                completed_at=_now(),
            ),
            draft.target,
        )
        return result.model_dump(mode="json")

    def _release(
        self,
        repository: SqlAlchemyReportRepository,
        session: Session,
        command: ReleaseCheckCommand,
    ) -> object:
        report = repository.get_report(command.report_id)
        reflection = SqlAlchemyReportReflectionRepository(session).get_result(
            command.reflection_run_id
        )
        if report is None or reflection is None:
            raise LookupError("REPORT_RELEASE_INPUT_NOT_FOUND")
        request = _request_for_report(repository, session, report.report.report_generation_run_id)
        policy = repository.get_policy(request.report_policy_version)
        if policy is None:
            raise LookupError("REPORT_POLICY_NOT_FOUND")
        decision = ReportReleaseGate().evaluate(
            report,
            request.manifest,
            reflection,
            policy,
        )
        record = SqlAlchemyReportReleaseGateRepository(
            session,
            repository,
        ).add_gate(
            ReportReleaseGateWrite(
                id=uuid5(
                    NAMESPACE_URL,
                    f"{report.report.id}:{RELEASE_GATE_VERSION}",
                ),
                decision=decision,
                sealed_report_id=(
                    None if decision.sealed_report is None else decision.sealed_report.report.id
                ),
                created_at=_now(),
            )
        )
        return record.model_dump(mode="json")

    @staticmethod
    def _read(
        repository: SqlAlchemyReportRepository,
        operation: str,
        report_id: UUID,
    ) -> object:
        query = ReportQueryService(repository)
        page = PageRequest(limit=100, offset=0)
        if operation == "show":
            return query.get_report(report_id)
        if operation == "sections":
            return query.list_sections(report_id, page)
        if operation == "claims":
            return query.list_claim_bindings(report_id, page)
        if operation == "evidence":
            return query.list_evidence_bindings(report_id, page)
        if operation == "citations":
            return query.list_citations(report_id, page)
        if operation == "findings":
            return query.list_reflection_findings(report_id, page)
        if operation == "versions":
            report = repository.get_report(report_id)
            if report is None:
                return query.get_report(report_id)
            return repository.list_versions(report.report.report_generation_run_id)
        raise ValueError("REPORT_CLI_OPERATION_INVALID")


def _request_for_report(
    repository: SqlAlchemyReportRepository,
    session: Session,
    generation_run_id: UUID,
) -> ReportRequestRecord:
    generation = SqlAlchemyReportGenerationRepository(session).get_run(generation_run_id)
    if generation is None:
        raise LookupError("REPORT_GENERATION_RUN_NOT_FOUND")
    request = repository.get_request(generation.report_request_id)
    if request is None:
        raise LookupError("REPORT_REQUEST_NOT_FOUND")
    return request


def _finding_write(
    report_id: UUID,
    run_id: UUID,
    index: int,
    candidate: CandidateReflectionFinding,
    created_at: datetime,
) -> ReportReflectionFindingWrite:
    section = candidate.report_section
    block_key = candidate.block_key
    return ReportReflectionFindingWrite(
        id=uuid5(
            NAMESPACE_URL,
            f"{run_id}:finding:{index}:{candidate.finding_code.value}:{block_key}",
        ),
        reflection_run_id=run_id,
        research_report_id=report_id,
        report_section_id=(
            None
            if section is None
            else uuid5(NAMESPACE_URL, f"{report_id}:section:{section.value}")
        ),
        report_block_id=(
            None if block_key is None else uuid5(NAMESPACE_URL, f"{report_id}:block:{block_key}")
        ),
        claim_id=candidate.claim_id,
        evidence_id=candidate.evidence_id,
        citation_id=candidate.citation_id,
        finding_code=candidate.finding_code.value,
        category=candidate.category,
        severity=candidate.severity,
        description=candidate.description,
        remediation_code=candidate.remediation_code,
        blocking=candidate.blocking,
        created_at=created_at,
    )


def _generation_outcome(
    report_status: str,
) -> tuple[ReportGenerationStatus, str | None]:
    if report_status == "DRAFT":
        return ReportGenerationStatus.COMPLETED, None
    if report_status == "PARTIAL":
        return ReportGenerationStatus.PARTIAL, "VERIFIED_EVIDENCE_INCOMPLETE"
    if report_status == "BLOCKED":
        return ReportGenerationStatus.BLOCKED, "VERIFIED_EVIDENCE_UNAVAILABLE"
    raise ValueError("REPORT_GENERATION_STATUS_INVALID")


def create_report_cli_application() -> SqlAlchemyReportCliApplication:
    return SqlAlchemyReportCliApplication()


__all__ = [
    "SqlAlchemyReportCliApplication",
    "create_report_cli_application",
]
