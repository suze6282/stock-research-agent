"""Deterministic subtractive and disclosure-only report revision."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Literal, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, JsonValue, model_validator

from stock_research_agent.domain.reports.binding_schemas import (
    ReportCitationBindingWrite,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
    VisibleReferenceKind,
)
from stock_research_agent.domain.reports.checksums import (
    ReportChecksumContext,
    combined_report_checksum,
    markdown_checksum,
    structured_report_checksum,
)
from stock_research_agent.domain.reports.enums import ReportSection
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
    DeterministicMarkdownRenderer,
)
from stock_research_agent.domain.reports.references import (
    ReferenceKind,
    ReportReferenceAllocator,
)
from stock_research_agent.domain.reports.reflection import (
    ReportReflectionFindingRecord,
    ReportReflectionResult,
    ReportReflectionRunRecord,
    ReportReflectionStatus,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ReportSectionStatus,
    ResearchReportAggregate,
    ResearchReportRecord,
    ResearchReportStatus,
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    Code,
    FrozenReportContract,
    ReportPolicyRecord,
    Version,
)

REVISION_ENGINE_NAME = "deterministic-report-revision"
REVISION_ENGINE_VERSION = "deterministic-report-revision-v1"


class ReportRevisionActionCode(StrEnum):
    DELETE_UNBOUND_FACT_BLOCK = "DELETE_UNBOUND_FACT_BLOCK"
    DELETE_UNSUPPORTED_FACT_BLOCK = "DELETE_UNSUPPORTED_FACT_BLOCK"
    DOWNGRADE_PARTIAL_LANGUAGE = "DOWNGRADE_PARTIAL_LANGUAGE"
    MOVE_CONFLICT_TO_CONFLICTS = "MOVE_CONFLICT_TO_CONFLICTS"
    MOVE_UNSUPPORTED_TO_APPENDIX = "MOVE_UNSUPPORTED_TO_APPENDIX"
    MOVE_BLOCKED_TO_LIMITATIONS = "MOVE_BLOCKED_TO_LIMITATIONS"
    ADD_DATA_QUALITY_FROM_EXISTING_STATE = "ADD_DATA_QUALITY_FROM_EXISTING_STATE"
    ADD_LIMITATIONS_FROM_EXISTING_STATE = "ADD_LIMITATIONS_FROM_EXISTING_STATE"
    RENUMBER_EXISTING_REFERENCES = "RENUMBER_EXISTING_REFERENCES"
    REMOVE_INVALID_CITATION_BLOCK = "REMOVE_INVALID_CITATION_BLOCK"
    REMOVE_FORBIDDEN_ADVICE_TEXT = "REMOVE_FORBIDDEN_ADVICE_TEXT"
    TRUNCATE_EXISTING_EXCERPT = "TRUNCATE_EXISTING_EXCERPT"
    FIX_DETERMINISTIC_FORMAT = "FIX_DETERMINISTIC_FORMAT"


class ReportRevisionAction(FrozenReportContract):
    finding_id: UUID
    action_code: ReportRevisionActionCode
    block_key: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_.-]{2,127}$",
    )


class ReportRevisionStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


TERMINAL_REVISION_STATUSES = frozenset(
    {
        ReportRevisionStatus.COMPLETED,
        ReportRevisionStatus.PARTIAL,
        ReportRevisionStatus.BLOCKED,
        ReportRevisionStatus.FAILED,
    }
)


class ReportRevisionRunWrite(FrozenReportContract):
    id: UUID
    source_report_id: UUID
    source_reflection_run_id: UUID
    report_policy_version: Version
    engine_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    engine_version: Version
    revision_round: Literal[1]
    status: Literal[ReportRevisionStatus.RUNNING]
    started_at: AwareUtcDateTime


class ReportRevisionRunRecord(FrozenReportContract):
    id: UUID
    source_report_id: UUID
    source_reflection_run_id: UUID
    report_policy_version: Version
    engine_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    engine_version: Version
    revision_round: Literal[1]
    status: ReportRevisionStatus
    started_at: AwareUtcDateTime
    target_report_id: UUID | None = None
    actions: tuple[ReportRevisionAction, ...] = Field(
        default=(),
        max_length=10_000,
    )
    applied_finding_ids: tuple[UUID, ...] = Field(
        default=(),
        max_length=10_000,
    )
    unresolved_finding_ids: tuple[UUID, ...] = Field(
        default=(),
        max_length=10_000,
    )
    blocked_reason_code: Code | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    completed_at: AwareUtcDateTime | None = None

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        _validate_revision_outcome(
            status=self.status,
            target_report_id=self.target_report_id,
            actions=self.actions,
            applied_finding_ids=self.applied_finding_ids,
            unresolved_finding_ids=self.unresolved_finding_ids,
            blocked_reason_code=self.blocked_reason_code,
            error_code=self.error_code,
            safe_error_message=self.safe_error_message,
            completed_at=self.completed_at,
        )
        return self


class ReportRevisionCompletion(FrozenReportContract):
    target_status: ReportRevisionStatus
    target_report_id: UUID | None = None
    actions: tuple[ReportRevisionAction, ...] = Field(
        default=(),
        max_length=10_000,
    )
    applied_finding_ids: tuple[UUID, ...] = Field(
        default=(),
        max_length=10_000,
    )
    unresolved_finding_ids: tuple[UUID, ...] = Field(
        default=(),
        max_length=10_000,
    )
    blocked_reason_code: Code | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    completed_at: AwareUtcDateTime

    @model_validator(mode="after")
    def require_terminal_shape(self) -> Self:
        _validate_revision_outcome(
            status=self.target_status,
            target_report_id=self.target_report_id,
            actions=self.actions,
            applied_finding_ids=self.applied_finding_ids,
            unresolved_finding_ids=self.unresolved_finding_ids,
            blocked_reason_code=self.blocked_reason_code,
            error_code=self.error_code,
            safe_error_message=self.safe_error_message,
            completed_at=self.completed_at,
        )
        return self


class ReportRevisionResult(FrozenReportContract):
    run: ReportRevisionRunRecord

    @model_validator(mode="after")
    def require_terminal_run(self) -> Self:
        if self.run.status not in TERMINAL_REVISION_STATUSES:
            raise ValueError("Revision result requires a terminal run")
        return self


class ReportRevisionDraft(FrozenReportContract):
    source_report_id: UUID
    source_report_checksum: Checksum
    engine_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    engine_version: Version
    target: ResearchReportAggregate
    actions: tuple[ReportRevisionAction, ...] = Field(max_length=10_000)
    applied_finding_ids: tuple[UUID, ...] = Field(max_length=10_000)
    unresolved_finding_ids: tuple[UUID, ...] = Field(max_length=10_000)


class ReportRevisionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReportRevisionTransitionError(RuntimeError):
    pass


class ReportRevisionStateMachine:
    def transition(
        self,
        current: ReportRevisionStatus,
        target: ReportRevisionStatus,
    ) -> ReportRevisionStatus:
        if current is not ReportRevisionStatus.RUNNING or target not in TERMINAL_REVISION_STATUSES:
            raise ReportRevisionTransitionError(
                f"REPORT_REVISION_TRANSITION_FORBIDDEN:{current.value}:{target.value}"
            )
        return target


def complete_revision_run(
    run: ReportRevisionRunRecord,
    completion: ReportRevisionCompletion,
) -> ReportRevisionRunRecord:
    target = ReportRevisionStateMachine().transition(
        run.status,
        completion.target_status,
    )
    return ReportRevisionRunRecord.model_validate(
        {
            **run.model_dump(
                mode="python",
                exclude={
                    "status",
                    "target_report_id",
                    "actions",
                    "applied_finding_ids",
                    "unresolved_finding_ids",
                    "blocked_reason_code",
                    "error_code",
                    "safe_error_message",
                    "completed_at",
                },
            ),
            **completion.model_dump(mode="python", exclude={"target_status"}),
            "status": target,
        }
    )


def revision_run_uniqueness_key(
    run: ReportRevisionRunWrite | ReportRevisionRunRecord,
) -> tuple[UUID]:
    return (run.source_report_id,)


def validate_revision_source(
    *,
    source_report_id: UUID,
    reflection: ReportReflectionRunRecord,
) -> None:
    if (
        reflection.research_report_id != source_report_id
        or reflection.round_number != 1
        or reflection.status is not ReportReflectionStatus.FINDINGS
    ):
        raise ReportRevisionTransitionError("REPORT_REVISION_SOURCE_INVALID")


def _validate_revision_outcome(
    *,
    status: ReportRevisionStatus,
    target_report_id: UUID | None,
    actions: tuple[ReportRevisionAction, ...],
    applied_finding_ids: tuple[UUID, ...],
    unresolved_finding_ids: tuple[UUID, ...],
    blocked_reason_code: str | None,
    error_code: str | None,
    safe_error_message: str | None,
    completed_at: object | None,
) -> None:
    action_finding_ids = tuple(action.finding_id for action in actions)
    if action_finding_ids != applied_finding_ids:
        raise ValueError("Revision actions must exactly match applied Findings")
    if len(applied_finding_ids) != len(set(applied_finding_ids)) or len(
        unresolved_finding_ids
    ) != len(set(unresolved_finding_ids)):
        raise ValueError("Revision Finding IDs must be unique")
    if set(applied_finding_ids) & set(unresolved_finding_ids):
        raise ValueError("Applied and unresolved Findings must be disjoint")
    if status is ReportRevisionStatus.RUNNING:
        if (
            target_report_id is not None
            or actions
            or applied_finding_ids
            or unresolved_finding_ids
            or blocked_reason_code is not None
            or error_code is not None
            or safe_error_message is not None
            or completed_at is not None
        ):
            raise ValueError("RUNNING Revision cannot contain terminal outcome")
        return
    if status not in TERMINAL_REVISION_STATUSES or completed_at is None:
        raise ValueError("Revision outcome must be a completed terminal state")
    if status in {ReportRevisionStatus.COMPLETED, ReportRevisionStatus.PARTIAL}:
        if target_report_id is None:
            raise ValueError("Successful Revision requires one target Report")
    elif target_report_id is not None:
        raise ValueError("Blocked or failed Revision cannot have a target Report")
    if status is ReportRevisionStatus.COMPLETED and unresolved_finding_ids:
        raise ValueError("COMPLETED Revision cannot retain unresolved Findings")
    if status is ReportRevisionStatus.PARTIAL and not unresolved_finding_ids:
        raise ValueError("PARTIAL Revision requires unresolved Findings")
    if status is ReportRevisionStatus.BLOCKED:
        if (
            blocked_reason_code is None
            or actions
            or applied_finding_ids
            or not unresolved_finding_ids
        ):
            raise ValueError("BLOCKED Revision requires unresolved-only outcome")
    elif blocked_reason_code is not None:
        raise ValueError("Only BLOCKED Revision can carry a blocked reason")
    if status is ReportRevisionStatus.FAILED:
        if error_code is None or safe_error_message is None or actions or applied_finding_ids:
            raise ValueError("FAILED Revision requires a safe error and no actions")
    elif error_code is not None or safe_error_message is not None:
        raise ValueError("Non-failed Revision cannot contain an error")


ActionHandler = Callable[
    [StructuredReportContent, ReportReflectionFindingRecord, ReportPolicyRecord],
    StructuredReportContent,
]


def _delete_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _delete_block(content, finding.block_key)


def _partial_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _transform_block(content, finding.block_key, _qualify_partial)


def _move_conflict_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _move_block(content, finding.block_key, ReportSection.CONFLICTS)


def _move_unsupported_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _move_block(content, finding.block_key, ReportSection.UNSUPPORTED_CLAIMS)


def _move_blocked_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _move_block(content, finding.block_key, ReportSection.LIMITATIONS)


def _add_data_quality_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _append_disclosure(
        content,
        finding,
        ReportSection.DATA_QUALITY,
        ReportBlockType.WARNING,
        ReportBlockStatus.PARTIAL,
    )


def _add_limitation_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del policy
    return _append_disclosure(
        content,
        finding,
        ReportSection.LIMITATIONS,
        ReportBlockType.LIMITATION,
        ReportBlockStatus.BLOCKED,
    )


def _renumber_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del finding, policy
    return ReportReferenceAllocator().allocate(content).content


def _truncate_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    return _transform_block(
        content,
        finding.block_key,
        lambda block: block.model_copy(
            update={
                "payload": _truncate_excerpts(
                    block.payload,
                    policy.max_excerpt_length,
                )
            }
        ),
    )


def _format_handler(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    policy: ReportPolicyRecord,
) -> StructuredReportContent:
    del finding, policy
    return _canonicalize(content)


REVISION_ACTION_HANDLERS: dict[ReportRevisionActionCode, ActionHandler] = {
    ReportRevisionActionCode.DELETE_UNBOUND_FACT_BLOCK: _delete_handler,
    ReportRevisionActionCode.DELETE_UNSUPPORTED_FACT_BLOCK: _delete_handler,
    ReportRevisionActionCode.DOWNGRADE_PARTIAL_LANGUAGE: _partial_handler,
    ReportRevisionActionCode.MOVE_CONFLICT_TO_CONFLICTS: _move_conflict_handler,
    ReportRevisionActionCode.MOVE_UNSUPPORTED_TO_APPENDIX: _move_unsupported_handler,
    ReportRevisionActionCode.MOVE_BLOCKED_TO_LIMITATIONS: _move_blocked_handler,
    ReportRevisionActionCode.ADD_DATA_QUALITY_FROM_EXISTING_STATE: (_add_data_quality_handler),
    ReportRevisionActionCode.ADD_LIMITATIONS_FROM_EXISTING_STATE: (_add_limitation_handler),
    ReportRevisionActionCode.RENUMBER_EXISTING_REFERENCES: _renumber_handler,
    ReportRevisionActionCode.REMOVE_INVALID_CITATION_BLOCK: _delete_handler,
    ReportRevisionActionCode.REMOVE_FORBIDDEN_ADVICE_TEXT: _delete_handler,
    ReportRevisionActionCode.TRUNCATE_EXISTING_EXCERPT: _truncate_handler,
    ReportRevisionActionCode.FIX_DETERMINISTIC_FORMAT: _format_handler,
}


class DeterministicReportRevisionEngine:
    def revise(
        self,
        source: ResearchReportAggregate,
        reflection: ReportReflectionResult,
        policy: ReportPolicyRecord,
    ) -> ReportRevisionDraft:
        _validate_revision_input(source, reflection, policy)
        content = source.report.structured_content
        actions: list[ReportRevisionAction] = []
        applied: list[UUID] = []
        unresolved: list[UUID] = []
        for finding in reflection.findings:
            try:
                action_code = ReportRevisionActionCode(finding.remediation_code)
            except ValueError:
                unresolved.append(finding.id)
                continue
            handler = REVISION_ACTION_HANDLERS[action_code]
            try:
                content = handler(content, finding, policy)
            except ReportRevisionError:
                unresolved.append(finding.id)
                continue
            actions.append(
                ReportRevisionAction(
                    finding_id=finding.id,
                    action_code=action_code,
                    block_key=finding.block_key,
                )
            )
            applied.append(finding.id)
        target = _build_target(source.report, _canonicalize(content))
        target_aggregate = rebase_report_bindings(source, target)
        return ReportRevisionDraft(
            source_report_id=source.report.id,
            source_report_checksum=source.report.content_checksum,
            engine_name=REVISION_ENGINE_NAME,
            engine_version=REVISION_ENGINE_VERSION,
            target=target_aggregate,
            actions=tuple(actions),
            applied_finding_ids=tuple(applied),
            unresolved_finding_ids=tuple(unresolved),
        )


def _validate_revision_input(
    source: ResearchReportAggregate,
    reflection: ReportReflectionResult,
    policy: ReportPolicyRecord,
) -> None:
    if reflection.run.status is not ReportReflectionStatus.FINDINGS:
        raise ReportRevisionError("REFLECTION_FINDINGS_REQUIRED")
    if not reflection.findings:
        raise ReportRevisionError("FINDINGS_NOT_MATERIALIZED")
    if (
        reflection.run.research_report_id != source.report.id
        or reflection.run.round_number != 1
        or reflection.run.input_report_checksum != source.report.content_checksum
    ):
        raise ReportRevisionError("REFLECTION_CONTEXT_MISMATCH")
    if policy.max_revision_rounds != 1:
        raise ReportRevisionError("REPORT_REVISION_POLICY_INVALID")
    if policy.allow_model_narrative or policy.allow_model_reflection:
        raise ReportRevisionError("MODEL_REVISION_FORBIDDEN")


def _delete_block(
    content: StructuredReportContent,
    block_key: str | None,
) -> StructuredReportContent:
    if block_key is None or not _contains_block(content, block_key):
        raise ReportRevisionError("REVISION_BLOCK_NOT_FOUND")
    sections = tuple(
        section.model_copy(
            update={
                "blocks": tuple(block for block in section.blocks if block.block_key != block_key)
            }
        )
        for section in content.sections
    )
    return content.model_copy(update={"sections": sections})


def _transform_block(
    content: StructuredReportContent,
    block_key: str | None,
    transform: Callable[[StructuredReportBlock], StructuredReportBlock],
) -> StructuredReportContent:
    if block_key is None or not _contains_block(content, block_key):
        raise ReportRevisionError("REVISION_BLOCK_NOT_FOUND")
    sections = tuple(
        section.model_copy(
            update={
                "blocks": tuple(
                    transform(block) if block.block_key == block_key else block
                    for block in section.blocks
                )
            }
        )
        for section in content.sections
    )
    return content.model_copy(update={"sections": sections})


def _qualify_partial(block: StructuredReportBlock) -> StructuredReportBlock:
    prefix = "Limited by verified evidence: "
    if block.text is None:
        raise ReportRevisionError("REVISION_TEXT_NOT_FOUND")
    if block.text.casefold().startswith(prefix.casefold()):
        return block
    return block.model_copy(update={"text": f"{prefix}{block.text}"})


def _move_block(
    content: StructuredReportContent,
    block_key: str | None,
    target: ReportSection,
) -> StructuredReportContent:
    if block_key is None:
        raise ReportRevisionError("REVISION_BLOCK_NOT_FOUND")
    selected: StructuredReportBlock | None = None
    retained: list[StructuredReportSection] = []
    for section in content.sections:
        kept: list[StructuredReportBlock] = []
        for block in section.blocks:
            if block.block_key == block_key:
                selected = block
            else:
                kept.append(block)
        retained.append(section.model_copy(update={"blocks": tuple(kept)}))
    if selected is None:
        raise ReportRevisionError("REVISION_BLOCK_NOT_FOUND")
    target_index = next(
        (index for index, section in enumerate(retained) if section.section is target),
        None,
    )
    if target_index is None:
        retained.append(
            StructuredReportSection(
                section=target,
                section_index=len(retained),
                title=target.value.replace("_", " ").title(),
                status=ReportSectionStatus.PARTIAL,
                blocks=(selected,),
            )
        )
    else:
        section = retained[target_index]
        retained[target_index] = section.model_copy(update={"blocks": (*section.blocks, selected)})
    return content.model_copy(update={"sections": tuple(retained)})


def _append_disclosure(
    content: StructuredReportContent,
    finding: ReportReflectionFindingRecord,
    section_key: ReportSection,
    block_type: ReportBlockType,
    block_status: ReportBlockStatus,
) -> StructuredReportContent:
    block = StructuredReportBlock(
        block_key=f"reflection.{finding.remediation_code.casefold()}.{finding.id.hex[:8]}",
        block_index=0,
        block_type=block_type,
        status=block_status,
        text=f"Reflection limitation: {finding.finding_code}.",
        payload={
            "finding_code": finding.finding_code,
            "remediation_code": finding.remediation_code,
        },
    )
    sections = list(content.sections)
    index = next(
        (index for index, section in enumerate(sections) if section.section is section_key),
        None,
    )
    if index is None:
        sections.append(
            StructuredReportSection(
                section=section_key,
                section_index=len(sections),
                title=section_key.value.replace("_", " ").title(),
                status=ReportSectionStatus(block_status.value),
                blocks=(block,),
            )
        )
    else:
        section = sections[index]
        sections[index] = section.model_copy(update={"blocks": (*section.blocks, block)})
    return content.model_copy(update={"sections": tuple(sections)})


def _truncate_excerpts(value: JsonValue, maximum: int) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: (
                item[:maximum]
                if key == "rendered_excerpt" and isinstance(item, str) and len(item) > maximum
                else _truncate_excerpts(item, maximum)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_truncate_excerpts(item, maximum) for item in value]
    return value


def _contains_block(content: StructuredReportContent, block_key: str) -> bool:
    return any(
        block.block_key == block_key for section in content.sections for block in section.blocks
    )


def _canonicalize(content: StructuredReportContent) -> StructuredReportContent:
    sections = tuple(
        StructuredReportSection(
            section=section.section,
            section_index=section_index,
            title=section.title,
            status=(section.status if section.blocks else ReportSectionStatus.NO_EVIDENCE),
            blocks=tuple(
                block.model_copy(update={"block_index": block_index})
                for block_index, block in enumerate(section.blocks)
            ),
        )
        for section_index, section in enumerate(content.sections)
    )
    return StructuredReportContent(
        schema_version=content.schema_version,
        locale=content.locale,
        sections=sections,
    )


def _build_target(
    source: ResearchReportRecord,
    content: StructuredReportContent,
) -> ResearchReportRecord:
    allocation = ReportReferenceAllocator().allocate(content)
    content = allocation.content
    rendered = DeterministicMarkdownRenderer().render(content)
    structured_checksum = structured_report_checksum(content)
    markdown_checksum_value = markdown_checksum(rendered.markdown_content)
    context = ReportChecksumContext(
        schema_version=content.schema_version,
        template_name=source.template_name,
        template_version=source.template_version,
        renderer_version=source.renderer_version,
        markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
        locale=source.report_locale,
        input_manifest_checksum=source.input_manifest_checksum,
        visible_references=allocation.references,
    )
    content_checksum = combined_report_checksum(
        structured_checksum,
        markdown_checksum_value,
        context,
    )
    target_id = uuid5(
        NAMESPACE_URL,
        f"{source.id}:{source.report_version + 1}:{content_checksum}",
    )
    return ResearchReportRecord(
        **source.model_dump(
            mode="python",
            exclude={
                "id",
                "report_version",
                "previous_report_id",
                "status",
                "structured_content",
                "markdown_content",
                "structured_checksum",
                "markdown_checksum",
                "content_checksum",
            },
        ),
        id=target_id,
        report_version=source.report_version + 1,
        previous_report_id=source.id,
        status=ResearchReportStatus.REVISED,
        structured_content=content,
        markdown_content=rendered.markdown_content,
        structured_checksum=structured_checksum,
        markdown_checksum=markdown_checksum_value,
        content_checksum=content_checksum,
    )


def rebase_report_bindings(
    source: ResearchReportAggregate,
    target: ResearchReportRecord,
) -> ResearchReportAggregate:
    """Copy only surviving immutable lineage edges onto the successor report."""

    source_block_keys = {
        uuid5(NAMESPACE_URL, f"{source.report.id}:block:{block.block_key}"): block.block_key
        for section in source.report.structured_content.sections
        for block in section.blocks
    }
    target_block_ids = {
        block.block_key: uuid5(NAMESPACE_URL, f"{target.id}:block:{block.block_key}")
        for section in target.structured_content.sections
        for block in section.blocks
    }
    references = {
        (entry.kind, entry.record_id): entry.label
        for entry in ReportReferenceAllocator().allocate(target.structured_content).references
    }
    claim_id_map: dict[UUID, UUID] = {}
    claim_bindings: list[ReportClaimBindingWrite] = []
    for claim_binding in source.claim_bindings:
        block_key = source_block_keys.get(claim_binding.report_block_id)
        if block_key is None or block_key not in target_block_ids:
            continue
        new_id = uuid5(
            NAMESPACE_URL,
            f"{target.id}:claim-binding:{block_key}:{claim_binding.claim_id}",
        )
        claim_id_map[claim_binding.id] = new_id
        claim_bindings.append(
            claim_binding.model_copy(
                update={
                    "id": new_id,
                    "report_block_id": target_block_ids[block_key],
                    "created_at": target.created_at,
                }
            )
        )
    evidence_id_map: dict[UUID, UUID] = {}
    evidence_bindings: list[ReportEvidenceBindingWrite] = []
    for evidence_binding in source.evidence_bindings:
        new_claim_binding_id = claim_id_map.get(evidence_binding.report_claim_binding_id)
        block_key = source_block_keys.get(evidence_binding.report_block_id)
        if new_claim_binding_id is None or block_key is None or block_key not in target_block_ids:
            continue
        reference_kind = (
            ReferenceKind.METRIC
            if evidence_binding.visible_reference_kind is VisibleReferenceKind.METRIC
            else ReferenceKind.EVIDENCE
        )
        visible_reference = references.get((reference_kind, evidence_binding.evidence_id))
        if visible_reference is None:
            continue
        new_id = uuid5(
            NAMESPACE_URL,
            f"{target.id}:evidence-binding:{block_key}:{evidence_binding.claim_evidence_link_id}",
        )
        evidence_id_map[evidence_binding.id] = new_id
        evidence_bindings.append(
            evidence_binding.model_copy(
                update={
                    "id": new_id,
                    "report_block_id": target_block_ids[block_key],
                    "report_claim_binding_id": new_claim_binding_id,
                    "visible_reference": visible_reference,
                    "created_at": target.created_at,
                }
            )
        )
    citation_bindings: list[ReportCitationBindingWrite] = []
    for citation_binding in source.citation_bindings:
        new_evidence_binding_id = evidence_id_map.get(citation_binding.report_evidence_binding_id)
        visible_reference = references.get((ReferenceKind.CITATION, citation_binding.citation_id))
        if new_evidence_binding_id is None or visible_reference is None:
            continue
        citation_bindings.append(
            citation_binding.model_copy(
                update={
                    "id": uuid5(
                        NAMESPACE_URL,
                        f"{target.id}:citation-binding:{citation_binding.citation_id}",
                    ),
                    "report_evidence_binding_id": new_evidence_binding_id,
                    "visible_reference": visible_reference,
                    "created_at": target.created_at,
                }
            )
        )
    return ResearchReportAggregate(
        report=target,
        claim_bindings=tuple(claim_bindings),
        evidence_bindings=tuple(evidence_bindings),
        citation_bindings=tuple(citation_bindings),
    )
