"""Persistence ports for financial normalization and deterministic calculations."""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.schemas import (
    ApprovedFactMapping,
    CalculationInputRecord,
    CalculationInputWrite,
    CalculationRunDetail,
    CalculationRunRecord,
    CalculationRunWrite,
    CalculationSnapshot,
    DerivedMetricRecord,
    DerivedMetricWrite,
    FinancialPeriodRecord,
    FinancialPeriodWrite,
    NormalizedFactForCalculation,
    NormalizedFactInputWrite,
    NormalizedFinancialFactRecord,
    NormalizedFinancialFactWrite,
    RawFinancialFactForNormalization,
    SnapshotForNormalization,
)
from stock_research_agent.domain.financials.seed import (
    FinancialReferenceSeedManifest,
)


class FinancialReferenceSeedRepository(Protocol):
    def acquire_financial_seed_lock(self, seed_version: str) -> None: ...

    def apply_financial_reference_seed(
        self,
        manifest: FinancialReferenceSeedManifest,
    ) -> tuple[int, int]: ...


class FinancialNormalizationRepository(Protocol):
    """Read boundary required before normalized writes are introduced."""

    def get_snapshot_for_normalization(
        self, snapshot_id: UUID
    ) -> SnapshotForNormalization | None: ...

    def list_snapshot_financial_facts(
        self, snapshot_id: UUID
    ) -> tuple[RawFinancialFactForNormalization, ...]: ...

    def find_approved_fact_mapping(
        self,
        fact: RawFinancialFactForNormalization,
        as_of: date,
    ) -> ApprovedFactMapping | None: ...

    def get_or_create_financial_period(self, value: FinancialPeriodWrite) -> UUID: ...

    def get_or_create_normalized_fact(
        self,
        value: NormalizedFinancialFactWrite,
    ) -> tuple[UUID, bool]: ...

    def get_or_create_normalized_fact_input(
        self,
        value: NormalizedFactInputWrite,
    ) -> tuple[UUID, bool]: ...


class FinancialCalculationRepository(Protocol):
    def acquire_calculation_lock(self, snapshot_id: UUID, input_checksum: str) -> None: ...

    def get_snapshot_for_calculation(self, snapshot_id: UUID) -> CalculationSnapshot | None: ...

    def list_normalized_facts_for_calculation(
        self, snapshot_id: UUID
    ) -> tuple[NormalizedFactForCalculation, ...]: ...

    def find_calculation_run(
        self,
        snapshot_id: UUID,
        input_checksum: str,
        calculation_version: str,
        formula_set_version: str,
        mapping_version: str,
        normalization_version: str,
    ) -> CalculationRunRecord | None: ...

    def create_calculation_run(self, value: CalculationRunWrite) -> UUID: ...

    def get_formula_definition_id(self, metric_code: str, formula_version: str) -> UUID: ...

    def add_derived_metric(self, value: DerivedMetricWrite) -> UUID: ...

    def add_calculation_input(self, value: CalculationInputWrite) -> UUID: ...

    def complete_calculation_run(
        self,
        calculation_run_id: UUID,
        status: QualityStatus,
        warning_count: int,
    ) -> None: ...


class FinancialReadRepository(Protocol):
    def read_snapshot_provenance(self, snapshot_id: UUID) -> tuple[str, str, str]: ...

    def read_financial_periods(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        period_type: str | None,
        limit: int,
    ) -> tuple[FinancialPeriodRecord, ...]: ...

    def read_normalized_financial_facts(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        concept_code: str | None,
        limit: int,
    ) -> tuple[NormalizedFinancialFactRecord, ...]: ...

    def read_financial_metrics(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        metric_code: str | None,
        limit: int,
    ) -> tuple[DerivedMetricRecord, ...]: ...

    def read_metric_lineage(
        self,
        calculation_run_id: UUID,
        metric_code: str,
        limit: int,
    ) -> tuple[CalculationInputRecord, ...]: ...

    def read_calculation_run(
        self,
        calculation_run_id: UUID,
    ) -> CalculationRunDetail | None: ...
