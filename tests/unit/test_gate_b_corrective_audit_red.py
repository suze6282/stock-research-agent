from __future__ import annotations

from stock_research_agent.domain.live_evidence.gate_b_pilot import GateBAuditView


def test_red_055_operational_audit_view_covers_complete_three_resource_lineage() -> None:
    """GBR-03: the review projection is complete, bounded, and secret-free."""

    required_fields = {
        "grant_id",
        "grant_checksum",
        "approval_id",
        "approval_state",
        "candidate",
        "plan_id",
        "plan_checksum",
        "resources",
        "sync_run_id",
        "attempts",
        "consumptions",
        "artifacts",
        "manifests",
        "document_version_id",
        "citation_ids",
        "data_quality_issues",
        "terminal_validation_id",
        "terminal_status",
        "terminal_stage",
        "warning_codes",
        "stop_reason",
    }
    forbidden_fields = {
        "contact_value",
        "credential_value",
        "user_agent",
        "authorization_header",
        "cookie",
        "body",
    }

    fields = set(GateBAuditView.model_fields)
    assert required_fields <= fields, (
        f"operational projection is missing approved lineage: {sorted(required_fields - fields)}"
    )
    assert fields.isdisjoint(forbidden_fields)
