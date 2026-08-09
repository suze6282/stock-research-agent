from __future__ import annotations

from pathlib import Path

from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.securities.enums import ListingStatus
from stock_research_agent.domain.securities.repositories import SecurityMasterRepository
from stock_research_agent.domain.securities.schemas import SeedResult
from stock_research_agent.domain.securities.seed import (
    SECURITY_MASTER_SEED_V0,
    SECURITY_MASTER_SEED_V0_PROVENANCE,
    SecurityMasterSeedService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeSeedRepository:
    def __init__(self, result: SeedResult) -> None:
        self.result = result
        self.events: list[object] = []

    def acquire_seed_lock(self, seed_version: str) -> None:
        self.events.append(("lock", seed_version))

    def apply_manifest(self, manifest: object) -> SeedResult:
        self.events.append(("apply", manifest))
        return self.result


def test_seed_manifest_contains_only_confirmed_v0_records() -> None:
    manifest = SECURITY_MASTER_SEED_V0

    assert manifest.version == "security-master-v0.1.0"
    assert {market.code for market in manifest.markets} == {"CN_A", "US_EQUITY"}
    assert {exchange.mic for exchange in manifest.exchanges} == {"XSHG", "XNAS"}
    assert {issuer.legal_name for issuer in manifest.issuers} == {
        "富士康工业互联网股份有限公司",
        "Micron Technology, Inc.",
    }
    assert {security.symbol for security in manifest.securities} == {"601138", "MU"}
    assert all(security.listing_status is ListingStatus.UNKNOWN for security in manifest.securities)
    assert all(security.is_primary_listing is None for security in manifest.securities)
    assert [(item.scheme.value, item.normalized_value) for item in manifest.issuer_identifiers] == [
        ("SEC_CIK", "0000723125")
    ]
    assert manifest.issuer_identifiers[0].is_primary is None
    assert all(alias.locale is None for alias in manifest.security_aliases)
    assert not hasattr(manifest, "security_identifiers")


def test_manifest_stores_raw_and_expected_normalized_values() -> None:
    manifest = SECURITY_MASTER_SEED_V0

    assert {item.alias: item.normalized_alias for item in manifest.exchange_aliases} == {
        ".SH": "SH",
        "SSE": "SSE",
        "XSHG": "XSHG",
        "NASDAQ": "NASDAQ",
        "XNAS": "XNAS",
    }
    assert {item.symbol: item.normalized_symbol for item in manifest.securities} == {
        "601138": "601138",
        "MU": "MU",
    }
    assert {item.alias: item.normalized_alias for item in manifest.security_aliases} == {
        "601138.SH": "601138.SH",
        "工业富联": "工业富联",
        "富士康工业互联网股份有限公司": "富士康工业互联网股份有限公司",
        "NASDAQ:MU": "NASDAQ:MU",
        "Micron": "MICRON",
        "Micron Technology": "MICRON TECHNOLOGY",
        "Micron Technology, Inc.": "MICRON TECHNOLOGY INC",
    }


def test_manifest_provenance_separates_stage1_facts_from_stage3_mappings() -> None:
    assert set(SECURITY_MASTER_SEED_V0.evidence_paths) == {
        "docs/sample-data-validation/601138.SH.md",
        "docs/sample-data-validation/MU.md",
        "docs/product-scope-v0.1.md",
    }
    assert {entry.source_kind for entry in SECURITY_MASTER_SEED_V0_PROVENANCE} == {
        "DETERMINISTIC_NORMALIZATION",
        "STAGE_1_EVIDENCE",
        "STAGE_3_REQUIRED_MAPPING",
    }
    for entry in SECURITY_MASTER_SEED_V0_PROVENANCE:
        if entry.source_kind == "STAGE_1_EVIDENCE":
            assert (PROJECT_ROOT / entry.source_reference).is_file()


def test_manifest_provenance_covers_every_persisted_field_with_exact_value() -> None:
    manifest = SECURITY_MASTER_SEED_V0
    records = {
        **{f"market:{item.code}": item for item in manifest.markets},
        **{f"exchange:{item.mic}": item for item in manifest.exchanges},
        **{f"exchange_alias:{item.normalized_alias}": item for item in manifest.exchange_aliases},
        **{f"issuer:{item.id}": item for item in manifest.issuers},
        **{f"issuer_identifier:{item.id}": item for item in manifest.issuer_identifiers},
        **{f"security:{item.id}": item for item in manifest.securities},
        **{f"security_alias:{item.id}": item for item in manifest.security_aliases},
    }
    expected = {
        (record_key, field_name, value)
        for record_key, record in records.items()
        for field_name, value in record.model_dump(mode="json").items()
    }
    actual = {
        (entry.record_key, entry.field_name, entry.value)
        for entry in SECURITY_MASTER_SEED_V0_PROVENANCE
    }

    assert actual == expected


def test_sql_repository_defines_complete_resolution_protocol_surface() -> None:
    required_methods = {
        name
        for name, value in SecurityMasterRepository.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert required_methods <= set(SqlAlchemySecurityMasterRepository.__dict__)


def test_seed_service_acquires_lock_before_applying_manifest() -> None:
    expected = SeedResult(version="security-master-v0.1.0", inserted_count=21, existing_count=0)
    repository = FakeSeedRepository(expected)

    result = SecurityMasterSeedService().seed(repository)

    assert result == expected
    assert repository.events == [
        ("lock", "security-master-v0.1.0"),
        ("apply", SECURITY_MASTER_SEED_V0),
    ]


def test_stage3_migration_contains_no_seed_business_data() -> None:
    migration = (
        PROJECT_ROOT / "migrations" / "versions" / "0002_create_security_master.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("601138", "0000723125", "Micron", "工业富联", "http://", "https://"):
        assert forbidden not in migration
