from __future__ import annotations

from uuid import uuid4

import pytest

from stock_research_agent.domain.data_access.enums import AccessMode, DataOrigin, LiveStatus
from stock_research_agent.domain.live_evidence.artifacts import (
    ArtifactSourceContext,
    classify_artifact_source,
)
from stock_research_agent.domain.live_evidence.enums import EvidenceSourceType
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (
            ArtifactSourceContext(
                provider_request_log_id=None,
                manual_evidence_import_request_id=uuid4(),
                data_origin=DataOrigin.FIXTURE,
                access_mode=AccessMode.OFFLINE,
                live_status=LiveStatus.NOT_LIVE,
                synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
            ),
            EvidenceSourceType.MANUAL_IMPORT,
        ),
        (
            ArtifactSourceContext(
                provider_request_log_id=uuid4(),
                manual_evidence_import_request_id=None,
                data_origin=DataOrigin.LIVE,
                access_mode=AccessMode.ONLINE,
                live_status=LiveStatus.LIVE,
                synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
            ),
            EvidenceSourceType.PROVIDER_LIVE,
        ),
        (
            ArtifactSourceContext(
                provider_request_log_id=uuid4(),
                manual_evidence_import_request_id=None,
                data_origin=DataOrigin.FIXTURE,
                access_mode=AccessMode.OFFLINE,
                live_status=LiveStatus.NOT_LIVE,
                synthetic_status=ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            ),
            EvidenceSourceType.SYNTHETIC_TEST,
        ),
        (
            ArtifactSourceContext(
                provider_request_log_id=uuid4(),
                manual_evidence_import_request_id=None,
                data_origin=DataOrigin.FIXTURE,
                access_mode=AccessMode.OFFLINE,
                live_status=LiveStatus.NOT_LIVE,
                synthetic_status=ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT,
            ),
            EvidenceSourceType.OFFLINE_FIXTURE,
        ),
    ],
)
def test_source_mechanisms_are_mutually_exclusive_and_explicit(
    context: ArtifactSourceContext,
    expected: EvidenceSourceType,
) -> None:
    assert classify_artifact_source(context) is expected


@pytest.mark.parametrize(
    "context",
    [
        ArtifactSourceContext(
            provider_request_log_id=uuid4(),
            manual_evidence_import_request_id=uuid4(),
            data_origin=DataOrigin.LIVE,
            access_mode=AccessMode.ONLINE,
            live_status=LiveStatus.LIVE,
            synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
        ),
        ArtifactSourceContext(
            provider_request_log_id=None,
            manual_evidence_import_request_id=None,
            data_origin=DataOrigin.FIXTURE,
            access_mode=AccessMode.OFFLINE,
            live_status=LiveStatus.NOT_LIVE,
            synthetic_status=ProviderSyntheticStatus.UNKNOWN,
        ),
        ArtifactSourceContext(
            provider_request_log_id=None,
            manual_evidence_import_request_id=uuid4(),
            data_origin=DataOrigin.LIVE,
            access_mode=AccessMode.ONLINE,
            live_status=LiveStatus.LIVE,
            synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
        ),
    ],
)
def test_ambiguous_or_fake_live_source_is_rejected(context: ArtifactSourceContext) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        classify_artifact_source(context)

    assert exc_info.value.code == "ARTIFACT_SOURCE_AMBIGUOUS"
