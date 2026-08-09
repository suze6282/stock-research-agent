"""Versioned, offline seed manifest for the V0.1 security master samples."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel

from stock_research_agent.domain.securities.enums import (
    ExchangeAliasType,
    IdentifierScheme,
    IssuerStatus,
    ListingStatus,
    MasterDataStatus,
    SecurityAliasType,
    SecurityType,
)
from stock_research_agent.domain.securities.repositories import SecurityMasterSeedRepository
from stock_research_agent.domain.securities.schemas import (
    SecurityMasterSeedManifest,
    SeedExchange,
    SeedExchangeAlias,
    SeedIssuer,
    SeedIssuerIdentifier,
    SeedMarket,
    SeedResult,
    SeedSecurity,
    SeedSecurityAlias,
)


@dataclass(frozen=True, slots=True)
class SeedProvenanceEntry:
    record_key: str
    field_name: str
    value: object
    source_kind: str
    source_reference: str


CN_MARKET_ID = UUID("10000000-0000-0000-0000-000000000001")
US_MARKET_ID = UUID("10000000-0000-0000-0000-000000000002")
XSHG_EXCHANGE_ID = UUID("20000000-0000-0000-0000-000000000001")
XNAS_EXCHANGE_ID = UUID("20000000-0000-0000-0000-000000000002")
INDUSTRIAL_FII_ISSUER_ID = UUID("30000000-0000-0000-0000-000000000001")
MICRON_ISSUER_ID = UUID("30000000-0000-0000-0000-000000000002")
MICRON_CIK_ID = UUID("31000000-0000-0000-0000-000000000001")
INDUSTRIAL_FII_SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
MICRON_SECURITY_ID = UUID("40000000-0000-0000-0000-000000000002")

SECURITY_MASTER_SEED_V0 = SecurityMasterSeedManifest(
    version="security-master-v0.1.0",
    evidence_paths=(
        "docs/sample-data-validation/601138.SH.md",
        "docs/sample-data-validation/MU.md",
        "docs/product-scope-v0.1.md",
    ),
    markets=(
        SeedMarket(
            id=CN_MARKET_ID,
            code="CN_A",
            name="China A Shares",
            country_code="CN",
            default_currency_code="CNY",
            status=MasterDataStatus.UNKNOWN,
        ),
        SeedMarket(
            id=US_MARKET_ID,
            code="US_EQUITY",
            name="US Equity",
            country_code="US",
            default_currency_code="USD",
            status=MasterDataStatus.UNKNOWN,
        ),
    ),
    exchanges=(
        SeedExchange(
            id=XSHG_EXCHANGE_ID,
            market_id=CN_MARKET_ID,
            mic="XSHG",
            name="Shanghai Stock Exchange",
            short_name="SSE",
            country_code="CN",
            timezone="Asia/Shanghai",
            default_currency_code="CNY",
            status=MasterDataStatus.UNKNOWN,
        ),
        SeedExchange(
            id=XNAS_EXCHANGE_ID,
            market_id=US_MARKET_ID,
            mic="XNAS",
            name="Nasdaq",
            short_name="NASDAQ",
            country_code="US",
            timezone="America/New_York",
            default_currency_code="USD",
            status=MasterDataStatus.UNKNOWN,
        ),
    ),
    exchange_aliases=(
        SeedExchangeAlias(
            id=UUID("21000000-0000-0000-0000-000000000001"),
            exchange_id=XSHG_EXCHANGE_ID,
            alias=".SH",
            normalized_alias="SH",
            alias_type=ExchangeAliasType.SUFFIX,
        ),
        SeedExchangeAlias(
            id=UUID("21000000-0000-0000-0000-000000000002"),
            exchange_id=XSHG_EXCHANGE_ID,
            alias="SSE",
            normalized_alias="SSE",
            alias_type=ExchangeAliasType.SHORT_NAME,
        ),
        SeedExchangeAlias(
            id=UUID("21000000-0000-0000-0000-000000000003"),
            exchange_id=XSHG_EXCHANGE_ID,
            alias="XSHG",
            normalized_alias="XSHG",
            alias_type=ExchangeAliasType.MIC,
        ),
        SeedExchangeAlias(
            id=UUID("21000000-0000-0000-0000-000000000004"),
            exchange_id=XNAS_EXCHANGE_ID,
            alias="NASDAQ",
            normalized_alias="NASDAQ",
            alias_type=ExchangeAliasType.DISPLAY_NAME,
        ),
        SeedExchangeAlias(
            id=UUID("21000000-0000-0000-0000-000000000005"),
            exchange_id=XNAS_EXCHANGE_ID,
            alias="XNAS",
            normalized_alias="XNAS",
            alias_type=ExchangeAliasType.MIC,
        ),
    ),
    issuers=(
        SeedIssuer(
            id=INDUSTRIAL_FII_ISSUER_ID,
            legal_name="富士康工业互联网股份有限公司",
            normalized_legal_name="富士康工业互联网股份有限公司",
            display_name="工业富联",
            normalized_display_name="工业富联",
            country_code="CN",
            issuer_status=IssuerStatus.UNKNOWN,
        ),
        SeedIssuer(
            id=MICRON_ISSUER_ID,
            legal_name="Micron Technology, Inc.",
            normalized_legal_name="MICRON TECHNOLOGY INC",
            display_name="Micron Technology",
            normalized_display_name="MICRON TECHNOLOGY",
            country_code="US",
            issuer_status=IssuerStatus.UNKNOWN,
        ),
    ),
    issuer_identifiers=(
        SeedIssuerIdentifier(
            id=MICRON_CIK_ID,
            issuer_id=MICRON_ISSUER_ID,
            scheme=IdentifierScheme.SEC_CIK,
            value="0000723125",
            normalized_value="0000723125",
            source_name="SEC EDGAR",
            is_primary=None,
        ),
    ),
    securities=(
        SeedSecurity(
            id=INDUSTRIAL_FII_SECURITY_ID,
            issuer_id=INDUSTRIAL_FII_ISSUER_ID,
            exchange_id=XSHG_EXCHANGE_ID,
            symbol="601138",
            normalized_symbol="601138",
            display_name="工业富联",
            security_type=SecurityType.COMMON_STOCK,
            currency_code="CNY",
            listing_status=ListingStatus.UNKNOWN,
            is_primary_listing=None,
        ),
        SeedSecurity(
            id=MICRON_SECURITY_ID,
            issuer_id=MICRON_ISSUER_ID,
            exchange_id=XNAS_EXCHANGE_ID,
            symbol="MU",
            normalized_symbol="MU",
            display_name="Micron Technology",
            security_type=SecurityType.COMMON_STOCK,
            currency_code="USD",
            listing_status=ListingStatus.UNKNOWN,
            is_primary_listing=None,
        ),
    ),
    security_aliases=(
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000001"),
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="601138.SH",
            normalized_alias="601138.SH",
            alias_type=SecurityAliasType.SYMBOL_WITH_EXCHANGE,
            source_name="Stage 1 validation",
        ),
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000002"),
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="工业富联",
            normalized_alias="工业富联",
            alias_type=SecurityAliasType.COMPANY_SHORT_NAME,
            locale=None,
            source_name="Stage 1 validation",
        ),
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000003"),
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            alias="富士康工业互联网股份有限公司",
            normalized_alias="富士康工业互联网股份有限公司",
            alias_type=SecurityAliasType.LEGAL_NAME,
            locale=None,
            source_name="Stage 1 validation",
        ),
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000004"),
            security_id=MICRON_SECURITY_ID,
            alias="NASDAQ:MU",
            normalized_alias="NASDAQ:MU",
            alias_type=SecurityAliasType.SYMBOL_WITH_EXCHANGE,
            source_name="Stage 3 required mapping",
        ),
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000005"),
            security_id=MICRON_SECURITY_ID,
            alias="Micron",
            normalized_alias="MICRON",
            alias_type=SecurityAliasType.COMPANY_SHORT_NAME,
            locale=None,
            source_name="Stage 1 validation",
        ),
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000006"),
            security_id=MICRON_SECURITY_ID,
            alias="Micron Technology",
            normalized_alias="MICRON TECHNOLOGY",
            alias_type=SecurityAliasType.ENGLISH_NAME,
            locale=None,
            source_name="Stage 1 validation",
        ),
        SeedSecurityAlias(
            id=UUID("50000000-0000-0000-0000-000000000007"),
            security_id=MICRON_SECURITY_ID,
            alias="Micron Technology, Inc.",
            normalized_alias="MICRON TECHNOLOGY INC",
            alias_type=SecurityAliasType.LEGAL_NAME,
            locale=None,
            source_name="Stage 1 validation",
        ),
    ),
)


def _field_provenance(
    record_key: str,
    record: BaseModel,
    *,
    stage1_fields: frozenset[str] = frozenset(),
    stage1_reference: str | None = None,
) -> tuple[SeedProvenanceEntry, ...]:
    entries: list[SeedProvenanceEntry] = []
    for field_name, value in record.model_dump(mode="json").items():
        if field_name in stage1_fields:
            if stage1_reference is None:
                raise RuntimeError(f"missing Stage 1 reference for {record_key}.{field_name}")
            source_kind = "STAGE_1_EVIDENCE"
            source_reference = stage1_reference
        elif field_name.startswith("normalized_"):
            source_kind = "DETERMINISTIC_NORMALIZATION"
            source_reference = "src/stock_research_agent/domain/securities/normalization.py"
        else:
            source_kind = "STAGE_3_REQUIRED_MAPPING"
            source_reference = "Stage 3 specification and reviewed implementation plan"
        entries.append(
            SeedProvenanceEntry(
                record_key=record_key,
                field_name=field_name,
                value=value,
                source_kind=source_kind,
                source_reference=source_reference,
            )
        )
    return tuple(entries)


_FII_EVIDENCE = "docs/sample-data-validation/601138.SH.md"
_MICRON_EVIDENCE = "docs/sample-data-validation/MU.md"

SECURITY_MASTER_SEED_V0_PROVENANCE = tuple(
    entry
    for record_key, record, stage1_fields, stage1_reference in (
        *(
            (f"market:{item.code}", item, frozenset(), None)
            for item in SECURITY_MASTER_SEED_V0.markets
        ),
        (
            "exchange:XSHG",
            SECURITY_MASTER_SEED_V0.exchanges[0],
            frozenset({"name", "country_code", "default_currency_code"}),
            _FII_EVIDENCE,
        ),
        (
            "exchange:XNAS",
            SECURITY_MASTER_SEED_V0.exchanges[1],
            frozenset({"name", "country_code", "default_currency_code"}),
            _MICRON_EVIDENCE,
        ),
        *(
            (
                f"exchange_alias:{item.normalized_alias}",
                item,
                frozenset(),
                None,
            )
            for item in SECURITY_MASTER_SEED_V0.exchange_aliases
        ),
        (
            f"issuer:{INDUSTRIAL_FII_ISSUER_ID}",
            SECURITY_MASTER_SEED_V0.issuers[0],
            frozenset({"legal_name", "display_name", "country_code"}),
            _FII_EVIDENCE,
        ),
        (
            f"issuer:{MICRON_ISSUER_ID}",
            SECURITY_MASTER_SEED_V0.issuers[1],
            frozenset({"legal_name", "display_name", "country_code"}),
            _MICRON_EVIDENCE,
        ),
        (
            f"issuer_identifier:{MICRON_CIK_ID}",
            SECURITY_MASTER_SEED_V0.issuer_identifiers[0],
            frozenset({"scheme", "value", "source_name"}),
            _MICRON_EVIDENCE,
        ),
        (
            f"security:{INDUSTRIAL_FII_SECURITY_ID}",
            SECURITY_MASTER_SEED_V0.securities[0],
            frozenset({"symbol", "display_name", "currency_code"}),
            _FII_EVIDENCE,
        ),
        (
            f"security:{MICRON_SECURITY_ID}",
            SECURITY_MASTER_SEED_V0.securities[1],
            frozenset({"symbol", "display_name", "currency_code"}),
            _MICRON_EVIDENCE,
        ),
        *(
            (
                f"security_alias:{item.id}",
                item,
                frozenset({"alias"}),
                _FII_EVIDENCE,
            )
            for item in SECURITY_MASTER_SEED_V0.security_aliases
            if item.security_id == INDUSTRIAL_FII_SECURITY_ID
        ),
        *(
            (
                f"security_alias:{item.id}",
                item,
                frozenset() if item.alias == "NASDAQ:MU" else frozenset({"alias"}),
                None if item.alias == "NASDAQ:MU" else _MICRON_EVIDENCE,
            )
            for item in SECURITY_MASTER_SEED_V0.security_aliases
            if item.security_id == MICRON_SECURITY_ID
        ),
    )
    for entry in _field_provenance(
        record_key,
        record,
        stage1_fields=stage1_fields,
        stage1_reference=stage1_reference,
    )
)


class SecurityMasterSeedService:
    def __init__(self, manifest: SecurityMasterSeedManifest = SECURITY_MASTER_SEED_V0) -> None:
        self._manifest = manifest

    def seed(self, repository: SecurityMasterSeedRepository) -> SeedResult:
        repository.acquire_seed_lock(self._manifest.version)
        return repository.apply_manifest(self._manifest)
