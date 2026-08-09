from __future__ import annotations

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from stock_research_agent.domain.reports.checksums import (
    ReportChecksumContext,
    combined_report_checksum,
    markdown_checksum,
    structured_report_checksum,
)
from stock_research_agent.domain.reports.composition import (
    DeterministicReportCompositionService,
)
from stock_research_agent.domain.reports.enums import ReportLocale, ReportSection
from stock_research_agent.domain.reports.markdown import (
    MARKDOWN_RENDERER_VERSION,
    DeterministicMarkdownRenderer,
)
from stock_research_agent.domain.reports.policies import build_default_report_policy
from stock_research_agent.domain.reports.references import ReportReferenceAllocator
from stock_research_agent.domain.reports.reflection import (
    DeterministicReportReflectionEngine,
    ReportReflectionStatus,
)
from stock_research_agent.domain.reports.reflection_policy import (
    build_default_runtime_reflection_policy,
)
from stock_research_agent.domain.reports.release_gate import (
    ReleaseGateDecision,
    ReportReleaseGate,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ResearchReportAggregate,
)
from stock_research_agent.domain.reports.revision import (
    DeterministicReportRevisionEngine,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
)
from tests.support.report_scenarios import (
    AS_OF,
    build_neutral_synthetic_scenario,
    materialize_reflection,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "reports"
MARKERS = {
    "SYNTHETIC_TEST_ONLY",
    "NOT_COMPANY_EVIDENCE",
    "OFFLINE",
    "NOT_LIVE",
}


def _synthetic_source() -> tuple[ResearchReportAggregate, ReportInputManifest]:
    scenario = build_neutral_synthetic_scenario(
        namespace="neutral-synthetic-stage8",
        locale=ReportLocale.EN_US,
    )
    base = DeterministicReportCompositionService().compose(
        scenario.report_input,
        scenario.request,
        build_default_report_policy(),
        scenario.template,
        report_id=uuid5(
            NAMESPACE_URL,
            "neutral-synthetic-stage8:report",
        ),
        generation_run_id=uuid5(
            NAMESPACE_URL,
            "neutral-synthetic-stage8:generation",
        ),
        created_at=AS_OF,
    )
    sections = tuple(
        section.model_copy(
            update={
                "blocks": tuple(
                    block.model_copy(
                        update={
                            "status": ReportBlockStatus.PARTIAL,
                            "payload": {
                                **block.payload,
                                "support_status": "PARTIALLY_SUPPORTED",
                            },
                        }
                    )
                    if section.section is ReportSection.SECURITY_IDENTITY
                    else block
                    for block in section.blocks
                )
            }
        )
        for section in base.report.structured_content.sections
    )
    content = base.report.structured_content.model_copy(update={"sections": sections})
    rendered = DeterministicMarkdownRenderer().render(content)
    structured_digest = structured_report_checksum(content)
    markdown_digest = markdown_checksum(rendered.markdown_content)
    references = ReportReferenceAllocator().allocate(content).references
    checksum_context = ReportChecksumContext(
        schema_version=content.schema_version,
        template_name=base.report.template_name,
        template_version=base.report.template_version,
        renderer_version=base.report.renderer_version,
        markdown_renderer_version=MARKDOWN_RENDERER_VERSION,
        locale=base.report.report_locale,
        input_manifest_checksum=base.report.input_manifest_checksum,
        visible_references=references,
    )
    source = base.model_copy(
        update={
            "report": base.report.model_copy(
                update={
                    "structured_content": content,
                    "markdown_content": rendered.markdown_content,
                    "structured_checksum": structured_digest,
                    "markdown_checksum": markdown_digest,
                    "content_checksum": combined_report_checksum(
                        structured_digest,
                        markdown_digest,
                        checksum_context,
                    ),
                }
            )
        }
    )
    return source, scenario.report_input.manifest


def test_isolated_synthetic_flow_revises_then_passes_internal_gate() -> None:
    source, manifest = _synthetic_source()
    assert source.report.security_id not in {
        INDUSTRIAL_FII_SECURITY_ID,
        MICRON_SECURITY_ID,
    }
    round_one = materialize_reflection(
        source,
        manifest,
        round_number=1,
        namespace="neutral-synthetic-stage8",
    )
    assert round_one.run.status is ReportReflectionStatus.FINDINGS

    revision = DeterministicReportRevisionEngine().revise(
        source,
        round_one,
        build_default_report_policy(),
    )
    assert revision.applied_finding_ids
    assert revision.unresolved_finding_ids == ()
    revised = revision.target

    round_two = materialize_reflection(
        revised,
        manifest,
        round_number=2,
        namespace="neutral-synthetic-stage8",
    )
    assert round_two.run.status is ReportReflectionStatus.PASS
    gate = ReportReleaseGate().evaluate(
        revised,
        manifest,
        round_two,
        build_default_report_policy(),
    )

    assert gate.internal_release_status is ReleaseGateDecision.PUBLISHABLE
    assert gate.sealed_report is not None
    assert gate.sealed_report.report.previous_report_id == revised.report.id
    assert len(gate.sealed_report.claim_bindings) == len(revised.claim_bindings)
    assert len(gate.sealed_report.evidence_bindings) == len(revised.evidence_bindings)
    assert gate.sealed_report.claim_bindings[0].id != revised.claim_bindings[0].id
    assert gate.sealed_report.report.security_id not in {
        INDUSTRIAL_FII_SECURITY_ID,
        MICRON_SECURITY_ID,
    }
    repeated = ReportReleaseGate().evaluate(
        revised,
        manifest,
        round_two,
        build_default_report_policy(),
    )
    assert repeated == gate


def test_synthetic_fixture_and_bilingual_expectations_are_explicitly_isolated() -> None:
    source = json.loads((FIXTURE_ROOT / "synthetic_report_input.json").read_text(encoding="utf-8"))
    assert set(source["fixture_status"]) == MARKERS
    assert source["security"]["symbol"] == "SYNTH-001"
    assert "601138" not in json.dumps(source)
    assert '"MU"' not in json.dumps(source)

    for locale in ("en_us", "zh_cn"):
        expected_json = json.loads(
            (FIXTURE_ROOT / f"synthetic_report_expected_{locale}.json").read_text(encoding="utf-8")
        )
        expected_markdown = (FIXTURE_ROOT / f"synthetic_report_expected_{locale}.md").read_text(
            encoding="utf-8"
        )
        assert expected_json["status"] == "PUBLISHABLE"
        assert set(expected_json["markers"]) == MARKERS
        assert all(marker in expected_markdown for marker in MARKERS)
        assert expected_markdown.endswith("\n")
        assert "\r" not in expected_markdown


def test_synthetic_runtime_has_no_model_or_external_capability() -> None:
    engine = DeterministicReportReflectionEngine()
    policy = build_default_runtime_reflection_policy()

    assert policy.allow_model_reflection is False
    assert vars(engine) == {}
    assert not hasattr(engine, "model_provider")
    assert not hasattr(engine, "http_client")
    assert not hasattr(engine, "tool_registry")
