from __future__ import annotations

import inspect
from importlib import import_module
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql


def _modules() -> SimpleNamespace:
    try:
        models = import_module("stock_research_agent.db.models.reports")
        repositories = import_module("stock_research_agent.db.repositories.reports")
        ports = import_module("stock_research_agent.domain.reports.repositories")
        schemas = import_module("stock_research_agent.domain.reports.schemas")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 report persistence boundary is missing")
    return SimpleNamespace(
        ReportRequest=models.ReportRequest,
        SqlAlchemyReportRepository=repositories.SqlAlchemyReportRepository,
        ReportInputRepository=ports.ReportInputRepository,
        ReportRequestRepository=ports.ReportRequestRepository,
        ReportRequestRecord=schemas.ReportRequestRecord,
        ReportRequestWrite=schemas.ReportRequestWrite,
    )


def test_report_request_model_has_exact_manifest_columns_and_restrictive_fks() -> None:
    modules = _modules()
    table = modules.ReportRequest.__table__
    expected = {
        "id",
        "research_package_id",
        "research_agent_run_id",
        "research_request_id",
        "security_id",
        "issuer_id",
        "snapshot_id",
        "research_as_of_time",
        "report_type",
        "report_locale",
        "template_name",
        "template_version",
        "report_policy_version",
        "reflection_policy_version",
        "requested_sections",
        "include_evidence_appendix",
        "include_claim_index",
        "max_excerpt_length",
        "manifest_schema_version",
        "manifest",
        "manifest_checksum",
        "package_checksum",
        "claims_checksum",
        "evidence_checksum",
        "links_checksum",
        "citations_checksum",
        "lineage_checksum",
        "idempotency_key",
        "created_at",
    }

    assert set(table.columns.keys()) == expected
    assert table.primary_key.name == "pk_report_requests"
    assert {fk.ondelete for fk in table.foreign_keys} == {"RESTRICT"}
    assert {fk.target_fullname for fk in table.foreign_keys} == {
        "research_packages.id",
        "research_agent_runs.id",
        "research_requests.id",
        "securities.id",
        "issuers.id",
        "data_snapshots.id",
        "report_policies.version",
        "runtime_reflection_policies.version",
    }


def test_report_request_model_has_named_bounds_uniqueness_and_query_index() -> None:
    modules = _modules()
    table = modules.ReportRequest.__table__
    constraint_names = {item.name for item in table.constraints}
    index_names = {item.name for item in table.indexes}

    assert "uq_report_requests_idempotency_key" in constraint_names
    assert {
        "ck_report_requests_type",
        "ck_report_requests_locale",
        "ck_report_requests_excerpt_length",
        "ck_report_requests_checksums",
        "ck_report_requests_manifest_size",
    }.issubset(constraint_names)
    assert "ix_report_requests_research_package" in index_names


def test_repository_ports_are_runtime_checkable_and_transaction_neutral() -> None:
    modules = _modules()
    source = inspect.getsource(modules.SqlAlchemyReportRepository)

    assert getattr(modules.ReportInputRepository, "_is_runtime_protocol", False)
    assert getattr(modules.ReportRequestRepository, "_is_runtime_protocol", False)
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "delete(" not in source
    assert "update(" not in source


def test_package_bundle_query_is_parameterized_stable_and_stage7_read_only() -> None:
    modules = _modules()
    source = inspect.getsource(modules.SqlAlchemyReportRepository.get_package_bundle)

    assert source.count(".order_by(") >= 4
    assert "ResearchClaim.id" in source
    assert "ResearchEvidence.id" in source
    assert "ClaimEvidenceLink.id" in source
    assert "CitationAnchor.id" in source
    assert ".add(" not in source
    assert ".flush(" not in source


class _ScalarOnlySession:
    def __init__(self) -> None:
        self.statement: object | None = None

    def scalar(self, statement: object) -> None:
        self.statement = statement
        return None


def test_missing_package_uses_bound_parameter_and_returns_none() -> None:
    modules = _modules()
    session = _ScalarOnlySession()
    repository = modules.SqlAlchemyReportRepository(session)
    package_id = UUID("12345678-1234-5678-1234-567812345678")

    assert repository.get_package_bundle(package_id) is None
    compiled = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
    assert "research_packages" in compiled
    assert "12345678-1234-5678-1234-567812345678" not in compiled
