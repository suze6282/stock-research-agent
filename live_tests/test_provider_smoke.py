from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.live


@dataclass(frozen=True)
class LiveProviderSpec:
    provider: str
    endpoint_type: str
    required_environment: tuple[str, ...]


@dataclass(frozen=True)
class LiveSmokeResult:
    provider: str
    endpoint: str
    checked_at: str
    status: str
    http_result: str
    authenticated: bool
    required_fields_satisfied: bool
    raw_payload_created: bool
    snapshot_created: bool
    blockers: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True)


_PROVIDERS = (
    LiveProviderSpec(
        provider="TUSHARE_PRO",
        endpoint_type="TUSHARE_API",
        required_environment=("TUSHARE_TOKEN", "TUSHARE_CACHE_PERMISSION_CONFIRMED"),
    ),
    LiveProviderSpec(
        provider="LICENSED_US_EOD",
        endpoint_type="LICENSED_US_EOD_API",
        required_environment=(
            "US_EOD_PROVIDER_CODE",
            "US_EOD_API_KEY",
            "US_EOD_LICENSE_CONFIRMED",
        ),
    ),
    LiveProviderSpec(
        provider="SEC_ARCHIVES",
        endpoint_type="SEC_ARCHIVES_API",
        required_environment=("SEC_CONTACT_EMAIL", "SEC_USER_AGENT"),
    ),
)


def _blocked_result(spec: LiveProviderSpec) -> LiveSmokeResult:
    blockers: list[str] = []
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        blockers.append("RUN_LIVE_PROVIDER_TESTS_NOT_ENABLED")
    blockers.extend(
        f"{name}_NOT_CONFIGURED"
        for name in spec.required_environment
        if not os.getenv(name, "").strip()
    )
    if not blockers:
        blockers.append("LIVE_PROVIDER_ADAPTER_NOT_IMPLEMENTED")

    return LiveSmokeResult(
        provider=spec.provider,
        endpoint=spec.endpoint_type,
        checked_at=datetime.now(UTC).isoformat(),
        status="BLOCKED",
        http_result="NOT_ATTEMPTED",
        authenticated=False,
        required_fields_satisfied=False,
        raw_payload_created=False,
        snapshot_created=False,
        blockers=tuple(blockers),
    )


@pytest.mark.parametrize("spec", _PROVIDERS, ids=lambda spec: spec.provider)
def test_live_provider_smoke_is_honestly_blocked_without_authorized_adapter(
    spec: LiveProviderSpec,
    record_property: pytest.RecordProperty,
) -> None:
    result = _blocked_result(spec)
    record_property("live_smoke_result", result.to_json())

    pytest.skip(f"BLOCKED {result.to_json()}")
