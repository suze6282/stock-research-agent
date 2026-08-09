from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from stock_research_agent.db.repositories.providers import SqlAlchemyProviderQueryRepository
from stock_research_agent.domain.providers.queries import (
    PageRequest,
    ProviderQueryPage,
    ProviderQueryResource,
    ProviderQueryService,
    SafeProviderProjection,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SECURITY_ID = UUID("22222222-2222-4222-8222-222222222222")


class _QueryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.override: Mapping[str, object] | None = None

    def _one(self, name: str, *args: object, **kwargs: object) -> Mapping[str, object]:
        self.calls.append((name, args, kwargs))
        return self.override or {
            "resource_type": name,
            "values": {"id": str(RUN_ID), "status": "BLOCKED"},
        }

    def _many(self, name: str, *args: object, **kwargs: object) -> tuple[Mapping[str, object], ...]:
        return (self._one(name, *args, **kwargs),)

    def list_provider_views(self, *, limit: int, offset: int) -> tuple[Mapping[str, object], ...]:
        return self._many("PROVIDER", limit=limit, offset=offset)

    def get_provider_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("PROVIDER", provider_code)

    def list_capability_views(
        self, provider_code: str, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("CAPABILITY", provider_code, limit=limit, offset=offset)

    def get_policy_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("POLICY", provider_code)

    def get_license_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("LICENSE", provider_code)

    def get_health_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("HEALTH", provider_code)

    def get_circuit_view(self, provider_code: str) -> Mapping[str, object]:
        return self._one("CIRCUIT", provider_code)

    def get_sync_run_view(self, run_id: UUID) -> Mapping[str, object]:
        return self._one("SYNC_RUN", run_id)

    def list_attempt_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("ATTEMPT", run_id, limit=limit, offset=offset)

    def list_artifact_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("ARTIFACT", run_id, limit=limit, offset=offset)

    def list_checkpoint_views(
        self, provider_code: str, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("CHECKPOINT", provider_code, limit=limit, offset=offset)

    def list_quality_issue_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("QUALITY_ISSUE", run_id, limit=limit, offset=offset)

    def list_dead_letter_views(
        self, run_id: UUID, *, limit: int, offset: int
    ) -> tuple[Mapping[str, object], ...]:
        return self._many("DEAD_LETTER", run_id, limit=limit, offset=offset)

    def get_readiness_view(self, security_id: UUID) -> Mapping[str, object]:
        return self._one("READINESS", security_id)


def test_page_request_is_bounded_and_has_no_arbitrary_sort_expression() -> None:
    assert PageRequest().model_dump() == {"limit": 50, "offset": 0, "sort": "STABLE_ASC"}
    assert PageRequest(limit=100, offset=10).limit == 100
    with pytest.raises(ValidationError):
        PageRequest(limit=101)
    with pytest.raises(ValidationError):
        PageRequest(limit=0)
    with pytest.raises(ValidationError):
        PageRequest(sort="created_at desc; drop table provider_definitions")


def test_query_service_exposes_all_approved_reads_with_bounded_repository_calls() -> None:
    repository = _QueryRepository()
    service = ProviderQueryService(repository)
    page = PageRequest(limit=25, offset=5)

    pages = (
        service.list_providers(page),
        service.list_capabilities("SEC_EDGAR_PUBLIC_V1", page),
        service.list_attempts(RUN_ID, page),
        service.list_artifacts(RUN_ID, page),
        service.list_checkpoints("SEC_EDGAR_PUBLIC_V1", page),
        service.list_quality_issues(RUN_ID, page),
        service.list_dead_letters(RUN_ID, page),
    )
    singles = (
        service.get_provider("SEC_EDGAR_PUBLIC_V1"),
        service.get_policy("SEC_EDGAR_PUBLIC_V1"),
        service.get_license("SEC_EDGAR_PUBLIC_V1"),
        service.get_health("SEC_EDGAR_PUBLIC_V1"),
        service.get_circuit("SEC_EDGAR_PUBLIC_V1"),
        service.get_sync_run(RUN_ID),
        service.get_readiness(SECURITY_ID),
    )

    assert all(isinstance(result, ProviderQueryPage) for result in pages)
    assert all(result.returned == 1 for result in pages)
    assert all(isinstance(result, SafeProviderProjection) for result in singles)
    paged_calls = [call for call in repository.calls if "limit" in call[2]]
    assert len(paged_calls) == 7
    assert all(call[2] == {"limit": 25, "offset": 5} for call in paged_calls)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("blob_key", "provider/raw/a.json"),
        ("storage_uri", "blob://local/private"),
        ("raw_payload", "full response"),
        ("headers", {"Authorization": "secret"}),
        ("credential_value", "secret"),
        ("database_url", "postgresql://user:secret@localhost/db"),
        ("sql", "select * from provider_definitions"),
        ("safe_detail", "C:\\private\\provider.json"),
    ),
)
def test_safe_projection_rejects_sensitive_keys_and_local_paths(key: str, value: object) -> None:
    with pytest.raises(ValidationError):
        SafeProviderProjection(
            resource_type=ProviderQueryResource.ARTIFACT,
            values={key: value},
        )


def test_query_service_revalidates_repository_output_and_stops_leakage() -> None:
    repository = _QueryRepository()
    repository.override = {
        "resource_type": "ARTIFACT",
        "values": {"blob_key": "private/provider/raw.json"},
    }

    with pytest.raises(ValueError, match="PROVIDER_QUERY_UNSAFE_PROJECTION"):
        ProviderQueryService(repository).list_artifacts(RUN_ID, PageRequest())


def test_query_service_has_no_write_probe_sync_or_network_surface() -> None:
    forbidden = {
        "add",
        "create",
        "delete",
        "download",
        "execute",
        "fetch",
        "probe",
        "refresh",
        "repair",
        "sync",
        "update",
    }
    public = {
        name
        for name, value in ProviderQueryService.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert not any(name.split("_", 1)[0] in forbidden for name in public)


class _MappingResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> _MappingResult:
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self) -> None:
        self.statements: list[object] = []

    def execute(self, statement: object) -> _MappingResult:
        self.statements.append(statement)
        return _MappingResult([])


def test_sqlalchemy_query_repository_uses_bound_limits_and_explicit_safe_artifact_columns() -> None:
    session = _Session()
    repository = SqlAlchemyProviderQueryRepository(session)  # type: ignore[arg-type]

    assert repository.list_artifact_views(RUN_ID, limit=20, offset=5) == ()

    statement = session.statements[0]
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[union-attr]
    sql = str(compiled).lower()
    assert compiled.params["param_1"] == 20
    assert compiled.params["param_2"] == 5
    assert "provider_raw_artifacts.blob_key" not in sql
    assert "authorization" not in sql
    assert "cookie" not in sql


def test_repository_query_class_has_no_commit_rollback_or_mutation_methods() -> None:
    public = {
        name
        for name, value in SqlAlchemyProviderQueryRepository.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert "commit" not in public
    assert "rollback" not in public
    assert not any(name.startswith(("add_", "create_", "update_", "delete_")) for name in public)
