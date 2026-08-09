from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from stock_research_agent.providers.cache import (
    InMemoryProviderCacheStore,
    ProviderCacheKey,
    ProviderCacheService,
    ProviderCacheStatus,
)

NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)


def _key(**changes: object) -> ProviderCacheKey:
    values: dict[str, object] = {
        "provider_definition_id": uuid4(),
        "provider_capability_id": uuid4(),
        "license_policy_id": uuid4(),
        "adapter_version": "1.0.0",
        "policy_version": "1.0.0",
        "license_policy_version": "1.0.0",
        "request_identity": "a" * 64,
    }
    values.update(changes)
    return ProviderCacheKey.model_validate(values)


def test_cache_key_binds_all_governance_versions_and_scope() -> None:
    baseline = _key()
    fields: dict[str, object] = {
        "provider_definition_id": uuid4(),
        "provider_capability_id": uuid4(),
        "license_policy_id": uuid4(),
        "adapter_version": "2.0.0",
        "policy_version": "2.0.0",
        "license_policy_version": "2.0.0",
        "request_identity": "b" * 64,
    }

    for field, replacement in fields.items():
        changed = baseline.model_copy(update={field: replacement})
        assert changed.checksum != baseline.checksum


def test_cache_put_and_get_are_explicitly_license_gated() -> None:
    service = ProviderCacheService(InMemoryProviderCacheStore())
    key = _key()
    artifact_id = uuid4()

    blocked = service.put(
        key,
        artifact_id=artifact_id,
        artifact_checksum="b" * 64,
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
        cache_permitted=False,
    )
    assert blocked.status is ProviderCacheStatus.BLOCKED
    assert blocked.reason_code == "LICENSE_CACHE_PROHIBITED"
    assert service.get(key, now=NOW).status is ProviderCacheStatus.MISS

    stored = service.put(
        key,
        artifact_id=artifact_id,
        artifact_checksum="b" * 64,
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
        cache_permitted=True,
    )
    assert stored.status is ProviderCacheStatus.STORED
    hit = service.get(key, now=NOW)
    assert hit.status is ProviderCacheStatus.HIT
    assert hit.artifact_id == artifact_id
    assert hit.artifact_checksum == "b" * 64


def test_expired_or_cross_scope_cache_never_reuses_artifact() -> None:
    service = ProviderCacheService(InMemoryProviderCacheStore())
    key = _key()
    service.put(
        key,
        artifact_id=uuid4(),
        artifact_checksum="c" * 64,
        expires_at=NOW + timedelta(seconds=1),
        now=NOW,
        cache_permitted=True,
    )

    assert service.get(key, now=NOW + timedelta(seconds=1)).status is ProviderCacheStatus.MISS
    changed_license = key.model_copy(update={"license_policy_id": UUID(int=1)})
    assert service.get(changed_license, now=NOW).status is ProviderCacheStatus.MISS


def test_cache_rejects_invalid_expiry_without_writing() -> None:
    store = InMemoryProviderCacheStore()
    service = ProviderCacheService(store)
    decision = service.put(
        _key(),
        artifact_id=uuid4(),
        artifact_checksum="d" * 64,
        expires_at=NOW,
        now=NOW,
        cache_permitted=True,
    )
    assert decision.status is ProviderCacheStatus.BLOCKED
    assert decision.reason_code == "INVALID_CACHE_EXPIRY"
    assert store.entry_count == 0
