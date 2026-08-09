"""Transaction-neutral SQLAlchemy persistence for Stage 8 report inputs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stock_research_agent.db.models.knowledge import CitationAnchor
from stock_research_agent.db.models.reports import (
    ReportBlockRow,
    ReportCitationBinding,
    ReportClaimBinding,
    ReportEvidenceBinding,
    ReportGenerationRun,
    ReportPolicy,
    ReportReflectionFinding,
    ReportReflectionRun,
    ReportReleaseGateRow,
    ReportRequest,
    ReportRevisionRun,
    ReportSectionRow,
    ReportTemplateVersion,
    ResearchReport,
    RuntimeReflectionPolicy,
)
from stock_research_agent.db.models.research_agent import (
    ClaimEvidenceLink,
    ResearchAgentRun,
    ResearchClaim,
    ResearchEvidence,
    ResearchPackage,
    ResearchRequest,
)
from stock_research_agent.db.models.security_master import Security
from stock_research_agent.db.repositories.research_agent import (
    _claim_record,
    _evidence_record,
    _link_record,
    _package_record,
    _request_record,
    _run_record,
)
from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    CitationVerification,
)
from stock_research_agent.domain.reports.bindings import (
    ReportCitationBindingWrite,
    ReportClaimBindingRole,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
    VisibleReferenceKind,
)
from stock_research_agent.domain.reports.enums import ReportSection
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunRecord,
    ReportGenerationRunWrite,
    ReportGenerationTransition,
)
from stock_research_agent.domain.reports.reflection import (
    ReportReflectionCompletion,
    ReportReflectionFindingRecord,
    ReportReflectionFindingWrite,
    ReportReflectionResult,
    ReportReflectionRunRecord,
    ReportReflectionRunWrite,
)
from stock_research_agent.domain.reports.reflection_policy import (
    RuntimeReflectionPolicyRecord,
)
from stock_research_agent.domain.reports.release_gate import (
    ReportReleaseGateRecord,
    ReportReleaseGateWrite,
)
from stock_research_agent.domain.reports.reporting import (
    ResearchReportAggregate,
    ResearchReportAggregateWrite,
    ResearchReportRecord,
)
from stock_research_agent.domain.reports.revision import (
    ReportRevisionCompletion,
    ReportRevisionResult,
    ReportRevisionRunRecord,
    ReportRevisionRunWrite,
)
from stock_research_agent.domain.reports.schemas import (
    PersistedReportInput,
    ReportInputManifest,
    ReportPolicyRecord,
    ReportPolicyWrite,
    ReportRequestRecord,
    ReportRequestWrite,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
    ReportTemplateVersionWrite,
)
from stock_research_agent.domain.research_agent.enums import EvidenceRole
from stock_research_agent.domain.research_agent.schemas import Page, PageRequest


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _binding_block_id(
    values: tuple[ReportEvidenceBindingWrite, ...],
    binding_id: UUID,
) -> UUID:
    for value in values:
        if value.id == binding_id:
            return value.report_block_id
    raise ValueError("REPORT_CITATION_EVIDENCE_BINDING_NOT_FOUND")


class SqlAlchemyReportRepository:
    """Read exact Stage 7 inputs and persist only Stage 8 request rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_policy(self, version: str) -> ReportPolicyRecord | None:
        row = self._session.scalar(select(ReportPolicy).where(ReportPolicy.version == version))
        return None if row is None else _report_policy_record(row)

    def add_policy(self, value: ReportPolicyWrite) -> ReportPolicyRecord:
        row = ReportPolicy(
            version=value.version,
            checksum=value.checksum,
            definition=value.model_dump(
                mode="json",
                exclude={"version", "checksum"},
            ),
        )
        self._session.add(row)
        self._session.flush()
        return _report_policy_record(row)

    def get_template(
        self,
        name: str,
        version: str,
        locale: object,
    ) -> ReportTemplateVersionRecord | None:
        locale_value = getattr(locale, "value", locale)
        row = self._session.scalar(
            select(ReportTemplateVersion).where(
                ReportTemplateVersion.name == name,
                ReportTemplateVersion.version == version,
                ReportTemplateVersion.locale == locale_value,
            )
        )
        return None if row is None else _report_template_record(row)

    def add_template(
        self,
        value: ReportTemplateVersionWrite,
    ) -> ReportTemplateVersionRecord:
        row = ReportTemplateVersion(
            name=value.name,
            version=value.version,
            report_type=value.report_type.value,
            locale=value.locale.value,
            template_schema_version=value.template_schema_version,
            status=value.status.value,
            checksum=value.checksum,
            definition=value.model_dump(
                mode="json",
                exclude={
                    "name",
                    "version",
                    "report_type",
                    "locale",
                    "template_schema_version",
                    "status",
                    "checksum",
                },
            ),
        )
        self._session.add(row)
        self._session.flush()
        return _report_template_record(row)

    def get_package_bundle(
        self,
        research_package_id: UUID,
    ) -> PersistedReportInput | None:
        package_row = self._session.scalar(
            select(ResearchPackage).where(ResearchPackage.id == research_package_id)
        )
        if package_row is None:
            return None
        run_row = self._session.scalar(
            select(ResearchAgentRun).where(ResearchAgentRun.id == package_row.research_agent_run_id)
        )
        request_row = self._session.scalar(
            select(ResearchRequest).where(ResearchRequest.id == package_row.request_id)
        )
        security_row = self._session.scalar(
            select(Security).where(Security.id == package_row.security_id)
        )
        if run_row is None or request_row is None or security_row is None:
            return None
        claim_rows = self._session.scalars(
            select(ResearchClaim)
            .where(ResearchClaim.research_agent_run_id == package_row.research_agent_run_id)
            .order_by(ResearchClaim.id)
        ).all()
        evidence_rows = self._session.scalars(
            select(ResearchEvidence)
            .where(ResearchEvidence.research_agent_run_id == package_row.research_agent_run_id)
            .order_by(ResearchEvidence.id)
        ).all()
        link_rows = self._session.scalars(
            select(ClaimEvidenceLink)
            .where(ClaimEvidenceLink.research_agent_run_id == package_row.research_agent_run_id)
            .order_by(ClaimEvidenceLink.id)
        ).all()
        citation_ids = tuple(
            sorted(
                {row.citation_id for row in evidence_rows if row.citation_id is not None},
                key=str,
            )
        )
        citation_rows = self._session.scalars(
            select(CitationAnchor)
            .where(CitationAnchor.id.in_(citation_ids))
            .order_by(CitationAnchor.id)
        ).all()
        citations = tuple(_citation_record(row) for row in citation_rows)
        evidence_status = {
            row.citation_id: row.status for row in evidence_rows if row.citation_id is not None
        }
        verifications = tuple(
            CitationVerification(
                citation_id=row.id,
                status=(
                    CitationStatus.VALID
                    if evidence_status.get(row.id) == "VALID"
                    else CitationStatus.INVALID
                ),
            )
            for row in citation_rows
        )
        return PersistedReportInput(
            package=_package_record(package_row),
            run=_run_record(run_row),
            request=_request_record(request_row),
            issuer_id=security_row.issuer_id,
            claims=tuple(_claim_record(row) for row in claim_rows),
            evidence=tuple(_evidence_record(row) for row in evidence_rows),
            links=tuple(_link_record(row) for row in link_rows),
            citations=citations,
            citation_verifications=verifications,
        )

    def add_request(self, value: ReportRequestWrite) -> ReportRequestRecord:
        manifest = value.manifest
        row = ReportRequest(
            id=value.id,
            research_package_id=manifest.research_package_id,
            research_agent_run_id=manifest.research_agent_run_id,
            research_request_id=manifest.research_request_id,
            security_id=manifest.security_id,
            issuer_id=manifest.issuer_id,
            snapshot_id=manifest.snapshot_id,
            research_as_of_time=manifest.research_as_of_time,
            report_type=value.report_type.value,
            report_locale=value.report_locale.value,
            template_name=value.template_name,
            template_version=value.template_version,
            report_policy_version=value.report_policy_version,
            reflection_policy_version=value.reflection_policy_version,
            requested_sections=[item.value for item in value.requested_sections],
            include_evidence_appendix=value.include_evidence_appendix,
            include_claim_index=value.include_claim_index,
            max_excerpt_length=value.max_excerpt_length,
            manifest_schema_version=manifest.manifest_schema_version,
            manifest=manifest.model_dump(mode="json"),
            manifest_checksum=manifest.canonical_payload_checksum,
            package_checksum=manifest.package_checksum,
            claims_checksum=manifest.claims_checksum,
            evidence_checksum=manifest.evidence_checksum,
            links_checksum=manifest.links_checksum,
            citations_checksum=manifest.citations_checksum,
            lineage_checksum=manifest.lineage_checksum,
            idempotency_key=value.idempotency_key,
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _request_record_from_report(row)

    def get_request(self, request_id: UUID) -> ReportRequestRecord | None:
        row = self._session.scalar(select(ReportRequest).where(ReportRequest.id == request_id))
        return None if row is None else _request_record_from_report(row)

    def get_runtime_reflection_policy(
        self,
        version: str,
    ) -> RuntimeReflectionPolicyRecord | None:
        row = self._session.scalar(
            select(RuntimeReflectionPolicy).where(RuntimeReflectionPolicy.version == version)
        )
        return None if row is None else _runtime_reflection_policy_record(row)

    def add_runtime_reflection_policy(
        self,
        value: RuntimeReflectionPolicyRecord,
    ) -> RuntimeReflectionPolicyRecord:
        row = RuntimeReflectionPolicy(
            version=value.version,
            checksum=value.checksum,
            definition=value.model_dump(
                mode="json",
                exclude={"version", "checksum"},
            ),
        )
        self._session.add(row)
        self._session.flush()
        return _runtime_reflection_policy_record(row)

    def add_report(
        self,
        value: ResearchReportAggregateWrite,
    ) -> ResearchReportAggregate:
        row = _report_row(value.report)
        self._session.add(row)
        self._session.flush()
        blocks: list[ReportBlockRow] = []
        for section in value.report.structured_content.sections:
            section_id = uuid5(
                NAMESPACE_URL,
                f"{value.report.id}:section:{section.section.value}",
            )
            self._session.add(
                ReportSectionRow(
                    id=section_id,
                    research_report_id=value.report.id,
                    section_key=section.section.value,
                    section_index=section.section_index,
                    title=section.title,
                    status=section.status.value,
                    created_at=value.report.created_at,
                )
            )
            for block in section.blocks:
                blocks.append(
                    ReportBlockRow(
                        id=uuid5(
                            NAMESPACE_URL,
                            f"{value.report.id}:block:{block.block_key}",
                        ),
                        research_report_id=value.report.id,
                        report_section_id=section_id,
                        block_key=block.block_key,
                        block_index=block.block_index,
                        block_type=block.block_type.value,
                        status=block.status.value,
                        text_content=block.text,
                        payload=block.payload,
                        created_at=value.report.created_at,
                    )
                )
        self._session.flush()
        self._session.add_all(blocks)
        self._session.flush()
        factual = any(
            block.block_type.value in {"METRIC_TABLE", "CONFLICT"}
            or any(key in block.payload for key in ("claim_id", "statement_code", "support_status"))
            for section in value.report.structured_content.sections
            for block in section.blocks
        )
        if factual and not value.claim_bindings:
            raise ValueError("REPORT_FACTUAL_BINDINGS_REQUIRED")
        self.add_bindings(
            value.report.id,
            value.claim_bindings,
            value.evidence_bindings,
            value.citation_bindings,
        )
        return ResearchReportAggregate(
            report=_research_report_record(row),
            claim_bindings=value.claim_bindings,
            evidence_bindings=value.evidence_bindings,
            citation_bindings=value.citation_bindings,
        )

    def get_report(self, report_id: UUID) -> ResearchReportAggregate | None:
        row = self._session.get(ResearchReport, report_id)
        return None if row is None else self._report_aggregate(row)

    def _report_aggregate(self, row: ResearchReport) -> ResearchReportAggregate:
        claim_rows = self._session.scalars(
            select(ReportClaimBinding)
            .where(ReportClaimBinding.research_report_id == row.id)
            .order_by(ReportClaimBinding.id)
        ).all()
        evidence_rows = self._session.scalars(
            select(ReportEvidenceBinding)
            .where(ReportEvidenceBinding.research_report_id == row.id)
            .order_by(ReportEvidenceBinding.id)
        ).all()
        citation_rows = self._session.scalars(
            select(ReportCitationBinding)
            .where(ReportCitationBinding.research_report_id == row.id)
            .order_by(ReportCitationBinding.id)
        ).all()
        return ResearchReportAggregate(
            report=_research_report_record(row),
            claim_bindings=tuple(
                ReportClaimBindingWrite(
                    id=value.id,
                    report_block_id=value.report_block_id,
                    claim_id=value.claim_id,
                    role=ReportClaimBindingRole(value.binding_role),
                    sentence_index=value.sentence_index,
                    item_or_row_key=value.item_or_row_key,
                    created_at=_utc(value.created_at),
                )
                for value in claim_rows
            ),
            evidence_bindings=tuple(
                ReportEvidenceBindingWrite(
                    id=value.id,
                    report_block_id=value.report_block_id,
                    report_claim_binding_id=value.report_claim_binding_id,
                    claim_evidence_link_id=value.claim_evidence_link_id,
                    evidence_id=value.evidence_id,
                    role=EvidenceRole(value.binding_role),
                    visible_reference_kind=VisibleReferenceKind(value.visible_reference_kind),
                    visible_reference=value.visible_reference,
                    item_or_row_key=value.item_or_row_key,
                    citation_id=value.citation_id,
                    source_record_id=value.source_record_id,
                    source_checksum=value.source_checksum,
                    created_at=_utc(value.created_at),
                )
                for value in evidence_rows
            ),
            citation_bindings=tuple(
                ReportCitationBindingWrite(
                    id=value.id,
                    report_evidence_binding_id=value.report_evidence_binding_id,
                    citation_id=value.citation_id,
                    document_version_id=value.document_version_id,
                    visible_reference=value.visible_reference,
                    locator_summary=value.locator_summary,
                    rendered_excerpt=value.rendered_excerpt,
                    rendered_excerpt_checksum=value.rendered_excerpt_checksum,
                    citation_status=cast(
                        Literal[CitationStatus.VALID],
                        CitationStatus(value.citation_status),
                    ),
                    created_at=_utc(value.created_at),
                )
                for value in citation_rows
            ),
        )

    def list_versions(
        self,
        generation_run_id: UUID,
    ) -> tuple[ResearchReportRecord, ...]:
        rows = self._session.scalars(
            select(ResearchReport)
            .where(ResearchReport.report_generation_run_id == generation_run_id)
            .order_by(ResearchReport.report_version, ResearchReport.id)
        ).all()
        return tuple(_research_report_record(row) for row in rows)

    def add_bindings(
        self,
        report_id: UUID,
        claim_bindings: tuple[ReportClaimBindingWrite, ...],
        evidence_bindings: tuple[ReportEvidenceBindingWrite, ...],
        citation_bindings: tuple[ReportCitationBindingWrite, ...],
    ) -> None:
        if self._session.get(ResearchReport, report_id) is None:
            raise LookupError("RESEARCH_REPORT_NOT_FOUND")
        self._session.add_all(
            [
                ReportClaimBinding(
                    id=value.id,
                    research_report_id=report_id,
                    report_block_id=value.report_block_id,
                    claim_id=value.claim_id,
                    binding_role=value.role.value,
                    sentence_index=value.sentence_index,
                    item_or_row_key=value.item_or_row_key,
                    created_at=value.created_at,
                )
                for value in claim_bindings
            ]
        )
        self._session.flush()
        self._session.add_all(
            [
                ReportEvidenceBinding(
                    id=value.id,
                    research_report_id=report_id,
                    report_block_id=value.report_block_id,
                    report_claim_binding_id=value.report_claim_binding_id,
                    claim_evidence_link_id=value.claim_evidence_link_id,
                    evidence_id=value.evidence_id,
                    binding_role=value.role.value,
                    visible_reference_kind=value.visible_reference_kind.value,
                    visible_reference=value.visible_reference,
                    item_or_row_key=value.item_or_row_key,
                    citation_id=value.citation_id,
                    source_record_id=value.source_record_id,
                    source_checksum=value.source_checksum,
                    created_at=value.created_at,
                )
                for value in evidence_bindings
            ]
        )
        self._session.flush()
        self._session.add_all(
            [
                ReportCitationBinding(
                    id=value.id,
                    research_report_id=report_id,
                    report_block_id=_binding_block_id(
                        evidence_bindings,
                        value.report_evidence_binding_id,
                    ),
                    report_evidence_binding_id=value.report_evidence_binding_id,
                    citation_id=value.citation_id,
                    document_version_id=value.document_version_id,
                    visible_reference=value.visible_reference,
                    locator_summary=value.locator_summary,
                    rendered_excerpt=value.rendered_excerpt,
                    rendered_excerpt_checksum=value.rendered_excerpt_checksum,
                    citation_status=value.citation_status.value,
                    created_at=value.created_at,
                )
                for value in citation_bindings
            ]
        )
        self._session.flush()

    def get_report_view(self, report_id: UUID) -> object | None:
        row = self._session.get(ResearchReport, report_id)
        return None if row is None else _report_view(row)

    def list_section_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportSectionRow,
            ReportSectionRow.research_report_id == report_id,
            (ReportSectionRow.section_index, ReportSectionRow.id),
            page,
            _row_view,
        )

    def list_block_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportBlockRow,
            ReportBlockRow.research_report_id == report_id,
            (ReportBlockRow.report_section_id, ReportBlockRow.block_index),
            page,
            _row_view,
        )

    def list_claim_binding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportClaimBinding,
            ReportClaimBinding.research_report_id == report_id,
            (ReportClaimBinding.report_block_id, ReportClaimBinding.id),
            page,
            _row_view,
        )

    def list_evidence_binding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportEvidenceBinding,
            ReportEvidenceBinding.research_report_id == report_id,
            (ReportEvidenceBinding.report_block_id, ReportEvidenceBinding.id),
            page,
            _row_view,
        )

    def list_citation_binding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportCitationBinding,
            ReportCitationBinding.research_report_id == report_id,
            (ReportCitationBinding.report_block_id, ReportCitationBinding.id),
            page,
            _row_view,
        )

    def list_reflection_run_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportReflectionRun,
            ReportReflectionRun.research_report_id == report_id,
            (ReportReflectionRun.round_number, ReportReflectionRun.id),
            page,
            _row_view,
        )

    def list_finding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportReflectionFinding,
            ReportReflectionFinding.research_report_id == report_id,
            (
                ReportReflectionFinding.report_reflection_run_id,
                ReportReflectionFinding.severity,
                ReportReflectionFinding.id,
            ),
            page,
            _row_view,
        )

    def list_revision_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        return self._page(
            ReportRevisionRun,
            ReportRevisionRun.source_report_id == report_id,
            (ReportRevisionRun.created_at, ReportRevisionRun.id),
            page,
            _row_view,
        )

    def get_release_gate_view(self, report_id: UUID) -> object | None:
        row = self._session.scalar(
            select(ReportReleaseGateRow).where(
                ReportReleaseGateRow.candidate_report_id == report_id
            )
        )
        return None if row is None else _row_view(row)

    def _page(
        self,
        model: type[Any],
        predicate: Any,
        ordering: tuple[Any, ...],
        page: PageRequest,
        projector: Callable[[Any], object],
    ) -> Page[object]:
        total = self._session.scalar(select(func.count()).select_from(model).where(predicate))
        rows = self._session.scalars(
            select(model).where(predicate).order_by(*ordering).limit(page.limit).offset(page.offset)
        ).all()
        return Page[object](
            items=tuple(projector(row) for row in rows),
            limit=page.limit,
            offset=page.offset,
            total=int(total or 0),
        )


class SqlAlchemyReportGenerationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(
        self,
        value: ReportGenerationRunWrite,
    ) -> ReportGenerationRunRecord:
        row = ReportGenerationRun(
            **value.model_dump(
                mode="python",
                exclude={"created_at", "updated_at", "terminal_at"},
            ),
            created_at=value.created_at,
            updated_at=value.updated_at,
            terminal_at=value.terminal_at,
        )
        self._session.add(row)
        self._session.flush()
        return _generation_run_record(row)

    def get_run(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> ReportGenerationRunRecord | None:
        statement = select(ReportGenerationRun).where(ReportGenerationRun.id == run_id)
        if for_update:
            statement = statement.with_for_update()
        row = self._session.scalar(statement)
        return None if row is None else _generation_run_record(row)

    def find_reusable_run(
        self,
        idempotency_key: str,
    ) -> ReportGenerationRunRecord | None:
        row = self._session.scalar(
            select(ReportGenerationRun)
            .where(
                ReportGenerationRun.idempotency_key == idempotency_key,
                ReportGenerationRun.status.in_(
                    ("CREATED", "RUNNING", "COMPLETED", "PARTIAL", "BLOCKED")
                ),
            )
            .order_by(ReportGenerationRun.created_at, ReportGenerationRun.id)
        )
        return None if row is None else _generation_run_record(row)

    def transition(
        self,
        run_id: UUID,
        value: ReportGenerationTransition,
    ) -> ReportGenerationRunRecord:
        row = self._session.scalar(
            select(ReportGenerationRun).where(ReportGenerationRun.id == run_id).with_for_update()
        )
        if row is None:
            raise LookupError("REPORT_GENERATION_RUN_NOT_FOUND")
        if row.status != value.expected_status.value:
            raise RuntimeError("REPORT_GENERATION_STATUS_CONFLICT")
        row.status = value.target_status.value
        row.warning_count = value.warning_count
        row.blocked_reason_code = value.blocked_reason_code
        row.error_code = value.error_code
        row.safe_error_message = value.safe_error_message
        row.updated_at = value.changed_at
        if value.target_status.value != "RUNNING":
            row.terminal_at = value.changed_at
        self._session.flush()
        return _generation_run_record(row)


class SqlAlchemyReportReflectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(
        self,
        value: ReportReflectionRunWrite,
    ) -> ReportReflectionRunRecord:
        row = ReportReflectionRun(
            id=value.id,
            research_report_id=value.research_report_id,
            reflection_policy_version=value.reflection_policy_version,
            engine_name=value.engine_name,
            engine_version=value.engine_version,
            round_number=value.round_number,
            status=value.status.value,
            input_report_checksum=value.input_report_checksum,
            total_finding_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            created_at=value.started_at,
        )
        self._session.add(row)
        self._session.flush()
        return _reflection_run_record(row)

    def get_result(self, run_id: UUID) -> ReportReflectionResult | None:
        row = self._session.get(ReportReflectionRun, run_id)
        if row is None or row.status == "RUNNING":
            return None
        finding_rows = self._session.scalars(
            select(ReportReflectionFinding)
            .where(ReportReflectionFinding.report_reflection_run_id == run_id)
            .order_by(ReportReflectionFinding.id)
        ).all()
        findings: list[ReportReflectionFindingRecord] = []
        for finding_row in finding_rows:
            record = _reflection_finding_record(finding_row)
            section = (
                None
                if finding_row.report_section_id is None
                else self._session.get(
                    ReportSectionRow,
                    finding_row.report_section_id,
                )
            )
            block = (
                None
                if finding_row.report_block_id is None
                else self._session.get(
                    ReportBlockRow,
                    finding_row.report_block_id,
                )
            )
            findings.append(
                record.model_copy(
                    update={
                        "report_section": (
                            None if section is None else ReportSection(section.section_key)
                        ),
                        "block_key": None if block is None else block.block_key,
                    }
                )
            )
        return ReportReflectionResult(
            run=_reflection_run_record(row),
            finding_ids=tuple(value.id for value in findings),
            findings=tuple(findings),
        )

    def complete_run(
        self,
        run_id: UUID,
        result: ReportReflectionCompletion,
        findings: tuple[ReportReflectionFindingWrite, ...],
    ) -> ReportReflectionResult:
        row = self._session.scalar(
            select(ReportReflectionRun).where(ReportReflectionRun.id == run_id).with_for_update()
        )
        if row is None:
            raise LookupError("REPORT_REFLECTION_RUN_NOT_FOUND")
        if len(findings) != result.total_finding_count:
            raise ValueError("REPORT_REFLECTION_FINDING_COUNT_MISMATCH")
        finding_rows = tuple(_reflection_finding_row(item) for item in findings)
        self._session.add_all(finding_rows)
        row.status = result.target_status.value
        row.total_finding_count = result.total_finding_count
        row.critical_count = result.critical_count
        row.high_count = result.high_count
        row.medium_count = result.medium_count
        row.low_count = result.low_count
        row.blocked_reason_code = result.blocked_reason_code
        row.error_code = result.error_code
        row.safe_error_message = result.safe_error_message
        row.completed_at = result.completed_at
        self._session.flush()
        return ReportReflectionResult(
            run=_reflection_run_record(row),
            finding_ids=tuple(item.id for item in findings),
            findings=tuple(_reflection_finding_record(item) for item in finding_rows),
        )


class SqlAlchemyReportRevisionRepository:
    def __init__(
        self,
        session: Session,
        reports: SqlAlchemyReportRepository | None = None,
    ) -> None:
        self._session = session
        self._reports = reports or SqlAlchemyReportRepository(session)

    def create_run(
        self,
        value: ReportRevisionRunWrite,
    ) -> ReportRevisionRunRecord:
        row = ReportRevisionRun(
            id=value.id,
            source_report_id=value.source_report_id,
            source_reflection_run_id=value.source_reflection_run_id,
            report_policy_version=value.report_policy_version,
            engine_name=value.engine_name,
            engine_version=value.engine_version,
            revision_round=value.revision_round,
            status=value.status.value,
            actions=[],
            applied_finding_ids=[],
            unresolved_finding_ids=[],
            created_at=value.started_at,
        )
        self._session.add(row)
        self._session.flush()
        return _revision_run_record(row)

    def complete_run(
        self,
        run_id: UUID,
        result: ReportRevisionCompletion,
        target: ResearchReportAggregateWrite | None,
    ) -> ReportRevisionResult:
        row = self._session.scalar(
            select(ReportRevisionRun).where(ReportRevisionRun.id == run_id).with_for_update()
        )
        if row is None:
            raise LookupError("REPORT_REVISION_RUN_NOT_FOUND")
        if target is not None:
            persisted = self._reports.add_report(target)
            if result.target_report_id != persisted.report.id:
                raise ValueError("REPORT_REVISION_TARGET_ID_MISMATCH")
        row.status = result.target_status.value
        row.target_report_id = result.target_report_id
        row.actions = [item.model_dump(mode="json") for item in result.actions]
        row.applied_finding_ids = [str(item) for item in result.applied_finding_ids]
        row.unresolved_finding_ids = [str(item) for item in result.unresolved_finding_ids]
        row.blocked_reason_code = result.blocked_reason_code
        row.error_code = result.error_code
        row.safe_error_message = result.safe_error_message
        row.completed_at = result.completed_at
        self._session.flush()
        return ReportRevisionResult(run=_revision_run_record(row))


class SqlAlchemyReportReleaseGateRepository:
    def __init__(
        self,
        session: Session,
        reports: SqlAlchemyReportRepository | None = None,
    ) -> None:
        self._session = session
        self._reports = reports or SqlAlchemyReportRepository(session)

    def add_gate(
        self,
        value: ReportReleaseGateWrite,
    ) -> ReportReleaseGateRecord:
        sealed_id = value.sealed_report_id
        sealed = value.decision.sealed_report
        if sealed is not None:
            persisted = self._reports.add_report(sealed)
            if sealed_id != persisted.report.id:
                raise ValueError("REPORT_RELEASE_SEALED_ID_MISMATCH")
        row = ReportReleaseGateRow(
            id=value.id,
            candidate_report_id=value.decision.candidate_report_id,
            round_two_reflection_run_id=(value.decision.round_two_reflection_run_id),
            sealed_report_id=sealed_id,
            gate_version=value.decision.gate_version,
            input_manifest_checksum=value.decision.input_manifest_checksum,
            report_checksum=value.decision.report_checksum,
            internal_release_status=value.decision.internal_release_status.value,
            requirements=[item.model_dump(mode="json") for item in value.decision.requirements],
            reason_codes=list(value.decision.reason_codes),
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return ReportReleaseGateRecord.model_validate(value.model_dump(mode="python"))


def _citation_record(row: CitationAnchor) -> CitationAnchorRecord:
    locator = row.locator
    return CitationAnchorRecord.model_validate(
        {
            "id": row.id,
            "document_version_id": row.document_version_id,
            "parse_run_id": row.parse_run_id,
            "page_id": row.page_id,
            "section_id": row.section_id,
            "chunk_id": row.chunk_id,
            "locator_type": row.locator_type,
            "start_page": locator.get("start_page"),
            "end_page": locator.get("end_page"),
            "html_anchor": locator.get("html_anchor"),
            "json_pointer": locator.get("json_pointer"),
            "start_offset": locator.get("start_offset"),
            "end_offset": locator.get("end_offset"),
            "excerpt": row.excerpt,
            "excerpt_checksum": row.excerpt_checksum,
            "canonical_text_checksum": row.canonical_text_checksum,
            "document_checksum": row.document_checksum,
            "locator_checksum": row.locator_checksum,
            "citation_version": row.citation_version,
            "parser_version": row.parser_version,
            "sanitizer_version": row.sanitizer_version,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _request_record_from_report(row: ReportRequest) -> ReportRequestRecord:
    return ReportRequestRecord.model_validate(
        {
            "id": row.id,
            "manifest": ReportInputManifest.model_validate(
                row.manifest,
                strict=False,
            ),
            "report_type": row.report_type,
            "report_locale": row.report_locale,
            "template_name": row.template_name,
            "template_version": row.template_version,
            "report_policy_version": row.report_policy_version,
            "reflection_policy_version": row.reflection_policy_version,
            "requested_sections": row.requested_sections,
            "include_evidence_appendix": row.include_evidence_appendix,
            "include_claim_index": row.include_claim_index,
            "max_excerpt_length": row.max_excerpt_length,
            "idempotency_key": row.idempotency_key,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _report_policy_record(row: ReportPolicy) -> ReportPolicyRecord:
    return ReportPolicyRecord.model_validate(
        {
            "version": row.version,
            "checksum": row.checksum,
            **row.definition,
        },
        strict=False,
    )


def _report_template_record(
    row: ReportTemplateVersion,
) -> ReportTemplateVersionRecord:
    return ReportTemplateVersionRecord.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "version": row.version,
            "report_type": row.report_type,
            "locale": row.locale,
            "template_schema_version": row.template_schema_version,
            "status": row.status,
            "checksum": row.checksum,
            "created_at": _utc(row.created_at),
            **row.definition,
        },
        strict=False,
    )


def _runtime_reflection_policy_record(
    row: RuntimeReflectionPolicy,
) -> RuntimeReflectionPolicyRecord:
    return RuntimeReflectionPolicyRecord.model_validate(
        {
            "version": row.version,
            "checksum": row.checksum,
            **row.definition,
        },
        strict=False,
    )


def _generation_run_record(
    row: ReportGenerationRun,
) -> ReportGenerationRunRecord:
    return ReportGenerationRunRecord.model_validate(
        _contract_row_values(row),
        strict=False,
    )


def _report_row(value: ResearchReportRecord) -> ResearchReport:
    payload = value.model_dump(
        mode="python",
        exclude={
            "research_as_of_time",
            "created_at",
            "structured_content",
        },
    )
    return ResearchReport(
        **payload,
        research_as_of_time=value.research_as_of_time,
        structured_content=value.structured_content.model_dump(mode="json"),
        created_at=value.created_at,
    )


def _research_report_record(row: ResearchReport) -> ResearchReportRecord:
    return ResearchReportRecord.model_validate(
        _contract_row_values(row),
        strict=False,
    )


def _report_view(row: ResearchReport) -> dict[str, object]:
    return _row_view(row)


def _row_view(row: Any) -> dict[str, object]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _contract_row_values(row: Any) -> dict[str, object]:
    values = _row_view(row)
    for key, value in tuple(values.items()):
        if isinstance(value, datetime):
            values[key] = _utc(value)
    return values


def _reflection_run_record(
    row: ReportReflectionRun,
) -> ReportReflectionRunRecord:
    return ReportReflectionRunRecord.model_validate(
        {
            "id": row.id,
            "research_report_id": row.research_report_id,
            "reflection_policy_version": row.reflection_policy_version,
            "engine_name": row.engine_name,
            "engine_version": row.engine_version,
            "round_number": row.round_number,
            "input_report_checksum": row.input_report_checksum,
            "status": row.status,
            "started_at": _utc(row.created_at),
            "total_finding_count": row.total_finding_count,
            "critical_count": row.critical_count,
            "high_count": row.high_count,
            "medium_count": row.medium_count,
            "low_count": row.low_count,
            "blocked_reason_code": row.blocked_reason_code,
            "error_code": row.error_code,
            "safe_error_message": row.safe_error_message,
            "completed_at": (None if row.completed_at is None else _utc(row.completed_at)),
        },
        strict=False,
    )


def _reflection_finding_row(
    value: ReportReflectionFindingWrite,
) -> ReportReflectionFinding:
    return ReportReflectionFinding(
        id=value.id,
        report_reflection_run_id=value.reflection_run_id,
        research_report_id=value.research_report_id,
        report_section_id=value.report_section_id,
        report_block_id=value.report_block_id,
        claim_id=value.claim_id,
        evidence_id=value.evidence_id,
        citation_id=value.citation_id,
        finding_code=value.finding_code,
        category=value.category.value,
        severity=value.severity.value,
        description=value.description,
        remediation_code=value.remediation_code,
        blocking=value.blocking,
        created_at=value.created_at,
    )


def _reflection_finding_record(
    row: ReportReflectionFinding,
) -> ReportReflectionFindingRecord:
    return ReportReflectionFindingRecord.model_validate(
        {
            "id": row.id,
            "reflection_run_id": row.report_reflection_run_id,
            "research_report_id": row.research_report_id,
            "report_section_id": row.report_section_id,
            "report_block_id": row.report_block_id,
            "claim_id": row.claim_id,
            "evidence_id": row.evidence_id,
            "citation_id": row.citation_id,
            "finding_code": row.finding_code,
            "category": row.category,
            "severity": row.severity,
            "description": row.description,
            "remediation_code": row.remediation_code,
            "blocking": row.blocking,
            "created_at": _utc(row.created_at),
        },
        strict=False,
    )


def _revision_run_record(
    row: ReportRevisionRun,
) -> ReportRevisionRunRecord:
    return ReportRevisionRunRecord.model_validate(
        {
            "id": row.id,
            "source_report_id": row.source_report_id,
            "source_reflection_run_id": row.source_reflection_run_id,
            "target_report_id": row.target_report_id,
            "report_policy_version": row.report_policy_version,
            "engine_name": row.engine_name,
            "engine_version": row.engine_version,
            "revision_round": row.revision_round,
            "status": row.status,
            "started_at": _utc(row.created_at),
            "actions": row.actions,
            "applied_finding_ids": row.applied_finding_ids,
            "unresolved_finding_ids": row.unresolved_finding_ids,
            "blocked_reason_code": row.blocked_reason_code,
            "error_code": row.error_code,
            "safe_error_message": row.safe_error_message,
            "completed_at": (None if row.completed_at is None else _utc(row.completed_at)),
        },
        strict=False,
    )
