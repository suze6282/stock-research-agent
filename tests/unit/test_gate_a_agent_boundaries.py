from __future__ import annotations

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.offline_pipeline import validate_agent_boundary
from stock_research_agent.domain.research_agent.tool_catalog import build_tool_catalog_snapshot
from stock_research_agent.tools.registry import create_tool_metadata_registry


def test_gate_a_catalog_is_read_only_offline_and_without_privileged_services() -> None:
    decision = validate_agent_boundary(
        build_tool_catalog_snapshot(create_tool_metadata_registry()),
        credential_access=False,
        provider_sync=False,
    )

    assert decision.status == "PASS"
    assert decision.warning_codes == ()


@pytest.mark.parametrize(
    ("credential_access", "provider_sync", "code"),
    [
        (True, False, "AGENT_CREDENTIAL_ACCESS_FORBIDDEN"),
        (False, True, "AGENT_PROVIDER_SYNC_FORBIDDEN"),
    ],
)
def test_gate_a_rejects_credential_or_provider_sync_services(
    credential_access: bool,
    provider_sync: bool,
    code: str,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as error:
        validate_agent_boundary(
            build_tool_catalog_snapshot(create_tool_metadata_registry()),
            credential_access=credential_access,
            provider_sync=provider_sync,
        )

    assert error.value.code == code
