from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.financials.enums import (
    FactNature,
    QualityStatus,
    UnitType,
)
from stock_research_agent.domain.financials.normalization import FinancialNormalizationService
from stock_research_agent.domain.financials.schemas import (
    ApprovedFactMapping,
    FinancialPeriodWrite,
    NormalizedFactInputWrite,
    NormalizedFinancialFactWrite,
    RawFinancialFactForNormalization,
    SnapshotForNormalization,
)

SNAPSHOT_ID = UUID("90000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
PROVIDER_ID = UUID("50000000-0000-0000-0000-000000000001")
FACT_ID = UUID("80000000-0000-0000-0000-000000000001")
MAPPING_ID = UUID("81000000-0000-0000-0000-000000000001")
CONCEPT_ID = UUID("82000000-0000-0000-0000-000000000001")
AS_OF = datetime(2026, 3, 1, tzinfo=UTC)


class EmptyNormalizationRepository:
    def __init__(self, facts: tuple[RawFinancialFactForNormalization, ...] = ()) -> None:
        self.facts = facts
        self.mapping_lookups = 0

    def get_snapshot_for_normalization(self, snapshot_id: UUID) -> SnapshotForNormalization | None:
        assert snapshot_id == SNAPSHOT_ID
        return SnapshotForNormalization(
            snapshot_id=SNAPSHOT_ID,
            security_id=SECURITY_ID,
            research_as_of_time=AS_OF,
            status="PARTIAL",
        )

    def list_snapshot_financial_facts(
        self, snapshot_id: UUID
    ) -> tuple[RawFinancialFactForNormalization, ...]:
        assert snapshot_id == SNAPSHOT_ID
        return self.facts

    def find_approved_fact_mapping(self, fact: object, as_of: date) -> None:
        self.mapping_lookups += 1
        return None


class RecordingNormalizationRepository(EmptyNormalizationRepository):
    def __init__(self, facts: tuple[RawFinancialFactForNormalization, ...]) -> None:
        super().__init__(facts)
        self.periods: list[FinancialPeriodWrite] = []
        self.normalized_facts: list[NormalizedFinancialFactWrite] = []
        self.normalized_fact_inputs: list[NormalizedFactInputWrite] = []

    def find_approved_fact_mapping(self, fact: object, as_of: date) -> ApprovedFactMapping:
        self.mapping_lookups += 1
        assert as_of == AS_OF.date()
        return ApprovedFactMapping(
            mapping_id=MAPPING_ID,
            canonical_concept_id=CONCEPT_ID,
            canonical_concept_code="REVENUE",
            fact_nature=FactNature.DURATION,
            default_unit_type=UnitType.MONETARY_AMOUNT,
            accounting_standard="TEST_GAAP",
            mapping_version="1.0.0",
        )

    def get_or_create_financial_period(self, value: FinancialPeriodWrite) -> UUID:
        self.periods.append(value)
        return UUID(f"83000000-0000-0000-0000-{len(self.periods):012d}")

    def get_or_create_normalized_fact(
        self, value: NormalizedFinancialFactWrite
    ) -> tuple[UUID, bool]:
        self.normalized_facts.append(value)
        return UUID(f"84000000-0000-0000-0000-{len(self.normalized_facts):012d}"), True

    def get_or_create_normalized_fact_input(
        self, value: NormalizedFactInputWrite
    ) -> tuple[UUID, bool]:
        self.normalized_fact_inputs.append(value)
        return UUID(f"85000000-0000-0000-0000-{len(self.normalized_fact_inputs):012d}"), True


def _raw_fact(*, published_at: datetime | None) -> RawFinancialFactForNormalization:
    return RawFinancialFactForNormalization(
        id=FACT_ID,
        security_id=SECURITY_ID,
        provider_id=PROVIDER_ID,
        provider_code="TEST_FIXTURE",
        statement_type="INCOME_STATEMENT",
        provider_concept="Revenue",
        taxonomy="TEST/1",
        context_id="CONSOLIDATED",
        dimensions=(),
        value=Decimal("100"),
        unit="ONE",
        currency_code="CNY",
        fiscal_year=2025,
        fiscal_quarter=None,
        fiscal_period="FY",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        instant_date=None,
        filed_at=published_at,
        source_published_at=published_at,
        form_type="ANNUAL_REPORT",
        is_annual=True,
        is_cumulative=True,
        is_restated=False,
        retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def test_empty_snapshot_is_honestly_blocked_without_writes() -> None:
    repository = EmptyNormalizationRepository()

    result = FinancialNormalizationService().normalize_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.BLOCKED
    assert result.normalized_fact_count == 0
    assert result.period_count == 0
    assert result.warnings == ("NO_FINANCIAL_FACTS_IN_SNAPSHOT",)
    assert repository.mapping_lookups == 0


def test_unknown_publication_time_is_not_normalized() -> None:
    repository = EmptyNormalizationRepository((_raw_fact(published_at=None),))

    result = FinancialNormalizationService().normalize_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.BLOCKED
    assert result.normalized_fact_count == 0
    assert result.warnings == (f"SOURCE_PUBLISHED_AT_UNKNOWN:{FACT_ID}",)
    assert repository.mapping_lookups == 0


def test_future_published_fact_is_excluded_before_mapping() -> None:
    repository = EmptyNormalizationRepository(
        (_raw_fact(published_at=datetime(2026, 4, 1, tzinfo=UTC)),)
    )

    result = FinancialNormalizationService().normalize_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.BLOCKED
    assert result.normalized_fact_count == 0
    assert result.warnings == (f"FACT_AFTER_RESEARCH_AS_OF:{FACT_ID}",)
    assert repository.mapping_lookups == 0


def test_exact_mapping_creates_period_and_reported_fact_without_mutating_source() -> None:
    raw = replace(
        _raw_fact(published_at=datetime(2026, 2, 1, tzinfo=UTC)),
        is_cumulative=False,
    )
    repository = RecordingNormalizationRepository((raw,))

    result = FinancialNormalizationService().normalize_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.PASS
    assert result.normalized_fact_count == 1
    assert result.period_count == 1
    assert result.warnings == ()
    assert repository.periods[0].period_type == "ANNUAL"
    assert repository.periods[0].is_cumulative is False
    normalized = repository.normalized_facts[0]
    assert normalized.original_value == Decimal("100")
    assert normalized.normalized_value == Decimal("100")
    assert normalized.original_unit == "ONE"
    assert normalized.normalized_unit == "ONE"
    assert normalized.scale_factor == Decimal("1")
    assert normalized.is_reported is True
    assert normalized.is_derived_from_cumulative is False
    assert raw.value == Decimal("100")


def test_eligible_but_unmapped_fact_is_blocked_without_writes() -> None:
    raw = _raw_fact(published_at=datetime(2026, 2, 1, tzinfo=UTC))
    repository = EmptyNormalizationRepository((raw,))

    result = FinancialNormalizationService().normalize_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.BLOCKED
    assert result.normalized_fact_count == 0
    assert result.period_count == 0
    assert result.warnings == (f"NO_APPROVED_MAPPING:{FACT_ID}",)
    assert repository.mapping_lookups == 1


def test_cumulative_a_share_series_creates_four_quarters_with_lineage() -> None:
    published = datetime(2026, 2, 1, tzinfo=UTC)
    base = _raw_fact(published_at=published)
    facts = (
        replace(
            base,
            id=UUID("80000000-0000-0000-0000-000000000011"),
            value=Decimal("10"),
            fiscal_quarter=1,
            fiscal_period="Q1",
            period_end=date(2025, 3, 31),
            is_annual=False,
        ),
        replace(
            base,
            id=UUID("80000000-0000-0000-0000-000000000012"),
            value=Decimal("25"),
            fiscal_quarter=2,
            fiscal_period="H1",
            period_end=date(2025, 6, 30),
            is_annual=False,
        ),
        replace(
            base,
            id=UUID("80000000-0000-0000-0000-000000000013"),
            value=Decimal("37"),
            fiscal_quarter=3,
            fiscal_period="9M",
            period_end=date(2025, 9, 30),
            is_annual=False,
        ),
        replace(
            base,
            id=UUID("80000000-0000-0000-0000-000000000014"),
            value=Decimal("57"),
            fiscal_quarter=None,
            fiscal_period="FY",
            period_end=date(2025, 12, 31),
        ),
    )
    repository = RecordingNormalizationRepository(facts)

    result = FinancialNormalizationService().normalize_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.PASS
    assert result.normalized_fact_count == 8
    assert result.period_count == 8
    derived = [fact for fact in repository.normalized_facts if fact.is_derived_from_cumulative]
    assert [fact.normalized_value for fact in derived] == [
        Decimal("10"),
        Decimal("15"),
        Decimal("12"),
        Decimal("20"),
    ]
    assert all(not fact.is_reported for fact in derived)
    assert len(repository.normalized_fact_inputs) == 7
