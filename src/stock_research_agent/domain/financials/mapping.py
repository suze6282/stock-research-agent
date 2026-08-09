"""Exact and versioned provider fact mapping rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from stock_research_agent.domain.financials.concepts import CanonicalConcept
from stock_research_agent.domain.financials.enums import MappingStatus, StatementType


@dataclass(frozen=True)
class FactMappingInput:
    provider_code: str
    provider_concept: str
    taxonomy: str
    statement_type: StatementType
    form_type: str | None
    contexts: tuple[str, ...]
    dimensions: tuple[str, ...]
    source_published_on: date


@dataclass(frozen=True)
class ProviderFactMappingRule:
    rule_id: str
    provider_code: str
    provider_concept: str
    taxonomy: str
    statement_type: StatementType
    form_type: str | None
    context_rules: tuple[str, ...]
    dimension_rules: tuple[str, ...]
    canonical_concept: CanonicalConcept | None
    status: MappingStatus
    mapping_version: str
    valid_from: date | None
    valid_to: date | None
    source_reference: str | None
    reviewed_by: str | None

    def __post_init__(self) -> None:
        if not self.rule_id or not self.provider_code or not self.provider_concept:
            raise ValueError("mapping identity fields must not be empty")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        if self.status is MappingStatus.APPROVED:
            if self.canonical_concept is None:
                raise ValueError("APPROVED mappings require a canonical_concept")
            if not self.source_reference:
                raise ValueError("APPROVED mappings require source_reference evidence")
            if not self.reviewed_by:
                raise ValueError("APPROVED mappings require reviewed_by evidence")


@dataclass(frozen=True)
class FactMappingResult:
    status: MappingStatus
    canonical_concept: CanonicalConcept | None
    rule_ids: tuple[str, ...]
    mapping_version: str | None


def _matches(fact: FactMappingInput, rule: ProviderFactMappingRule) -> bool:
    if rule.status is MappingStatus.DEPRECATED:
        return False
    if (
        fact.provider_code != rule.provider_code
        or fact.provider_concept != rule.provider_concept
        or fact.taxonomy != rule.taxonomy
        or fact.statement_type is not rule.statement_type
        or (rule.form_type is not None and fact.form_type != rule.form_type)
    ):
        return False
    if not set(rule.context_rules).issubset(fact.contexts):
        return False
    if not set(rule.dimension_rules).issubset(fact.dimensions):
        return False
    if rule.valid_from is not None and fact.source_published_on < rule.valid_from:
        return False
    return rule.valid_to is None or fact.source_published_on <= rule.valid_to


def resolve_fact_mapping(
    fact: FactMappingInput,
    rules: tuple[ProviderFactMappingRule, ...],
) -> FactMappingResult:
    """Resolve only exact, valid rules and surface conflicts without guessing."""

    matches = tuple(
        sorted((rule for rule in rules if _matches(fact, rule)), key=lambda rule: rule.rule_id)
    )
    if not matches:
        return FactMappingResult(MappingStatus.UNMAPPED, None, (), None)
    rule_ids = tuple(rule.rule_id for rule in matches)
    approved = tuple(rule for rule in matches if rule.status is MappingStatus.APPROVED)
    if len(matches) != 1 or len(approved) != 1:
        return FactMappingResult(MappingStatus.AMBIGUOUS, None, rule_ids, None)
    selected = approved[0]
    return FactMappingResult(
        MappingStatus.APPROVED,
        selected.canonical_concept,
        rule_ids,
        selected.mapping_version,
    )
