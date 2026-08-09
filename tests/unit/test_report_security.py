from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.providers import (
    CandidateReportBlock,
    ProviderClassification,
    ReportProviderMetadata,
)
from stock_research_agent.domain.reports.reporting import (
    ReportBlockStatus,
    ReportBlockType,
    StructuredReportBlock,
)
from stock_research_agent.domain.reports.templates import TemplateToken
from tests.support.report_providers import ScriptedTestNarrativeProvider

CLAIM_ID = UUID("90000000-0000-4000-8000-000000000001")


def _block(**updates: object) -> StructuredReportBlock:
    values: dict[str, object] = {
        "block_key": "synthetic.claim",
        "block_index": 0,
        "block_type": ReportBlockType.PARAGRAPH,
        "status": ReportBlockStatus.COMPLETE,
        "text": "Bound synthetic statement.",
        "payload": {"claim_id": str(CLAIM_ID)},
    }
    values.update(updates)
    return StructuredReportBlock.model_validate(values)


def test_candidate_provider_cannot_emit_unbound_or_ambiguous_fact_blocks() -> None:
    valid = CandidateReportBlock(block=_block(), claim_ids=(CLAIM_ID,))
    assert valid.claim_ids == (CLAIM_ID,)

    with pytest.raises(ValidationError, match="payload claim"):
        CandidateReportBlock(
            block=_block(payload={}),
            claim_ids=(CLAIM_ID,),
        )
    with pytest.raises(ValidationError, match="sorted and unique"):
        CandidateReportBlock(
            block=_block(),
            claim_ids=(CLAIM_ID, CLAIM_ID),
        )


@pytest.mark.parametrize(
    "payload",
    (
        "<script>alert(1)</script>",
        "{{ environment.SECRET }}",
        "${OPENAI_API_KEY}",
        "file:///C:/private/key",
        "https://example.invalid/prompt",
        "SELECT * FROM secrets",
        "powershell -Command Get-ChildItem Env:",
        "../../outside",
    ),
)
def test_template_literals_reject_executable_or_context_escape_syntax(
    payload: str,
) -> None:
    with pytest.raises(ValidationError):
        TemplateToken(literal=payload)


def test_scripted_provider_is_test_only_and_cannot_be_production_default() -> None:
    provider = ScriptedTestNarrativeProvider(
        blocks=(CandidateReportBlock(block=_block(), claim_ids=(CLAIM_ID,)),)
    )
    assert provider.metadata.classification is ProviderClassification.TEST_ONLY
    assert provider.metadata.production_default is False

    with pytest.raises(ValidationError, match="deterministic"):
        ReportProviderMetadata(
            provider_name="scripted-test-provider",
            provider_version="scripted-test-provider-v1",
            classification=ProviderClassification.TEST_ONLY,
            production_default=True,
            requires_network=False,
            model_token_budget=0,
        )
