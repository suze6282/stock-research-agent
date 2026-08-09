from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.markdown import DeterministicMarkdownRenderer
from stock_research_agent.domain.reports.reflection_policy import (
    ReflectionSeverity,
    RuntimeReflectionCheck,
    build_default_runtime_reflection_policy,
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
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchPackageStatus,
    SyntheticStatus,
)

NOW = datetime(2026, 7, 29, 1, tzinfo=UTC)
REPORT_ID = UUID("10000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("10000000-0000-0000-0000-000000000002")
SNAPSHOT_ID = UUID("10000000-0000-0000-0000-000000000003")
PACKAGE_ID = UUID("10000000-0000-0000-0000-000000000004")
CLAIM_ID = UUID("20000000-0000-0000-0000-000000000001")
EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000001")
LINK_ID = UUID("40000000-0000-0000-0000-000000000001")
CITATION_ID = UUID("50000000-0000-0000-0000-000000000001")

EXPECTED_MINIMUM_SEVERITIES = {
    RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.SECURITY_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.SNAPSHOT_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.AS_OF_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_FUTURE_EVIDENCE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.STRICT_DOCUMENT_PUBLISHED_AT_KNOWN: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE: (ReflectionSeverity.CRITICAL),
    RuntimeReflectionCheck.NO_CROSS_SECURITY_RECORDS: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_CROSS_SNAPSHOT_RECORDS: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.BLOCKED_CAPABILITY_NOT_COMPLETED: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.DATA_QUALITY_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.LIMITATIONS_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.NO_UNUSED_APPENDIX_REFERENCE: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.CITATION_VALID: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.CLAIM_SET_CHECKSUM_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.EVIDENCE_LINK_SET_CHECKSUMS_MATCH: (ReflectionSeverity.CRITICAL),
    RuntimeReflectionCheck.PACKAGE_CHECKSUM_MATCHES: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_RATING_LANGUAGE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_TARGET_PRICE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_POSITION_ADVICE: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_TRADING_INSTRUCTION: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.FIXTURE_NOT_DESCRIBED_AS_LIVE: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.SYNTHETIC_NOT_REAL_COMPANY_RESEARCH: (ReflectionSeverity.CRITICAL),
    RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.UNIT_CURRENCY_MATCH: ReflectionSeverity.MEDIUM,
    RuntimeReflectionCheck.REPORT_AS_OF_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.SNAPSHOT_IDENTITY_PRESENT: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.NO_FALSE_MODEL_CALL_CLAIM: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.RETRIEVAL_CAPABILITY_HONEST: ReflectionSeverity.HIGH,
    RuntimeReflectionCheck.JSON_MARKDOWN_CHECKSUMS_MATCH: ReflectionSeverity.CRITICAL,
    RuntimeReflectionCheck.REPORT_STRUCTURE_VERSION_CHAIN_VALID: (ReflectionSeverity.CRITICAL),
    RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED: ReflectionSeverity.CRITICAL,
}


def _module() -> object:
    return import_module("stock_research_agent.domain.reports.reflection")


def _section(
    section: ReportSection,
    index: int,
    block: StructuredReportBlock,
) -> StructuredReportSection:
    return StructuredReportSection(
        section=section,
        section_index=index,
        title=section.value.replace("_", " ").title(),
        status=ReportSectionStatus(block.status.value),
        blocks=(block.model_copy(update={"block_index": 0}),),
    )


def _body_block(**payload_updates: object) -> StructuredReportBlock:
    payload: dict[str, object] = {
        "claim_id": str(CLAIM_ID),
        "evidence_ids": [str(EVIDENCE_ID)],
        "link_ids": [str(LINK_ID)],
        "reference": "[MET-001]",
        "reference_targets": [
            {
                "kind": "METRIC",
                "record_id": str(EVIDENCE_ID),
                "label": "MET-001",
            }
        ],
        "statement_code": "REVENUE",
        "support_status": "SUPPORTED",
        "unit": "USD",
        "currency_code": "USD",
        "value": "100.00",
        "period": "FY2025",
        "security_id": str(SECURITY_ID),
        "snapshot_id": str(SNAPSHOT_ID),
        "as_of_time": NOW.isoformat().replace("+00:00", "Z"),
        "source_published_at": (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
    }
    payload.update(payload_updates)
    return StructuredReportBlock(
        block_key="claim.revenue.0",
        block_index=0,
        block_type=ReportBlockType.METRIC_TABLE,
        status=ReportBlockStatus.COMPLETE,
        text="100.00 USD, period: FY2025 [MET-001]",
        payload=payload,
    )


def _base_content() -> StructuredReportContent:
    blocks = (
        (
            ReportSection.RESEARCH_SCOPE,
            StructuredReportBlock(
                block_key="scope.context",
                block_index=0,
                block_type=ReportBlockType.HEADING,
                status=ReportBlockStatus.COMPLETE,
                text=f"As of {NOW.date().isoformat()}; snapshot {SNAPSHOT_ID}.",
                payload={},
            ),
        ),
        (ReportSection.FINANCIAL_HEALTH, _body_block()),
        (
            ReportSection.DATA_QUALITY,
            StructuredReportBlock(
                block_key="data_quality.summary",
                block_index=0,
                block_type=ReportBlockType.WARNING,
                status=ReportBlockStatus.COMPLETE,
                text="Only verified point-in-time inputs are included.",
                payload={},
            ),
        ),
        (
            ReportSection.LIMITATIONS,
            StructuredReportBlock(
                block_key="limitations.summary",
                block_index=0,
                block_type=ReportBlockType.LIMITATION,
                status=ReportBlockStatus.COMPLETE,
                text="No additional limitations were recorded.",
                payload={},
            ),
        ),
        (
            ReportSection.EVIDENCE_APPENDIX,
            StructuredReportBlock(
                block_key="appendix.evidence",
                block_index=0,
                block_type=ReportBlockType.EVIDENCE_TABLE,
                status=ReportBlockStatus.COMPLETE,
                text=None,
                payload={
                    "references": [
                        {
                            "label": "MET-001",
                            "record_id": str(EVIDENCE_ID),
                        }
                    ]
                },
            ),
        ),
        (
            ReportSection.CITATION_APPENDIX,
            StructuredReportBlock(
                block_key="appendix.citations",
                block_index=0,
                block_type=ReportBlockType.CITATION_LIST,
                status=ReportBlockStatus.NO_EVIDENCE,
                text=None,
                payload={"citations": []},
            ),
        ),
    )
    return StructuredReportContent(
        schema_version="research-report-v1",
        locale=ReportLocale.EN_US,
        sections=tuple(
            _section(section, index, block) for index, (section, block) in enumerate(blocks)
        ),
    )


def _manifest(**updates: object) -> ReportInputManifest:
    values: dict[str, object] = {
        "research_package_id": PACKAGE_ID,
        "research_agent_run_id": UUID(int=11),
        "research_request_id": UUID(int=12),
        "security_id": SECURITY_ID,
        "issuer_id": UUID(int=13),
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "research_type": "FULL_RESEARCH_PACKAGE",
        "research_mode": ResearchMode.REAL_RESEARCH,
        "package_status": ResearchPackageStatus.COMPLETE,
        "package_checksum": "a" * 64,
        "policy_version": "research-policy-v1",
        "planner_version": "deterministic-template-planner-v1",
        "tool_catalog_version": "b" * 80,
        "evidence_version": "research-evidence-v1",
        "claim_version": "research-claim-v1",
        "package_version": "research-package-v1",
        "claim_ids": (CLAIM_ID,),
        "evidence_ids": (EVIDENCE_ID,),
        "link_ids": (LINK_ID,),
        "citation_ids": (),
        "lineage_ids": (),
        "claims_checksum": "c" * 64,
        "evidence_checksum": "d" * 64,
        "links_checksum": "e" * 64,
        "citations_checksum": "f" * 64,
        "lineage_checksum": "0" * 64,
        "section_states": (),
        "blocked_capabilities": (),
        "warnings": (),
        "data_quality_items": (),
        "limitation_items": (),
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "manifest_schema_version": "report-input-manifest-v1",
        "canonical_payload_checksum": "1" * 64,
        "created_at": NOW,
    }
    values.update(updates)
    return ReportInputManifest.model_construct(**values)


def _aggregate(
    *,
    content: StructuredReportContent | None = None,
    manifest: ReportInputManifest | None = None,
    **updates: object,
) -> tuple[ResearchReportAggregate, ReportInputManifest]:
    actual_manifest = manifest or _manifest()
    actual_content = content or _base_content()
    rendered = DeterministicMarkdownRenderer().render(actual_content)
    values: dict[str, object] = {
        "id": REPORT_ID,
        "report_generation_run_id": UUID(int=21),
        "report_version": 1,
        "previous_report_id": None,
        "report_type": ReportType.FULL_RESEARCH_DRAFT,
        "report_locale": ReportLocale.EN_US,
        "status": ResearchReportStatus.DRAFT,
        "title": "Verifiable Research Report",
        "subtitle": None,
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "research_package_id": PACKAGE_ID,
        "input_manifest_checksum": actual_manifest.canonical_payload_checksum,
        "package_checksum": actual_manifest.package_checksum,
        "structured_content": actual_content,
        "markdown_content": rendered.markdown_content,
        "structured_checksum": report_checksum(actual_content),
        "markdown_checksum": report_checksum(rendered.markdown_content),
        "content_checksum": "2" * 64,
        "claim_set_checksum": actual_manifest.claims_checksum,
        "evidence_set_checksum": actual_manifest.evidence_checksum,
        "link_set_checksum": actual_manifest.links_checksum,
        "citation_set_checksum": actual_manifest.citations_checksum,
        "renderer_version": "deterministic-report-renderer-v1",
        "template_name": "full_research_report",
        "template_version": "1.0.0",
        "created_at": NOW,
    }
    values.update(updates)
    report = ResearchReportRecord.model_construct(**values)
    return ResearchReportAggregate(report=report), actual_manifest


def _replace_body(
    content: StructuredReportContent,
    block: StructuredReportBlock,
    *,
    section: ReportSection = ReportSection.FINANCIAL_HEALTH,
) -> StructuredReportContent:
    sections = list(content.sections)
    body_index = next(
        index
        for index, item in enumerate(sections)
        if item.section is ReportSection.FINANCIAL_HEALTH
    )
    sections[body_index] = _section(section, body_index, block)
    return content.model_copy(update={"sections": tuple(sections)})


def _remove_section(
    content: StructuredReportContent,
    section: ReportSection,
) -> StructuredReportContent:
    retained = tuple(item for item in content.sections if item.section is not section)
    return content.model_copy(
        update={
            "sections": tuple(
                item.model_copy(update={"section_index": index})
                for index, item in enumerate(retained)
            )
        }
    )


def _violation(
    check: RuntimeReflectionCheck,
) -> tuple[ResearchReportAggregate, ReportInputManifest]:
    aggregate, manifest = _aggregate()
    report = aggregate.report
    content = report.structured_content
    body = next(
        item.blocks[0]
        for item in content.sections
        if item.section is ReportSection.FINANCIAL_HEALTH
    )
    payload = dict(body.payload)

    if check is RuntimeReflectionCheck.FACTUAL_BLOCK_HAS_CLAIM:
        payload.pop("claim_id")
    elif check is RuntimeReflectionCheck.PRIMARY_CLAIM_HAS_EVIDENCE:
        payload["evidence_ids"] = []
    elif check is RuntimeReflectionCheck.DOCUMENT_CLAIM_HAS_VALID_CITATION:
        content = _replace_body(content, body, section=ReportSection.DOCUMENT_EVIDENCE)
        return _aggregate(content=content)
    elif check is RuntimeReflectionCheck.STRUCTURED_CLAIM_HAS_LINEAGE:
        payload["link_ids"] = []
    elif check is RuntimeReflectionCheck.SECURITY_MATCHES:
        return _aggregate(security_id=UUID(int=991))
    elif check is RuntimeReflectionCheck.SNAPSHOT_MATCHES:
        return _aggregate(snapshot_id=UUID(int=992))
    elif check is RuntimeReflectionCheck.AS_OF_MATCHES:
        return _aggregate(research_as_of_time=NOW - timedelta(days=1))
    elif check is RuntimeReflectionCheck.NO_FUTURE_EVIDENCE:
        payload["source_published_at"] = (NOW + timedelta(days=1)).isoformat()
    elif check is RuntimeReflectionCheck.STRICT_DOCUMENT_PUBLISHED_AT_KNOWN:
        payload.pop("source_published_at")
        payload["citation_ids"] = [str(CITATION_ID)]
        payload["citation_status"] = "VALID"
        content = _replace_body(
            content,
            body.model_copy(update={"payload": payload}),
            section=ReportSection.DOCUMENT_EVIDENCE,
        )
        return _aggregate(content=content)
    elif check is RuntimeReflectionCheck.NO_REAL_RESEARCH_SYNTHETIC_EVIDENCE:
        manifest = _manifest(synthetic_status=SyntheticStatus.SYNTHETIC_TEST_ONLY)
        return _aggregate(manifest=manifest)
    elif check is RuntimeReflectionCheck.NO_CROSS_SECURITY_RECORDS:
        payload["security_id"] = str(UUID(int=993))
    elif check is RuntimeReflectionCheck.NO_CROSS_SNAPSHOT_RECORDS:
        payload["snapshot_id"] = str(UUID(int=994))
    elif check is RuntimeReflectionCheck.CONFLICTING_CLAIMS_DISCLOSED:
        payload["support_status"] = "CONFLICTING"
    elif check is RuntimeReflectionCheck.PARTIAL_SUPPORT_QUALIFIED:
        payload["support_status"] = "PARTIALLY_SUPPORTED"
    elif check is RuntimeReflectionCheck.UNSUPPORTED_CLAIMS_RESTRICTED:
        payload["support_status"] = "UNSUPPORTED"
    elif check is RuntimeReflectionCheck.BLOCKED_CAPABILITY_NOT_COMPLETED:
        manifest = _manifest(blocked_capabilities=("FINANCIAL_FACTS_MISSING",))
        payload["capability_code"] = "FINANCIAL_FACTS_MISSING"
        body = body.model_copy(update={"text": "Capability completed successfully."})
    elif check is RuntimeReflectionCheck.DATA_QUALITY_PRESENT:
        return _aggregate(content=_remove_section(content, ReportSection.DATA_QUALITY))
    elif check is RuntimeReflectionCheck.LIMITATIONS_PRESENT:
        return _aggregate(content=_remove_section(content, ReportSection.LIMITATIONS))
    elif check is RuntimeReflectionCheck.NO_ORPHAN_BODY_REFERENCE:
        payload["reference"] = "[MET-999]"
        payload["reference_targets"] = [
            {
                "kind": "METRIC",
                "record_id": str(EVIDENCE_ID),
                "label": "MET-999",
            }
        ]
    elif check is RuntimeReflectionCheck.NO_UNUSED_APPENDIX_REFERENCE:
        appendix = next(
            item for item in content.sections if item.section is ReportSection.EVIDENCE_APPENDIX
        )
        appendix_payload = dict(appendix.blocks[0].payload)
        appendix_payload["references"] = [
            *appendix_payload["references"],
            {"label": "EV-999", "record_id": str(UUID(int=999))},
        ]
        sections = tuple(
            item.model_copy(
                update={
                    "blocks": (item.blocks[0].model_copy(update={"payload": appendix_payload}),)
                }
            )
            if item.section is ReportSection.EVIDENCE_APPENDIX
            else item
            for item in content.sections
        )
        return _aggregate(content=content.model_copy(update={"sections": sections}))
    elif check in {
        RuntimeReflectionCheck.CITATION_VALID,
        RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY,
    }:
        citation_section = next(
            item for item in content.sections if item.section is ReportSection.CITATION_APPENDIX
        )
        row = {
            "citation_id": str(CITATION_ID),
            "label": "CIT-001",
            "citation_status": (
                "INVALID" if check is RuntimeReflectionCheck.CITATION_VALID else "VALID"
            ),
            "rendered_excerpt": (
                "x" * 1001
                if check is RuntimeReflectionCheck.EXCERPT_WITHIN_POLICY
                else "Verified excerpt."
            ),
        }
        changed = citation_section.model_copy(
            update={
                "status": ReportSectionStatus.COMPLETE,
                "blocks": (
                    citation_section.blocks[0].model_copy(
                        update={
                            "status": ReportBlockStatus.COMPLETE,
                            "payload": {"citations": [row]},
                        }
                    ),
                ),
            }
        )
        sections = tuple(
            changed if item.section is ReportSection.CITATION_APPENDIX else item
            for item in content.sections
        )
        return _aggregate(content=content.model_copy(update={"sections": sections}))
    elif check is RuntimeReflectionCheck.CLAIM_SET_CHECKSUM_MATCHES:
        return _aggregate(claim_set_checksum="9" * 64)
    elif check is RuntimeReflectionCheck.EVIDENCE_LINK_SET_CHECKSUMS_MATCH:
        return _aggregate(link_set_checksum="9" * 64)
    elif check is RuntimeReflectionCheck.PACKAGE_CHECKSUM_MATCHES:
        return _aggregate(package_checksum="9" * 64)
    elif check is RuntimeReflectionCheck.NO_RATING_LANGUAGE:
        body = body.model_copy(update={"text": "Rating: strong buy."})
    elif check is RuntimeReflectionCheck.NO_TARGET_PRICE:
        body = body.model_copy(update={"text": "Target price: USD 150."})
    elif check is RuntimeReflectionCheck.NO_POSITION_ADVICE:
        body = body.model_copy(update={"text": "Position size should be 10%."})
    elif check is RuntimeReflectionCheck.NO_TRADING_INSTRUCTION:
        body = body.model_copy(update={"text": "Sell the shares now."})
    elif check is RuntimeReflectionCheck.NO_UNSUPPORTED_OVERSTATEMENT:
        body = body.model_copy(update={"text": "Revenue will definitely rise."})
    elif check is RuntimeReflectionCheck.FIXTURE_NOT_DESCRIBED_AS_LIVE:
        manifest = _manifest(synthetic_status=SyntheticStatus.FIXTURE_REAL_EXCERPT)
        body = body.model_copy(update={"text": "Live market data is included."})
    elif check is RuntimeReflectionCheck.SYNTHETIC_NOT_REAL_COMPANY_RESEARCH:
        manifest = _manifest(
            research_mode=ResearchMode.SYNTHETIC_TEST_ONLY,
            synthetic_status=SyntheticStatus.SYNTHETIC_TEST_ONLY,
        )
    elif check is RuntimeReflectionCheck.UNIT_CURRENCY_MATCH:
        payload["currency_code"] = "CNY"
    elif check is RuntimeReflectionCheck.REPORT_AS_OF_PRESENT:
        return _aggregate(research_as_of_time=None)
    elif check is RuntimeReflectionCheck.SNAPSHOT_IDENTITY_PRESENT:
        return _aggregate(snapshot_id=UUID(int=0))
    elif check is RuntimeReflectionCheck.NO_FALSE_MODEL_CALL_CLAIM:
        body = body.model_copy(update={"text": "Generated by an OpenAI model."})
    elif check is RuntimeReflectionCheck.RETRIEVAL_CAPABILITY_HONEST:
        manifest = _manifest(blocked_capabilities=("VECTOR_PROVIDER_MISSING",))
        body = body.model_copy(update={"text": "Full semantic vector retrieval completed."})
    elif check is RuntimeReflectionCheck.JSON_MARKDOWN_CHECKSUMS_MATCH:
        return _aggregate(markdown_content="# tampered\n")
    elif check is RuntimeReflectionCheck.REPORT_STRUCTURE_VERSION_CHAIN_VALID:
        return _aggregate(report_version=2, previous_report_id=None)
    elif check is RuntimeReflectionCheck.REPORT_INPUT_MANIFEST_UNCHANGED:
        return _aggregate(input_manifest_checksum="9" * 64)

    changed_body = body.model_copy(update={"payload": payload})
    changed_content = _replace_body(content, changed_body)
    return _aggregate(content=changed_content, manifest=manifest)


def test_engine_registry_is_exactly_the_40_approved_checks_with_fixed_minimums() -> None:
    module = _module()

    assert len(module.REFLECTION_RULES) == 40
    assert tuple(rule.check for rule in module.REFLECTION_RULES) == tuple(RuntimeReflectionCheck)
    assert {
        rule.check: rule.minimum_severity for rule in module.REFLECTION_RULES
    } == EXPECTED_MINIMUM_SEVERITIES


def test_valid_report_passes_deterministically_without_external_capabilities() -> None:
    module = _module()
    report, manifest = _aggregate()
    engine = module.DeterministicReportReflectionEngine()

    first = engine.reflect(
        report,
        manifest,
        build_default_runtime_reflection_policy(),
        1,
    )
    second = engine.reflect(
        report,
        manifest,
        build_default_runtime_reflection_policy(),
        1,
    )

    assert first == second
    assert first.status is module.ReportReflectionStatus.PASS
    assert first.findings == ()
    assert first.engine_version == "deterministic-report-reflection-v1"
    assert vars(engine) == {}
    assert not hasattr(engine, "tool_registry")
    assert not hasattr(engine, "model_provider")
    assert not hasattr(engine, "http_client")
    assert not hasattr(engine, "repository")


@pytest.mark.parametrize("check", tuple(RuntimeReflectionCheck))
def test_each_approved_check_emits_its_stable_finding(
    check: RuntimeReflectionCheck,
) -> None:
    module = _module()
    report, manifest = _violation(check)

    result = module.DeterministicReportReflectionEngine().reflect(
        report,
        manifest,
        build_default_runtime_reflection_policy(),
        1,
    )

    findings = {finding.finding_code: finding for finding in result.findings}
    assert check in findings
    assert findings[check].severity is EXPECTED_MINIMUM_SEVERITIES[check]
    assert findings[check].blocking is (
        EXPECTED_MINIMUM_SEVERITIES[check] in {ReflectionSeverity.CRITICAL, ReflectionSeverity.HIGH}
    )


def test_language_rules_are_contextual_and_do_not_scan_source_excerpt_quotes() -> None:
    module = _module()
    aggregate, manifest = _aggregate()
    content = aggregate.report.structured_content
    body = next(
        item.blocks[0]
        for item in content.sections
        if item.section is ReportSection.FINANCIAL_HEALTH
    ).model_copy(update={"text": "The issuer maintains a market position in memory."})
    content = _replace_body(content, body)
    citation = next(
        item for item in content.sections if item.section is ReportSection.CITATION_APPENDIX
    )
    citation = citation.model_copy(
        update={
            "status": ReportSectionStatus.COMPLETE,
            "blocks": (
                citation.blocks[0].model_copy(
                    update={
                        "status": ReportBlockStatus.COMPLETE,
                        "payload": {
                            "citations": [
                                {
                                    "citation_id": str(CITATION_ID),
                                    "label": "CIT-001",
                                    "citation_status": "VALID",
                                    "rendered_excerpt": (
                                        "The source says buy, sell, and target price "
                                        "as a quoted historical statement."
                                    ),
                                }
                            ]
                        },
                    }
                ),
            ),
        }
    )
    content = content.model_copy(
        update={
            "sections": tuple(
                citation if item.section is ReportSection.CITATION_APPENDIX else item
                for item in content.sections
            )
        }
    )
    aggregate, manifest = _aggregate(content=content, manifest=manifest)

    result = module.DeterministicReportReflectionEngine().reflect(
        aggregate,
        manifest,
        build_default_runtime_reflection_policy(),
        1,
    )

    forbidden = {
        RuntimeReflectionCheck.NO_RATING_LANGUAGE,
        RuntimeReflectionCheck.NO_TARGET_PRICE,
        RuntimeReflectionCheck.NO_POSITION_ADVICE,
        RuntimeReflectionCheck.NO_TRADING_INSTRUCTION,
    }
    assert forbidden.isdisjoint(finding.finding_code for finding in result.findings)


@pytest.mark.parametrize("round_number", [0, 3])
def test_engine_rejects_rounds_outside_the_closed_two_round_workflow(
    round_number: int,
) -> None:
    module = _module()
    report, manifest = _aggregate()

    with pytest.raises(
        module.ReportReflectionEngineError,
        match="REPORT_REFLECTION_ROUND_INVALID",
    ):
        module.DeterministicReportReflectionEngine().reflect(
            report,
            manifest,
            build_default_runtime_reflection_policy(),
            round_number,
        )
