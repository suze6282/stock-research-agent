from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from stock_research_agent.domain.live_evidence.snapshot import (
    IngestionSnapshotBindingWrite,
    bind_manifest_to_snapshot,
    verify_snapshot_immutability,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")


def _binding() -> object:
    return bind_manifest_to_snapshot(
        IngestionSnapshotBindingWrite(
            manifest_id=uuid4(),
            manifest_checksum="a" * 64,
            manifest_security_id=SECURITY_ID,
            snapshot_id=uuid4(),
            snapshot_checksum="b" * 64,
            snapshot_security_id=SECURITY_ID,
            security_id=SECURITY_ID,
            research_as_of_time=NOW,
            source_published_at=NOW,
            bound_at=NOW,
        )
    )


def test_terminal_snapshot_and_exact_binding_are_immutable() -> None:
    binding = _binding()
    decision = verify_snapshot_immutability(
        binding.snapshot_id,
        snapshot_status="COMPLETE",
        binding=binding,
        expected_binding_checksum=binding.binding_checksum,
    )

    assert decision.status == "PASS"
    assert decision.warning_codes == ()


def test_nonterminal_snapshot_fails_closed() -> None:
    binding = _binding()
    decision = verify_snapshot_immutability(
        binding.snapshot_id,
        snapshot_status="BUILDING",
        binding=binding,
        expected_binding_checksum=binding.binding_checksum,
    )

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("SNAPSHOT_IMMUTABLE",)


def test_missing_or_changed_binding_fails_closed() -> None:
    binding = _binding()
    missing = verify_snapshot_immutability(
        binding.snapshot_id,
        snapshot_status="COMPLETE",
        binding=None,
        expected_binding_checksum=binding.binding_checksum,
    )
    changed = verify_snapshot_immutability(
        binding.snapshot_id,
        snapshot_status="COMPLETE",
        binding=binding,
        expected_binding_checksum="c" * 64,
    )

    assert missing.warning_codes == ("SNAPSHOT_BINDING_IMMUTABLE",)
    assert changed.warning_codes == ("SNAPSHOT_BINDING_IMMUTABLE",)
