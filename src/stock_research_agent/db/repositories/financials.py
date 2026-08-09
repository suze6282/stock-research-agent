"""SQLAlchemy persistence for Stage 5 financial reference and calculation data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.data_access import (
    DataProvider,
    DataSnapshot,
    ProviderFinancialFact,
    SnapshotItem,
)
from stock_research_agent.db.models.financials import (
    CalculationInput,
    CalculationRun,
    CanonicalFinancialConcept,
    DerivedMetric,
    FinancialPeriod,
    FormulaDefinition,
    NormalizedFactInput,
    NormalizedFinancialFact,
    ProviderFactMapping,
)
from stock_research_agent.domain.data_access.provenance import classify_provider_evidence
from stock_research_agent.domain.financials.enums import FactNature, QualityStatus, UnitType
from stock_research_agent.domain.financials.exceptions import FinancialSeedConflictError
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
from stock_research_agent.domain.financials.seed import FinancialReferenceSeedManifest


class SqlAlchemyFinancialRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire_financial_seed_lock(self, seed_version: str) -> None:
        digest = sha256(seed_version.encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def acquire_calculation_lock(self, snapshot_id: UUID, input_checksum: str) -> None:
        digest = sha256(f"{snapshot_id}:{input_checksum}".encode()).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def get_snapshot_for_normalization(self, snapshot_id: UUID) -> SnapshotForNormalization | None:
        snapshot = self._session.get(DataSnapshot, snapshot_id)
        if snapshot is None:
            return None
        return SnapshotForNormalization(
            snapshot_id=snapshot.id,
            security_id=snapshot.security_id,
            research_as_of_time=snapshot.research_as_of_time,
            status=snapshot.status,
        )

    def get_snapshot_for_calculation(self, snapshot_id: UUID) -> CalculationSnapshot | None:
        snapshot = self._session.get(DataSnapshot, snapshot_id)
        if snapshot is None:
            return None
        return CalculationSnapshot(
            snapshot_id=snapshot.id,
            security_id=snapshot.security_id,
            research_as_of_time=snapshot.research_as_of_time,
            status=snapshot.status,
        )

    def list_normalized_facts_for_calculation(
        self, snapshot_id: UUID
    ) -> tuple[NormalizedFactForCalculation, ...]:
        rows = self._session.execute(
            select(NormalizedFinancialFact, FinancialPeriod, CanonicalFinancialConcept.code)
            .join(
                FinancialPeriod,
                FinancialPeriod.id == NormalizedFinancialFact.financial_period_id,
            )
            .join(
                CanonicalFinancialConcept,
                CanonicalFinancialConcept.id == NormalizedFinancialFact.canonical_concept_id,
            )
            .where(NormalizedFinancialFact.snapshot_id == snapshot_id)
            .order_by(
                FinancialPeriod.period_end,
                CanonicalFinancialConcept.code,
                NormalizedFinancialFact.id,
            )
        ).all()
        return tuple(
            NormalizedFactForCalculation(
                id=fact.id,
                canonical_concept_code=concept_code,
                financial_period_id=period.id,
                fiscal_year=period.fiscal_year,
                fiscal_quarter=period.fiscal_quarter,
                fiscal_period=period.fiscal_period,
                period_type=period.period_type,
                period_start=period.period_start,
                period_end=period.period_end,
                duration_days=period.duration_days,
                accounting_standard=period.accounting_standard,
                is_cumulative=period.is_cumulative,
                is_single_quarter=period.is_single_quarter,
                normalized_value=fact.normalized_value,
                normalized_unit=fact.normalized_unit,
                currency_code=fact.currency_code,
                source_published_at=fact.source_published_at,
            )
            for fact, period, concept_code in rows
            if fact.source_published_at is not None
        )

    def find_calculation_run(
        self,
        snapshot_id: UUID,
        input_checksum: str,
        calculation_version: str,
        formula_set_version: str,
        mapping_version: str,
        normalization_version: str,
    ) -> CalculationRunRecord | None:
        run = self._session.scalar(
            select(CalculationRun).where(
                CalculationRun.snapshot_id == snapshot_id,
                CalculationRun.input_checksum == input_checksum,
                CalculationRun.calculation_version == calculation_version,
                CalculationRun.formula_set_version == formula_set_version,
                CalculationRun.mapping_version == mapping_version,
                CalculationRun.normalization_version == normalization_version,
                CalculationRun.status != "RUNNING",
            )
        )
        if run is None:
            return None
        metric_count = self._session.scalar(
            select(func.count())
            .select_from(DerivedMetric)
            .where(DerivedMetric.calculation_run_id == run.id)
        )
        return CalculationRunRecord(
            id=run.id,
            security_id=run.security_id,
            snapshot_id=run.snapshot_id,
            status=QualityStatus(run.status),
            input_checksum=run.input_checksum,
            metric_count=int(metric_count or 0),
            warning_count=run.warning_count,
        )

    def create_calculation_run(self, value: CalculationRunWrite) -> UUID:
        run = CalculationRun(**asdict(value))
        self._session.add(run)
        self._session.flush()
        return run.id

    def get_formula_definition_id(self, metric_code: str, formula_version: str) -> UUID:
        formula_id = self._session.scalar(
            select(FormulaDefinition.id).where(
                FormulaDefinition.metric_code == metric_code,
                FormulaDefinition.formula_version == formula_version,
                FormulaDefinition.status == "ACTIVE",
            )
        )
        if formula_id is None:
            raise FinancialSeedConflictError(
                f"active formula definition missing for {metric_code}:{formula_version}"
            )
        return formula_id

    def add_derived_metric(self, value: DerivedMetricWrite) -> UUID:
        values = asdict(value)
        values["quality_status"] = value.quality_status.value
        values["warning_codes"] = list(value.warning_codes)
        metric = DerivedMetric(**values)
        self._session.add(metric)
        self._session.flush()
        return metric.id

    def add_calculation_input(self, value: CalculationInputWrite) -> UUID:
        calculation_input = CalculationInput(**asdict(value))
        self._session.add(calculation_input)
        self._session.flush()
        return calculation_input.id

    def complete_calculation_run(
        self,
        calculation_run_id: UUID,
        status: QualityStatus,
        warning_count: int,
    ) -> None:
        run = self._session.get(CalculationRun, calculation_run_id)
        if run is None or run.status != "RUNNING":
            raise FinancialSeedConflictError("calculation run is missing or already terminal")
        run.status = status.value
        run.warning_count = warning_count
        run.completed_at = datetime.now(UTC)
        self._session.flush()

    def read_financial_periods(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        period_type: str | None,
        limit: int,
    ) -> tuple[FinancialPeriodRecord, ...]:
        statement = select(FinancialPeriod).where(
            FinancialPeriod.security_id == security_id,
            FinancialPeriod.snapshot_id == snapshot_id,
        )
        if period_type is not None:
            statement = statement.where(FinancialPeriod.period_type == period_type)
        periods = self._session.scalars(
            statement.order_by(FinancialPeriod.period_end.desc(), FinancialPeriod.id).limit(limit)
        )
        return tuple(
            FinancialPeriodRecord(
                id=period.id,
                security_id=period.security_id,
                snapshot_id=period.snapshot_id,
                fiscal_year=period.fiscal_year,
                fiscal_quarter=period.fiscal_quarter,
                fiscal_period=period.fiscal_period,
                period_type=period.period_type,
                period_start=period.period_start,
                period_end=period.period_end,
                published_at=period.published_at,
                duration_days=period.duration_days,
                is_annual=period.is_annual,
                is_cumulative=period.is_cumulative,
                is_single_quarter=period.is_single_quarter,
                is_ttm=period.is_ttm,
                accounting_standard=period.accounting_standard,
                source_form_type=period.source_form_type,
            )
            for period in periods
        )

    def read_snapshot_provenance(self, snapshot_id: UUID) -> tuple[str, str, str]:
        providers = self._session.execute(
            select(
                DataProvider.provider_type,
                DataProvider.status,
                DataProvider.terms_status,
            )
            .join(SnapshotItem, SnapshotItem.provider_id == DataProvider.id)
            .where(SnapshotItem.snapshot_id == snapshot_id)
            .distinct()
        ).all()
        markers = tuple(
            classify_provider_evidence(
                provider_type=provider_type,
                status=status,
                terms_status=terms_status,
            )
            for provider_type, status, terms_status in providers
        )
        if not markers:
            return ("UNKNOWN", "UNKNOWN", "UNKNOWN")
        values = {
            (
                marker.data_origin,
                marker.access_mode,
                marker.live_status,
            )
            for marker in markers
        }
        if len(values) == 1:
            return next(iter(values))
        return ("MIXED", "MIXED", "MIXED")

    def read_normalized_financial_facts(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        concept_code: str | None,
        limit: int,
    ) -> tuple[NormalizedFinancialFactRecord, ...]:
        statement = (
            select(NormalizedFinancialFact, CanonicalFinancialConcept.code)
            .join(
                CanonicalFinancialConcept,
                CanonicalFinancialConcept.id == NormalizedFinancialFact.canonical_concept_id,
            )
            .where(
                NormalizedFinancialFact.security_id == security_id,
                NormalizedFinancialFact.snapshot_id == snapshot_id,
            )
        )
        if concept_code is not None:
            statement = statement.where(CanonicalFinancialConcept.code == concept_code)
        rows = self._session.execute(
            statement.order_by(
                NormalizedFinancialFact.source_published_at.desc(),
                NormalizedFinancialFact.id,
            ).limit(limit)
        )
        return tuple(
            NormalizedFinancialFactRecord(
                id=fact.id,
                security_id=fact.security_id,
                snapshot_id=fact.snapshot_id,
                financial_period_id=fact.financial_period_id,
                canonical_concept_code=concept_code_value,
                source_financial_fact_id=fact.source_financial_fact_id,
                original_value=fact.original_value,
                normalized_value=fact.normalized_value,
                original_unit=fact.original_unit,
                normalized_unit=fact.normalized_unit,
                currency_code=fact.currency_code,
                is_reported=fact.is_reported,
                is_derived_from_cumulative=fact.is_derived_from_cumulative,
                is_restated=fact.is_restated,
                source_published_at=fact.source_published_at,
                mapping_version=fact.mapping_version,
                normalization_version=fact.normalization_version,
            )
            for fact, concept_code_value in rows
        )

    def read_financial_metrics(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        metric_code: str | None,
        limit: int,
    ) -> tuple[DerivedMetricRecord, ...]:
        run_id = self._session.scalar(
            select(CalculationRun.id)
            .where(
                CalculationRun.security_id == security_id,
                CalculationRun.snapshot_id == snapshot_id,
                CalculationRun.status != "RUNNING",
            )
            .order_by(CalculationRun.created_at.desc(), CalculationRun.id.desc())
            .limit(1)
        )
        if run_id is None:
            return ()
        statement = select(DerivedMetric).where(
            DerivedMetric.calculation_run_id == run_id,
            DerivedMetric.security_id == security_id,
            DerivedMetric.snapshot_id == snapshot_id,
        )
        if metric_code is not None:
            statement = statement.where(DerivedMetric.metric_code == metric_code)
        metrics = self._session.scalars(
            statement.order_by(DerivedMetric.metric_code, DerivedMetric.period_end.desc()).limit(
                limit
            )
        )
        return tuple(_metric_record(metric) for metric in metrics)

    def read_metric_lineage(
        self,
        calculation_run_id: UUID,
        metric_code: str,
        limit: int,
    ) -> tuple[CalculationInputRecord, ...]:
        inputs = self._session.scalars(
            select(CalculationInput)
            .where(
                CalculationInput.calculation_run_id == calculation_run_id,
                CalculationInput.metric_code == metric_code,
            )
            .order_by(CalculationInput.input_role, CalculationInput.id)
            .limit(limit)
        )
        return tuple(
            CalculationInputRecord(
                id=item.id,
                calculation_run_id=item.calculation_run_id,
                metric_code=item.metric_code,
                normalized_fact_id=item.normalized_fact_id,
                source_record_type=item.source_record_type,
                source_record_id=item.source_record_id,
                input_role=item.input_role,
                value_used=item.value_used,
                unit=item.unit,
                currency_code=item.currency_code,
            )
            for item in inputs
        )

    def read_calculation_run(
        self,
        calculation_run_id: UUID,
    ) -> CalculationRunDetail | None:
        run = self._session.get(CalculationRun, calculation_run_id)
        if run is None or run.status == "RUNNING":
            return None
        return CalculationRunDetail(
            id=run.id,
            security_id=run.security_id,
            snapshot_id=run.snapshot_id,
            status=QualityStatus(run.status),
            calculation_version=run.calculation_version,
            formula_set_version=run.formula_set_version,
            mapping_version=run.mapping_version,
            normalization_version=run.normalization_version,
            input_checksum=run.input_checksum,
            started_at=run.started_at,
            completed_at=run.completed_at,
            warning_count=run.warning_count,
            error_code=run.error_code,
            safe_error_message=run.safe_error_message,
        )

    def list_snapshot_financial_facts(
        self, snapshot_id: UUID
    ) -> tuple[RawFinancialFactForNormalization, ...]:
        rows = self._session.execute(
            select(ProviderFinancialFact, DataProvider.code)
            .join(
                SnapshotItem,
                (SnapshotItem.source_record_id == ProviderFinancialFact.id)
                & (SnapshotItem.source_record_type == "provider_financial_facts"),
            )
            .join(DataProvider, DataProvider.id == ProviderFinancialFact.provider_id)
            .where(SnapshotItem.snapshot_id == snapshot_id)
            .order_by(ProviderFinancialFact.id)
        ).all()
        facts: list[RawFinancialFactForNormalization] = []
        for fact, provider_code in rows:
            if (
                fact.value is None
                or fact.unit is None
                or fact.fiscal_year is None
                or fact.fiscal_period is None
            ):
                continue
            facts.append(
                RawFinancialFactForNormalization(
                    id=fact.id,
                    security_id=fact.security_id,
                    provider_id=fact.provider_id,
                    provider_code=provider_code,
                    statement_type=fact.statement_type,
                    provider_concept=fact.provider_concept,
                    taxonomy=fact.taxonomy,
                    context_id=fact.context_id,
                    dimensions=tuple(
                        sorted((str(key), str(value)) for key, value in fact.dimensions.items())
                    ),
                    value=fact.value,
                    unit=fact.unit,
                    currency_code=fact.currency_code,
                    fiscal_year=fact.fiscal_year,
                    fiscal_quarter=fact.fiscal_quarter,
                    fiscal_period=fact.fiscal_period,
                    period_start=fact.period_start,
                    period_end=fact.period_end,
                    instant_date=fact.instant_date,
                    filed_at=fact.filed_at,
                    source_published_at=fact.source_published_at,
                    form_type=fact.form_type,
                    is_annual=bool(fact.is_annual),
                    is_cumulative=bool(fact.is_cumulative),
                    is_restated=bool(fact.is_restated),
                    retrieved_at=fact.retrieved_at,
                )
            )
        return tuple(facts)

    def find_approved_fact_mapping(
        self,
        fact: RawFinancialFactForNormalization,
        as_of: date,
    ) -> ApprovedFactMapping | None:
        candidates = self._session.execute(
            select(ProviderFactMapping, CanonicalFinancialConcept)
            .join(
                CanonicalFinancialConcept,
                CanonicalFinancialConcept.id == ProviderFactMapping.canonical_concept_id,
            )
            .where(
                ProviderFactMapping.provider_id == fact.provider_id,
                ProviderFactMapping.provider_concept == fact.provider_concept,
                ProviderFactMapping.taxonomy.is_not_distinct_from(fact.taxonomy),
                ProviderFactMapping.statement_type == fact.statement_type,
                ProviderFactMapping.form_type.is_not_distinct_from(fact.form_type),
                ProviderFactMapping.mapping_status == "APPROVED",
                (ProviderFactMapping.valid_from.is_(None))
                | (ProviderFactMapping.valid_from <= as_of),
                (ProviderFactMapping.valid_to.is_(None)) | (ProviderFactMapping.valid_to >= as_of),
            )
            .order_by(ProviderFactMapping.id)
        ).all()
        contexts = {fact.context_id} if fact.context_id is not None else set()
        dimensions = {f"{key}={value}" for key, value in fact.dimensions}
        matches = [
            (mapping, concept)
            for mapping, concept in candidates
            if {str(value) for value in mapping.context_rules}.issubset(contexts)
            and {str(value) for value in mapping.dimension_rules}.issubset(dimensions)
        ]
        if len(matches) != 1:
            return None
        mapping, concept = matches[0]
        return ApprovedFactMapping(
            mapping_id=mapping.id,
            canonical_concept_id=concept.id,
            canonical_concept_code=concept.code,
            fact_nature=FactNature(concept.fact_nature),
            default_unit_type=UnitType(concept.default_unit_type),
            accounting_standard=fact.taxonomy or "PROVIDER_REPORTED",
            mapping_version=mapping.mapping_version,
        )

    def get_or_create_financial_period(self, value: FinancialPeriodWrite) -> UUID:
        values = asdict(value)
        conditions = tuple(
            getattr(FinancialPeriod, field_name) == field_value
            for field_name, field_value in values.items()
        )
        existing = self._session.scalar(select(FinancialPeriod).where(*conditions))
        if existing is not None:
            return existing.id
        period = FinancialPeriod(**values)
        self._session.add(period)
        self._session.flush()
        return period.id

    def get_or_create_normalized_fact(
        self,
        value: NormalizedFinancialFactWrite,
    ) -> tuple[UUID, bool]:
        existing = self._session.scalar(
            select(NormalizedFinancialFact).where(
                NormalizedFinancialFact.snapshot_id == value.snapshot_id,
                NormalizedFinancialFact.source_financial_fact_id == value.source_financial_fact_id,
                NormalizedFinancialFact.mapping_version == value.mapping_version,
                NormalizedFinancialFact.normalization_version == value.normalization_version,
                NormalizedFinancialFact.is_derived_from_cumulative
                == value.is_derived_from_cumulative,
            )
        )
        if existing is not None:
            expected = asdict(value)
            expected["fact_nature"] = value.fact_nature.value
            if any(
                getattr(existing, key) != expected_value for key, expected_value in expected.items()
            ):
                raise FinancialSeedConflictError(
                    f"normalized fact conflict for source {value.source_financial_fact_id}"
                )
            return existing.id, False
        values = asdict(value)
        values["fact_nature"] = value.fact_nature.value
        fact = NormalizedFinancialFact(**values)
        self._session.add(fact)
        self._session.flush()
        return fact.id, True

    def get_or_create_normalized_fact_input(
        self,
        value: NormalizedFactInputWrite,
    ) -> tuple[UUID, bool]:
        existing = self._session.scalar(
            select(NormalizedFactInput).where(
                NormalizedFactInput.normalized_fact_id == value.normalized_fact_id,
                NormalizedFactInput.input_role == value.input_role,
                NormalizedFactInput.input_normalized_fact_id == value.input_normalized_fact_id,
            )
        )
        if existing is not None:
            if existing.input_ordinal != value.input_ordinal:
                raise FinancialSeedConflictError(
                    f"normalized lineage conflict for fact {value.normalized_fact_id}"
                )
            return existing.id, False
        lineage = NormalizedFactInput(**asdict(value))
        self._session.add(lineage)
        self._session.flush()
        return lineage.id, True

    def apply_financial_reference_seed(
        self,
        manifest: FinancialReferenceSeedManifest,
    ) -> tuple[int, int]:
        inserted = 0
        existing = 0
        for concept_record in manifest.concepts:
            values: dict[str, object] = {
                "id": concept_record.id,
                "code": concept_record.code,
                "name": concept_record.name,
                "statement_type": concept_record.statement_type,
                "fact_nature": concept_record.fact_nature,
                "default_unit_type": concept_record.default_unit_type,
                "supports_duration": concept_record.supports_duration,
                "supports_instant": concept_record.supports_instant,
                "supports_cumulative": concept_record.supports_cumulative,
                "supports_ttm": concept_record.supports_ttm,
                "allows_negative": concept_record.allows_negative,
                "description": concept_record.description,
                "version": concept_record.version,
                "status": concept_record.status,
            }
            concept_by_id = self._session.get(CanonicalFinancialConcept, concept_record.id)
            concept_by_natural = self._session.scalar(
                select(CanonicalFinancialConcept).where(
                    CanonicalFinancialConcept.code == concept_record.code
                )
            )
            if self._apply_seed_model(
                by_id=concept_by_id,
                by_natural=concept_by_natural,
                record_id=concept_record.id,
                values=values,
                instance=CanonicalFinancialConcept(**values),
                label=f"concept:{concept_record.code}",
            ):
                inserted += 1
            else:
                existing += 1

        for formula_record in manifest.formulas:
            values = {
                "id": formula_record.id,
                "metric_code": formula_record.metric_code,
                "name": formula_record.name,
                "formula_expression": formula_record.formula_expression,
                "formula_version": formula_record.formula_version,
                "required_concepts": list(formula_record.required_inputs),
                "optional_concepts": list(formula_record.optional_inputs),
                "period_requirement": formula_record.period_requirement,
                "currency_requirement": formula_record.currency_requirement,
                "denominator_policy": formula_record.denominator_policy,
                "negative_value_policy": formula_record.negative_value_policy,
                "status": formula_record.status,
                "effective_from": None,
                "effective_to": None,
            }
            formula_by_id = self._session.get(FormulaDefinition, formula_record.id)
            formula_by_natural = self._session.scalar(
                select(FormulaDefinition).where(
                    FormulaDefinition.metric_code == formula_record.metric_code,
                    FormulaDefinition.formula_version == formula_record.formula_version,
                )
            )
            if self._apply_seed_model(
                by_id=formula_by_id,
                by_natural=formula_by_natural,
                record_id=formula_record.id,
                values=values,
                instance=FormulaDefinition(**values),
                label=(f"formula:{formula_record.metric_code}:{formula_record.formula_version}"),
            ):
                inserted += 1
            else:
                existing += 1
        return inserted, existing

    def _apply_seed_model(
        self,
        *,
        by_id: CanonicalFinancialConcept | FormulaDefinition | None,
        by_natural: CanonicalFinancialConcept | FormulaDefinition | None,
        record_id: UUID,
        values: Mapping[str, object],
        instance: CanonicalFinancialConcept | FormulaDefinition,
        label: str,
    ) -> bool:
        if by_id is not None and by_natural is not None and by_id.id != by_natural.id:
            raise FinancialSeedConflictError(f"seed key collision for {label}")
        existing = by_id if by_id is not None else by_natural
        if existing is not None:
            if existing.id != record_id:
                raise FinancialSeedConflictError(f"seed UUID collision for {label}")
            mismatches = tuple(
                sorted(
                    field_name
                    for field_name, expected in values.items()
                    if getattr(existing, field_name) != expected
                )
            )
            if mismatches:
                raise FinancialSeedConflictError(
                    f"seed conflict for {label}: {', '.join(mismatches)}"
                )
            return False
        self._session.add(instance)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise FinancialSeedConflictError(f"database rejected seed record {label}") from error
        return True


def _metric_record(metric: DerivedMetric) -> DerivedMetricRecord:
    return DerivedMetricRecord(
        id=metric.id,
        calculation_run_id=metric.calculation_run_id,
        security_id=metric.security_id,
        snapshot_id=metric.snapshot_id,
        metric_code=metric.metric_code,
        metric_period=metric.metric_period,
        period_end=metric.period_end,
        value=metric.value,
        value_state=metric.value_state,
        unit=metric.unit,
        currency_code=metric.currency_code,
        quality_status=QualityStatus(metric.quality_status),
        formula_version=metric.formula_version,
        warning_codes=tuple(str(value) for value in metric.warning_codes),
    )
