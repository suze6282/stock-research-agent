from __future__ import annotations

from importlib import import_module
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from stock_research_agent.domain.reports.bindings import (
    ReportClaimBindingRole,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
    VisibleReferenceKind,
)
from stock_research_agent.domain.reports.enums import ReportSection
from stock_research_agent.domain.reports.policies import build_default_report_policy
from stock_research_agent.domain.reports.reflection import (
    REFLECTION_RULES,
    ReflectionFindingCategory,
    ReflectionSeverity,
    ReportReflectionFindingRecord,
    ReportReflectionResult,
    ReportReflectionRunRecord,
    ReportReflectionStatus,
)
from stock_research_agent.domain.reports.reflection_policy import (
    RuntimeReflectionCheck,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    ResearchReportAggregate,
    StructuredReportBlock,
)
from stock_research_agent.domain.research_agent.enums import EvidenceRole
from tests.unit.test_report_reflection_engine import (
    NOW,
    _aggregate,
    _replace_body,
)

REFLECTION_RUN_ID = UUID("60000000-0000-0000-0000-000000000001")
SECTION_ID = UUID("60000000-0000-0000-0000-000000000002")
BLOCK_ID = UUID("60000000-0000-0000-0000-000000000003")

EXPECTED_ACTION_CODES = (
    "DELETE_UNBOUND_FACT_BLOCK",
    "DELETE_UNSUPPORTED_FACT_BLOCK",
    "DOWNGRADE_PARTIAL_LANGUAGE",
    "MOVE_CONFLICT_TO_CONFLICTS",
    "MOVE_UNSUPPORTED_TO_APPENDIX",
    "MOVE_BLOCKED_TO_LIMITATIONS",
    "ADD_DATA_QUALITY_FROM_EXISTING_STATE",
    "ADD_LIMITATIONS_FROM_EXISTING_STATE",
    "RENUMBER_EXISTING_REFERENCES",
    "REMOVE_INVALID_CITATION_BLOCK",
    "REMOVE_FORBIDDEN_ADVICE_TEXT",
    "TRUNCATE_EXISTING_EXCERPT",
    "FIX_DETERMINISTIC_FORMAT",
)


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.revision")


def _body(source: ResearchReportAggregate) -> StructuredReportBlock:
    return next(
        section.blocks[0]
        for section in source.report.structured_content.sections
        if section.section is ReportSection.FINANCIAL_HEALTH
    )


def _source(action_code: str) -> ResearchReportAggregate:
    source, _ = _aggregate()
    body = _body(source)
    if action_code == "TRUNCATE_EXISTING_EXCERPT":
        payload = {
            **body.payload,
            "rendered_excerpt": "x" * 1001,
        }
        body = body.model_copy(update={"payload": payload})
    elif action_code == "RENUMBER_EXISTING_REFERENCES":
        payload = {
            **body.payload,
            "reference": "[MET-009]",
            "reference_targets": [
                {
                    "kind": "METRIC",
                    "record_id": body.payload["evidence_ids"][0],
                    "label": "MET-009",
                }
            ],
        }
        body = body.model_copy(
            update={
                "text": (body.text or "").replace("[MET-001]", "[MET-009]"),
                "payload": payload,
            }
        )
    elif action_code == "REMOVE_FORBIDDEN_ADVICE_TEXT":
        body = body.model_copy(update={"text": "Buy the shares now."})
    elif action_code == "REMOVE_INVALID_CITATION_BLOCK":
        body = body.model_copy(
            update={
                "block_type": ReportBlockType.EVIDENCE_TABLE,
                "payload": {
                    **body.payload,
                    "citation_id": str(UUID(int=701)),
                    "citation_status": "INVALID",
                },
            }
        )
    elif action_code == "DOWNGRADE_PARTIAL_LANGUAGE":
        body = body.model_copy(
            update={
                "status": ReportBlockStatus.PARTIAL,
                "payload": {
                    **body.payload,
                    "support_status": "PARTIALLY_SUPPORTED",
                },
            }
        )
    elif action_code == "MOVE_CONFLICT_TO_CONFLICTS":
        body = body.model_copy(
            update={
                "block_type": ReportBlockType.CONFLICT,
                "status": ReportBlockStatus.PARTIAL,
                "payload": {**body.payload, "support_status": "CONFLICTING"},
            }
        )
    elif action_code in {
        "DELETE_UNSUPPORTED_FACT_BLOCK",
        "MOVE_UNSUPPORTED_TO_APPENDIX",
    }:
        body = body.model_copy(
            update={
                "status": ReportBlockStatus.NO_EVIDENCE,
                "payload": {**body.payload, "support_status": "UNSUPPORTED"},
            }
        )
    elif action_code == "MOVE_BLOCKED_TO_LIMITATIONS":
        body = body.model_copy(
            update={
                "block_type": ReportBlockType.LIMITATION,
                "status": ReportBlockStatus.BLOCKED,
                "payload": {**body.payload, "support_status": "BLOCKED"},
            }
        )
    content = _replace_body(source.report.structured_content, body)
    return _aggregate(content=content)[0]


def _reflection(
    source: ResearchReportAggregate,
    remediation_code: str,
) -> ReportReflectionResult:
    run = ReportReflectionRunRecord(
        id=REFLECTION_RUN_ID,
        research_report_id=source.report.id,
        reflection_policy_version="runtime-report-reflection-v1",
        engine_name="deterministic-report-reflection",
        engine_version="deterministic-report-reflection-v1",
        round_number=1,
        input_report_checksum=source.report.content_checksum,
        status=ReportReflectionStatus.FINDINGS,
        started_at=NOW,
        total_finding_count=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        completed_at=NOW,
    )
    finding = ReportReflectionFindingRecord(
        id=UUID(int=801),
        reflection_run_id=run.id,
        research_report_id=source.report.id,
        report_section_id=SECTION_ID,
        report_block_id=BLOCK_ID,
        claim_id=UUID(str(_body(source).payload["claim_id"])),
        evidence_id=None,
        citation_id=None,
        finding_code=RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM.value,
        category=ReflectionFindingCategory.BINDING,
        severity=ReflectionSeverity.HIGH,
        description="A deterministic report revision is required.",
        remediation_code=remediation_code,
        blocking=True,
        created_at=NOW,
        report_section=ReportSection.FINANCIAL_HEALTH,
        block_key=_body(source).block_key,
    )
    return ReportReflectionResult(
        run=run,
        finding_ids=(finding.id,),
        findings=(finding,),
    )


def test_revision_action_registry_is_closed_and_complete() -> None:
    module = _module()

    assert tuple(item.value for item in module.ReportRevisionActionCode) == (EXPECTED_ACTION_CODES)
    assert tuple(module.REVISION_ACTION_HANDLERS) == tuple(module.ReportRevisionActionCode)


def test_safe_reflection_rules_emit_revision_actions_and_unsafe_rules_do_not() -> None:
    module = _module()
    rules = {rule.check: rule.remediation_code for rule in REFLECTION_RULES}
    approved = {item.value for item in module.ReportRevisionActionCode}

    assert rules[RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM] in approved
    assert rules[RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED] in approved
    assert rules[RuntimeReflectionCheck.NO_TRADING_INSTRUCTION] in approved
    assert rules[RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY] in approved
    assert rules[RuntimeReflectionCheck.SECURITY_MATCHES] not in approved
    assert rules[RuntimeReflectionCheck.NO_FUTURE_EVIDENCE] not in approved
    assert rules[RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED] not in approved


@pytest.mark.parametrize("action_code", EXPECTED_ACTION_CODES)
def test_every_approved_action_is_dispatched_and_recorded(
    action_code: str,
) -> None:
    module = _module()
    source = _source(action_code)
    before = source.model_dump(mode="python")

    result = module.DeterministicReportRevisionEngine().revise(
        source,
        _reflection(source, action_code),
        build_default_report_policy(),
    )

    assert result.applied_finding_ids == (UUID(int=801),)
    assert result.unresolved_finding_ids == ()
    assert tuple(action.action_code.value for action in result.actions) == (action_code,)
    assert result.target.report.previous_report_id == source.report.id
    assert result.target.report.report_version == source.report.report_version + 1
    assert source.model_dump(mode="python") == before


def test_revision_is_subtractive_or_disclosure_only_and_preserves_source_lineage() -> None:
    module = _module()
    source = _source("DOWNGRADE_PARTIAL_LANGUAGE")

    result = module.DeterministicReportRevisionEngine().revise(
        source,
        _reflection(source, "DOWNGRADE_PARTIAL_LANGUAGE"),
        build_default_report_policy(),
    )

    target = result.target.report
    assert (
        target.security_id,
        target.snapshot_id,
        target.research_as_of_time,
        target.research_package_id,
        target.input_manifest_checksum,
        target.claim_set_checksum,
        target.evidence_set_checksum,
        target.link_set_checksum,
        target.citation_set_checksum,
    ) == (
        source.report.security_id,
        source.report.snapshot_id,
        source.report.research_as_of_time,
        source.report.research_package_id,
        source.report.input_manifest_checksum,
        source.report.claim_set_checksum,
        source.report.evidence_set_checksum,
        source.report.link_set_checksum,
        source.report.citation_set_checksum,
    )
    revised_body = _body(result.target)
    assert revised_body.payload == _body(source).payload
    assert "limited by verified evidence" in (revised_body.text or "").casefold()
    assert target.status.value == "REVISED"


def test_revision_rebases_surviving_claim_and_evidence_bindings() -> None:
    module = _module()
    source = _source("DOWNGRADE_PARTIAL_LANGUAGE")
    body = _body(source)
    claim_id = UUID(str(body.payload["claim_id"]))
    evidence_id = UUID(str(body.payload["evidence_ids"][0]))
    link_id = UUID(str(body.payload["link_ids"][0]))
    block_id = uuid5(
        NAMESPACE_URL,
        f"{source.report.id}:block:{body.block_key}",
    )
    claim_binding = ReportClaimBindingWrite(
        id=UUID(int=9001),
        report_block_id=block_id,
        claim_id=claim_id,
        role=ReportClaimBindingRole.PRIMARY,
        item_or_row_key=body.block_key,
        created_at=NOW,
    )
    evidence_binding = ReportEvidenceBindingWrite(
        id=UUID(int=9002),
        report_block_id=block_id,
        report_claim_binding_id=claim_binding.id,
        claim_evidence_link_id=link_id,
        evidence_id=evidence_id,
        role=EvidenceRole.PRIMARY,
        visible_reference_kind=VisibleReferenceKind.METRIC,
        visible_reference="MET-001",
        item_or_row_key=body.block_key,
        source_record_id=UUID(int=9003),
        source_checksum="a" * 64,
        created_at=NOW,
    )
    source = ResearchReportAggregate(
        report=source.report,
        claim_bindings=(claim_binding,),
        evidence_bindings=(evidence_binding,),
    )

    result = module.DeterministicReportRevisionEngine().revise(
        source,
        _reflection(source, "DOWNGRADE_PARTIAL_LANGUAGE"),
        build_default_report_policy(),
    )

    target = result.target
    assert len(target.claim_bindings) == 1
    assert len(target.evidence_bindings) == 1
    assert target.claim_bindings[0].id != claim_binding.id
    assert target.evidence_bindings[0].id != evidence_binding.id
    assert target.evidence_bindings[0].report_claim_binding_id == target.claim_bindings[0].id
    assert target.evidence_bindings[0].visible_reference == "MET-001"


@pytest.mark.parametrize(
    "updates",
    (
        {"research_report_id": UUID(int=999)},
        {"round_number": 2},
        {"input_report_checksum": "9" * 64},
    ),
)
def test_revision_rejects_cross_report_wrong_round_or_stale_reflection(
    updates: dict[str, object],
) -> None:
    module = _module()
    source = _source("DOWNGRADE_PARTIAL_LANGUAGE")
    reflection = _reflection(source, "DOWNGRADE_PARTIAL_LANGUAGE")
    bad_run = reflection.run.model_copy(update=updates)
    bad = reflection.model_copy(update={"run": bad_run})

    with pytest.raises(module.ReportRevisionError):
        module.DeterministicReportRevisionEngine().revise(
            source,
            bad,
            build_default_report_policy(),
        )


def test_unknown_or_nonlocal_remediation_is_retained_as_unresolved() -> None:
    module = _module()
    source = _source("DOWNGRADE_PARTIAL_LANGUAGE")

    result = module.DeterministicReportRevisionEngine().revise(
        source,
        _reflection(source, "REQUERY_PROVIDER"),
        build_default_report_policy(),
    )

    assert result.applied_finding_ids == ()
    assert result.unresolved_finding_ids == (UUID(int=801),)
    assert result.actions == ()
    assert result.target.report.structured_content == source.report.structured_content


def test_revision_requires_materialized_findings_and_has_no_external_dependencies() -> None:
    module = _module()
    source = _source("DOWNGRADE_PARTIAL_LANGUAGE")
    reflection = _reflection(source, "DOWNGRADE_PARTIAL_LANGUAGE").model_copy(
        update={"findings": ()}
    )
    engine = module.DeterministicReportRevisionEngine()

    with pytest.raises(module.ReportRevisionError, match="FINDINGS_NOT_MATERIALIZED"):
        engine.revise(source, reflection, build_default_report_policy())
    assert vars(engine) == {}
    assert not hasattr(engine, "tool_registry")
    assert not hasattr(engine, "model_provider")
    assert not hasattr(engine, "http_client")
    assert not hasattr(engine, "repository")
