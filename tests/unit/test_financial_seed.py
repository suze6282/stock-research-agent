from __future__ import annotations

from stock_research_agent.domain.financials.concepts import CANONICAL_CONCEPTS
from stock_research_agent.domain.financials.formulas import FORMULA_REGISTRY
from stock_research_agent.domain.financials.seed import (
    FINANCIAL_REFERENCE_SEED_V0,
    FinancialReferenceSeedManifest,
    FinancialReferenceSeedService,
)


class RecordingSeedRepository:
    def __init__(self) -> None:
        self.locked: list[str] = []
        self.manifests: list[object] = []

    def acquire_financial_seed_lock(self, seed_version: str) -> None:
        self.locked.append(seed_version)

    def apply_financial_reference_seed(
        self, manifest: FinancialReferenceSeedManifest
    ) -> tuple[int, int]:
        self.manifests.append(manifest)
        return len(manifest.concepts) + len(manifest.formulas), 0


def test_financial_seed_contains_only_reviewed_concepts_and_formulas() -> None:
    manifest = FINANCIAL_REFERENCE_SEED_V0

    assert manifest.version == "financial-reference-v0.1.0"
    assert len(manifest.concepts) == len(CANONICAL_CONCEPTS)
    assert len(manifest.formulas) == len(FORMULA_REGISTRY)
    assert manifest.provider_mappings == ()
    assert {item.code for item in manifest.concepts} == {
        definition.code.value for definition in CANONICAL_CONCEPTS
    }
    assert {item.metric_code for item in manifest.formulas} == {
        definition.metric_code.value for definition in FORMULA_REGISTRY
    }
    assert len({item.id for item in (*manifest.concepts, *manifest.formulas)}) == (
        len(manifest.concepts) + len(manifest.formulas)
    )


def test_financial_seed_documents_why_provider_mapping_seed_is_empty() -> None:
    manifest = FINANCIAL_REFERENCE_SEED_V0

    assert "docs/metric-definitions-v0.1.md" in manifest.evidence_paths
    assert "docs/stage-4-implementation-report.md" in manifest.evidence_paths
    assert "no numeric financial facts" in manifest.mapping_seed_policy
    assert "UNMAPPED" in manifest.mapping_seed_policy


def test_seed_service_acquires_transaction_lock_before_apply() -> None:
    repository = RecordingSeedRepository()

    result = FinancialReferenceSeedService().seed(repository)

    assert repository.locked == [FINANCIAL_REFERENCE_SEED_V0.version]
    assert repository.manifests == [FINANCIAL_REFERENCE_SEED_V0]
    assert result.version == FINANCIAL_REFERENCE_SEED_V0.version
    assert result.inserted_count == len(CANONICAL_CONCEPTS) + len(FORMULA_REGISTRY)
    assert result.existing_count == 0
