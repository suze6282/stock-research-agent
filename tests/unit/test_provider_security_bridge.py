from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionManifestRecord,
    ProviderRecord,
    ProviderRecordIdentity,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.securities.enums import SecurityAliasType
from stock_research_agent.providers.bridges.security_master import (
    SecurityAliasAppend,
    SecurityIdentifierAppend,
    SecurityMasterBinding,
    SecurityMasterBridgeContext,
    SecurityMasterProviderBridge,
)

SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_SECURITY_ID = UUID("22222222-2222-4222-8222-222222222222")
RAW_ARTIFACT_ID = UUID("33333333-3333-4333-8333-333333333333")
MANIFEST_ID = UUID("44444444-4444-4444-8444-444444444444")
MANIFEST_CHECKSUM = "a" * 64
PUBLISHED_AT = datetime(2026, 7, 30, 12, tzinfo=UTC)
AS_OF = datetime(2026, 7, 31, 12, tzinfo=UTC)


class _Repository:
    def __init__(self) -> None:
        self.bindings = {
            SECURITY_ID: SecurityMasterBinding(
                security_id=SECURITY_ID,
                issuer_id=UUID("55555555-5555-4555-8555-555555555555"),
                market_code="US_EQUITY",
                exchange_mic="XNAS",
            )
        }
        self.identifier_owners: dict[tuple[str, str], UUID] = {}
        self.alias_owners: dict[tuple[SecurityAliasType, str], tuple[UUID, ...]] = {}
        self.identifiers: list[SecurityIdentifierAppend] = []
        self.aliases: list[SecurityAliasAppend] = []

    def get_security_binding(self, security_id: UUID) -> SecurityMasterBinding | None:
        return self.bindings.get(security_id)

    def find_identifier_owner(self, scheme: str, normalized_value: str) -> UUID | None:
        return self.identifier_owners.get((scheme, normalized_value))

    def find_alias_owners(
        self,
        alias_type: SecurityAliasType,
        normalized_alias: str,
    ) -> tuple[UUID, ...]:
        return self.alias_owners.get((alias_type, normalized_alias), ())

    def append_identifier(self, value: SecurityIdentifierAppend) -> UUID:
        self.identifiers.append(value)
        self.identifier_owners[(value.scheme, value.normalized_value)] = value.security_id
        return uuid4()

    def append_alias(self, value: SecurityAliasAppend) -> UUID:
        self.aliases.append(value)
        key = (value.alias_type, value.normalized_alias)
        self.alias_owners[key] = (*self.alias_owners.get(key, ()), value.security_id)
        return uuid4()


def _record(
    *,
    security_id: UUID = SECURITY_ID,
    market_code: str = "US_EQUITY",
    exchange_mic: str = "XNAS",
    source_published_at: datetime | None = PUBLISHED_AT,
    synthetic_status: ProviderSyntheticStatus = ProviderSyntheticStatus.REAL_VERIFIED,
) -> ProviderRecord:
    return ProviderRecord(
        identity=ProviderRecordIdentity(
            provider_definition_id=UUID("66666666-6666-4666-8666-666666666666"),
            provider_capability_id=UUID("77777777-7777-4777-8777-777777777777"),
            source_identity="sec:issuer:723125",
            record_key="security-master:mu:0001",
            revision=1,
        ),
        raw_artifact_id=RAW_ARTIFACT_ID,
        source_checksum="b" * 64,
        source_published_at=source_published_at,
        status=ProviderRecordStatus.COMPLETE,
        numeric_values={},
        text_values={
            "security_id": str(security_id),
            "market_code": market_code,
            "exchange_mic": exchange_mic,
            "verification_status": "VERIFIED",
            "identifier_scheme": "SEC_CIK",
            "identifier_value": "723125",
            "alias": "NASDAQ:MU",
            "alias_type": "PROVIDER_SYMBOL",
            "locale": "en-US",
        },
        synthetic_status=synthetic_status,
    )


def _batch(record: ProviderRecord) -> ProviderBatch:
    return ProviderBatch(manifest_checksum=MANIFEST_CHECKSUM, records=(record,))


def _manifest(
    batch: ProviderBatch,
    *,
    synthetic_status: ProviderSyntheticStatus = ProviderSyntheticStatus.REAL_VERIFIED,
) -> ProviderIngestionManifestRecord:
    return ProviderIngestionManifestRecord(
        id=MANIFEST_ID,
        raw_artifact_id=RAW_ARTIFACT_ID,
        sync_run_id=UUID("88888888-8888-4888-8888-888888888888"),
        adapter_version="1.0.0",
        parser_version="1.0.0",
        schema_version="1.0.0",
        batch_checksum=batch.batch_checksum,
        record_count=batch.record_count,
        source_published_at=PUBLISHED_AT,
        warning_codes=(),
        synthetic_status=synthetic_status,
        manifest_checksum=MANIFEST_CHECKSUM,
        created_at=AS_OF,
    )


def _context() -> SecurityMasterBridgeContext:
    return SecurityMasterBridgeContext(
        provider_code="SEC_EDGAR_PUBLIC_V1",
        research_as_of_time=AS_OF,
        derived_use_approved=True,
    )


def test_bridge_appends_verified_identifier_and_alias_with_manifest_lineage() -> None:
    repository = _Repository()
    record = _record()
    batch = _batch(record)

    result = SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())

    assert result.security_ids == (SECURITY_ID,)
    assert result.appended_identifier_count == 1
    assert result.appended_alias_count == 1
    assert result.existing_record_count == 0
    assert repository.identifiers[0].normalized_value == "0000723125"
    assert repository.identifiers[0].source_name == (
        "SEC_EDGAR_PUBLIC_V1:manifest:44444444-4444-4444-8444-444444444444"
    )
    assert repository.aliases[0].normalized_alias == "NASDAQ:MU"
    assert repository.aliases[0].source_name == repository.identifiers[0].source_name


def test_bridge_requires_exact_existing_security_without_issuer_guessing() -> None:
    repository = _Repository()
    batch = _batch(_record(security_id=OTHER_SECURITY_ID))

    with pytest.raises(ValueError, match="SECURITY_MAPPING_NOT_FOUND"):
        SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())

    assert repository.identifiers == []
    assert repository.aliases == []


@pytest.mark.parametrize(
    ("market_code", "exchange_mic", "error"),
    (
        ("CN_A", "XNAS", "SECURITY_MARKET_MISMATCH"),
        ("US_EQUITY", "XSHG", "SECURITY_EXCHANGE_MISMATCH"),
    ),
)
def test_bridge_rejects_cross_market_or_exchange_ticker_mapping(
    market_code: str,
    exchange_mic: str,
    error: str,
) -> None:
    repository = _Repository()
    batch = _batch(_record(market_code=market_code, exchange_mic=exchange_mic))

    with pytest.raises(ValueError, match=error):
        SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())


def test_bridge_rejects_synthetic_records_for_real_security_master() -> None:
    repository = _Repository()
    record = _record(synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY)
    batch = _batch(record)

    with pytest.raises(ValueError, match="SYNTHETIC_SECURITY_MASTER_WRITE_FORBIDDEN"):
        SecurityMasterProviderBridge(repository).stage(
            _manifest(batch, synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY),
            batch,
            _context(),
        )


def test_bridge_rejects_identifier_bound_to_another_security() -> None:
    repository = _Repository()
    repository.identifier_owners[("SEC_CIK", "0000723125")] = OTHER_SECURITY_ID
    batch = _batch(_record())

    with pytest.raises(ValueError, match="SECURITY_IDENTIFIER_CONFLICT"):
        SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())


def test_bridge_rejects_provider_alias_bound_to_another_security() -> None:
    repository = _Repository()
    repository.alias_owners[(SecurityAliasType.PROVIDER_SYMBOL, "NASDAQ:MU")] = (OTHER_SECURITY_ID,)
    batch = _batch(_record())

    with pytest.raises(ValueError, match="SECURITY_ALIAS_CONFLICT"):
        SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())


def test_bridge_rejects_future_data_before_any_write() -> None:
    repository = _Repository()
    record = _record(source_published_at=datetime(2026, 8, 2, tzinfo=UTC))
    batch = _batch(record)

    with pytest.raises(ValueError, match="SECURITY_MASTER_FUTURE_DATA"):
        SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())

    assert repository.identifiers == []
    assert repository.aliases == []


def test_bridge_is_idempotent_and_never_overwrites_existing_identity() -> None:
    repository = _Repository()
    repository.identifier_owners[("SEC_CIK", "0000723125")] = SECURITY_ID
    repository.alias_owners[(SecurityAliasType.PROVIDER_SYMBOL, "NASDAQ:MU")] = (SECURITY_ID,)
    batch = _batch(_record())

    result = SecurityMasterProviderBridge(repository).stage(_manifest(batch), batch, _context())

    assert result.appended_identifier_count == 0
    assert result.appended_alias_count == 0
    assert result.existing_record_count == 2
    assert repository.identifiers == []
    assert repository.aliases == []


def test_bridge_validates_manifest_batch_lineage_and_derived_use_approval() -> None:
    repository = _Repository()
    batch = _batch(_record())
    manifest = _manifest(batch)

    with pytest.raises(ValueError, match="DERIVED_USE_NOT_APPROVED"):
        SecurityMasterProviderBridge(repository).stage(
            manifest,
            batch,
            _context().model_copy(update={"derived_use_approved": False}),
        )
    with pytest.raises(ValueError, match="SECURITY_MASTER_BATCH_CHECKSUM_MISMATCH"):
        SecurityMasterProviderBridge(repository).stage(
            manifest.model_copy(update={"batch_checksum": "c" * 64}),
            batch,
            _context(),
        )
    with pytest.raises(ValueError, match="SECURITY_MASTER_MANIFEST_MISMATCH"):
        SecurityMasterProviderBridge(repository).stage(
            manifest,
            batch.model_copy(update={"manifest_checksum": "d" * 64}),
            _context(),
        )
