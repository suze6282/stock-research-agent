"""Explicit Stage 10 Gate B harness; excluded from default pytest and CI."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live
APPROVAL_PHRASE = "批准执行该SEC有限Live验证"


def test_sec_controlled_live_gate_status() -> None:
    approved = os.environ.get("STAGE10_SEC_LIVE_APPROVAL") == APPROVAL_PHRASE
    transport_configured = os.environ.get("STAGE10_SEC_LIVE_TRANSPORT") == "CONFIGURED"
    status = "BLOCKED" if approved and not transport_configured else "NOT_ATTEMPTED"
    assert status in {"NOT_ATTEMPTED", "BLOCKED"}
    assert status != "PASS"
