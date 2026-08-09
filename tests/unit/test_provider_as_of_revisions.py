from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.providers.temporal import (
    ProviderTemporalRecord,
    ProviderTemporalStatus,
    ProviderTemporalValidator,
)

AS_OF = datetime(2026, 7, 31, 12, tzinfo=UTC)


def _record(
    *,
    revision: int = 1,
    source_checksum: str = "a" * 64,
    source_published_at: datetime | None = datetime(2026, 7, 30, tzinfo=UTC),
    retrieved_at: datetime = datetime(2026, 7, 30, 1, tzinfo=UTC),
    supersedes_revision: int | None = None,
    is_restatement: bool = False,
) -> ProviderTemporalRecord:
    return ProviderTemporalRecord(
        provider_definition_id=UUID("11111111-1111-4111-8111-111111111111"),
        provider_capability_id=UUID("22222222-2222-4222-8222-222222222222"),
        source_identity="provider:filing:stable-id",
        revision=revision,
        source_checksum=source_checksum,
        raw_artifact_id=UUID(f"{revision:08x}-3333-4333-8333-333333333333"),
        manifest_id=UUID(f"{revision:08x}-4444-4444-8444-444444444444"),
        source_published_at=source_published_at,
        retrieved_at=retrieved_at,
        supersedes_revision=supersedes_revision,
        is_restatement=is_restatement,
        license_policy_version="1.0.0",
    )


def test_known_published_record_is_eligible_at_research_as_of() -> None:
    result = ProviderTemporalValidator().validate(_record(), AS_OF)

    assert result.status is ProviderTemporalStatus.ELIGIBLE
    assert result.eligible is True
    assert result.warning_codes == ()
    assert result.record.revision == 1


def test_future_publication_is_blocked_even_when_retrieved_earlier() -> None:
    record = _record(source_published_at=datetime(2026, 8, 1, tzinfo=UTC))

    result = ProviderTemporalValidator().validate(record, AS_OF)

    assert result.status is ProviderTemporalStatus.BLOCKED
    assert result.eligible is False
    assert result.warning_codes == ("SOURCE_PUBLISHED_AFTER_AS_OF",)


def test_unknown_publication_is_blocked_in_strict_mode_and_retrieval_never_substitutes() -> None:
    record = _record(source_published_at=None, retrieved_at=datetime(2026, 7, 1, tzinfo=UTC))

    result = ProviderTemporalValidator().validate(record, AS_OF, strict_historical=True)

    assert result.status is ProviderTemporalStatus.BLOCKED
    assert result.eligible is False
    assert result.warning_codes == ("UNKNOWN_PUBLISHED_AT",)


def test_unknown_publication_is_partial_not_pass_in_non_strict_mode() -> None:
    result = ProviderTemporalValidator().validate(
        _record(source_published_at=None),
        AS_OF,
        strict_historical=False,
    )

    assert result.status is ProviderTemporalStatus.PARTIAL
    assert result.eligible is True
    assert result.warning_codes == ("UNKNOWN_PUBLISHED_AT",)


def test_retrieved_after_as_of_is_blocked_without_changing_publication_semantics() -> None:
    record = _record(retrieved_at=datetime(2026, 8, 1, tzinfo=UTC))

    result = ProviderTemporalValidator().validate(record, AS_OF)

    assert result.status is ProviderTemporalStatus.BLOCKED
    assert result.warning_codes == ("RETRIEVED_AFTER_AS_OF",)


def test_exact_existing_revision_is_reused_but_conflicting_overwrite_is_rejected() -> None:
    existing = _record()
    validator = ProviderTemporalValidator((existing,))

    reused = validator.validate(existing, AS_OF)
    assert reused.status is ProviderTemporalStatus.REUSED
    assert reused.preserved_history == (existing,)
    with pytest.raises(ValueError, match="PROVIDER_REVISION_OVERWRITE_FORBIDDEN"):
        validator.validate(_record(source_checksum="b" * 64), AS_OF)


def test_restatement_appends_next_revision_and_preserves_old_artifact_and_manifest() -> None:
    original = _record()
    restatement = _record(
        revision=2,
        source_checksum="b" * 64,
        source_published_at=datetime(2026, 7, 31, 8, tzinfo=UTC),
        supersedes_revision=1,
        is_restatement=True,
    )

    result = ProviderTemporalValidator((original,)).validate(restatement, AS_OF)

    assert result.status is ProviderTemporalStatus.ELIGIBLE
    assert result.append_required is True
    assert result.preserved_history == (original,)
    assert result.record.raw_artifact_id != original.raw_artifact_id
    assert result.record.manifest_id != original.manifest_id


@pytest.mark.parametrize(
    "record",
    (
        _record(revision=2, source_checksum="b" * 64, supersedes_revision=None),
        _record(revision=3, source_checksum="c" * 64, supersedes_revision=1),
        _record(revision=2, source_checksum="a" * 64, supersedes_revision=1),
    ),
)
def test_revision_cannot_skip_history_hide_latest_wins_or_duplicate_old_bytes(
    record: ProviderTemporalRecord,
) -> None:
    with pytest.raises(ValueError, match="PROVIDER_REVISION_APPEND_INVALID"):
        ProviderTemporalValidator((_record(),)).validate(record, AS_OF)


def test_eligible_history_keeps_all_as_of_revisions_instead_of_latest_wins() -> None:
    original = _record()
    restatement = _record(
        revision=2,
        source_checksum="b" * 64,
        source_published_at=datetime(2026, 7, 31, 8, tzinfo=UTC),
        supersedes_revision=1,
        is_restatement=True,
    )
    future = _record(
        revision=3,
        source_checksum="c" * 64,
        source_published_at=datetime(2026, 8, 1, tzinfo=UTC),
        supersedes_revision=2,
        is_restatement=True,
    )

    eligible = ProviderTemporalValidator((original, restatement, future)).eligible_history(AS_OF)

    assert eligible == (original, restatement)
