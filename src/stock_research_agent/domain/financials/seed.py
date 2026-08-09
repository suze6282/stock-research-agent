"""Versioned seed for canonical concepts and immutable formula metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from stock_research_agent.domain.financials.concepts import CANONICAL_CONCEPTS
from stock_research_agent.domain.financials.formulas import FORMULA_REGISTRY

if TYPE_CHECKING:
    from stock_research_agent.domain.financials.repositories import FinancialReferenceSeedRepository

_FINANCIAL_SEED_NAMESPACE = UUID("f1000000-0000-0000-0000-000000000001")


@dataclass(frozen=True)
class SeedCanonicalConcept:
    id: UUID
    code: str
    name: str
    statement_type: str
    fact_nature: str
    default_unit_type: str
    supports_duration: bool
    supports_instant: bool
    supports_cumulative: bool
    supports_ttm: bool
    allows_negative: bool
    description: str
    version: str
    status: str


@dataclass(frozen=True)
class SeedFormulaDefinition:
    id: UUID
    metric_code: str
    name: str
    formula_expression: str
    formula_version: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    period_requirement: str
    currency_requirement: str
    denominator_policy: str
    negative_value_policy: str
    status: str


@dataclass(frozen=True)
class SeedProviderFactMapping:
    """Reserved typed manifest entry; V0.1 has no evidence-backed mapping rows."""

    id: UUID


@dataclass(frozen=True)
class FinancialReferenceSeedManifest:
    version: str
    evidence_paths: tuple[str, ...]
    mapping_seed_policy: str
    concepts: tuple[SeedCanonicalConcept, ...]
    formulas: tuple[SeedFormulaDefinition, ...]
    provider_mappings: tuple[SeedProviderFactMapping, ...]


@dataclass(frozen=True)
class FinancialSeedResult:
    version: str
    inserted_count: int
    existing_count: int


FINANCIAL_REFERENCE_SEED_V0 = FinancialReferenceSeedManifest(
    version="financial-reference-v0.1.0",
    evidence_paths=(
        "docs/metric-definitions-v0.1.md",
        "docs/stage-4-implementation-report.md",
        "docs/plans/stage-5-financial-normalization.md",
    ),
    mapping_seed_policy=(
        "Stage 4 approved fixtures preserve no numeric financial facts; therefore no provider "
        "mapping can be evidence-reviewed. Future raw tags remain UNMAPPED until an explicit "
        "provider/taxonomy/context review creates a new seed version."
    ),
    concepts=tuple(
        SeedCanonicalConcept(
            id=uuid5(_FINANCIAL_SEED_NAMESPACE, f"concept:{definition.code.value}"),
            code=definition.code.value,
            name=definition.name,
            statement_type=definition.statement_type.value,
            fact_nature=definition.fact_nature.value,
            default_unit_type=definition.default_unit_type.value,
            supports_duration=definition.supports_duration,
            supports_instant=definition.supports_instant,
            supports_cumulative=definition.supports_cumulative,
            supports_ttm=definition.supports_ttm,
            allows_negative=definition.allows_negative,
            description=definition.description,
            version=definition.version,
            status=definition.status.value,
        )
        for definition in CANONICAL_CONCEPTS
    ),
    formulas=tuple(
        SeedFormulaDefinition(
            id=uuid5(_FINANCIAL_SEED_NAMESPACE, f"formula:{definition.metric_code.value}:1.0.0"),
            metric_code=definition.metric_code.value,
            name=definition.name,
            formula_expression=definition.formula_expression,
            formula_version=definition.formula_version,
            required_inputs=definition.required_inputs,
            optional_inputs=definition.optional_inputs,
            period_requirement=definition.period_requirement,
            currency_requirement=definition.currency_requirement,
            denominator_policy=definition.denominator_policy,
            negative_value_policy=definition.negative_value_policy,
            status=definition.status,
        )
        for definition in FORMULA_REGISTRY
    ),
    provider_mappings=(),
)


class FinancialReferenceSeedService:
    def __init__(
        self,
        manifest: FinancialReferenceSeedManifest = FINANCIAL_REFERENCE_SEED_V0,
    ) -> None:
        self._manifest = manifest

    def seed(self, repository: FinancialReferenceSeedRepository) -> FinancialSeedResult:
        repository.acquire_financial_seed_lock(self._manifest.version)
        inserted_count, existing_count = repository.apply_financial_reference_seed(self._manifest)
        return FinancialSeedResult(
            version=self._manifest.version,
            inserted_count=inserted_count,
            existing_count=existing_count,
        )
