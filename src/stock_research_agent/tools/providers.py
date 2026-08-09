"""Thin read-only adapters for persisted Provider governance projections."""

from __future__ import annotations

from pydantic import BaseModel

from stock_research_agent.domain.providers.queries import PageRequest, ProviderQueryService
from stock_research_agent.tools.schemas_providers import (
    ProviderCodeInput,
    ProviderCodePageInput,
    ProviderReadOutput,
    ProviderRunInput,
    ProviderRunPageInput,
    ProviderSecurityInput,
    ProviderToolName,
)


class ProviderReadTool:
    """Dispatch exactly one approved metadata read without Provider execution."""

    def __init__(self, service: ProviderQueryService, name: ProviderToolName) -> None:
        self._service = service
        self._name = name

    def __call__(self, request: BaseModel) -> BaseModel:
        data = self._read(request)
        if data is None:
            return ProviderReadOutput(
                tool_name=self._name,
                status="BLOCKED",
                data=None,
                warnings=("PROVIDER_RESOURCE_NOT_FOUND",),
            )
        return ProviderReadOutput(
            tool_name=self._name,
            status="PASS",
            data=data.model_dump(mode="json"),
            warnings=(),
        )

    def _read(self, request: BaseModel) -> BaseModel | None:
        if isinstance(request, ProviderCodePageInput):
            page = PageRequest(limit=request.limit, offset=request.offset)
            if self._name == "list_provider_capabilities":
                return self._service.list_capabilities(request.provider_code, page)
            if self._name == "get_provider_sync_checkpoint":
                return self._service.list_checkpoints(request.provider_code, page)
            raise TypeError("invalid paged Provider query")
        if isinstance(request, ProviderRunPageInput):
            page = PageRequest(limit=request.limit, offset=request.offset)
            operations = {
                "list_provider_raw_artifacts": self._service.list_artifacts,
                "list_provider_quality_issues": self._service.list_quality_issues,
                "list_provider_dead_letters": self._service.list_dead_letters,
            }
            operation = operations.get(self._name)
            if operation is None:
                raise TypeError("invalid paged Provider Run query")
            return operation(request.run_id, page)
        if isinstance(request, ProviderCodeInput):
            if self._name == "get_provider":
                return self._service.get_provider(request.provider_code)
            if self._name == "get_provider_health":
                return self._service.get_health(request.provider_code)
            if self._name == "get_provider_license_status":
                return self._service.get_license(request.provider_code)
            raise TypeError("invalid Provider query")
        if isinstance(request, ProviderRunInput) and self._name == "get_provider_sync_run":
            return self._service.get_sync_run(request.run_id)
        if isinstance(request, ProviderSecurityInput) and self._name == "get_provider_readiness":
            return self._service.get_readiness(request.security_id)
        raise TypeError("invalid Provider query request")


__all__ = ["ProviderReadTool"]
