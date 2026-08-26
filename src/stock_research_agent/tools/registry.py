"""Deterministic internal registry for approved read-only tools."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from stock_research_agent.domain.data_access.enums import DataCategory, QualityStatus
from stock_research_agent.domain.data_access.provenance import classify_provider_evidence
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import (
    DataQueryResult,
    ProviderProvenanceRecord,
)
from stock_research_agent.domain.retrieval.schemas import EvidenceBundle
from stock_research_agent.tools.permissions import SnapshotBehavior, ToolPermission
from stock_research_agent.tools.schemas import (
    CalculationRunEnvelope,
    CorporateActionsEnvelope,
    DailyPriceHistoryEnvelope,
    DataSnapshotEnvelope,
    FinancialMetricsEnvelope,
    FinancialPeriodsEnvelope,
    GetCalculationRunInput,
    GetCorporateActionsInput,
    GetDailyPriceHistoryInput,
    GetDataSnapshotInput,
    GetFinancialMetricsInput,
    GetFinancialPeriodsInput,
    GetLatestCloseInput,
    GetMetricDetailInput,
    GetMetricLineageInput,
    GetNormalizedFinancialFactsInput,
    GetReportedFinancialFactsInput,
    GetSourceDocumentMetadataInput,
    LatestCloseEnvelope,
    ListSnapshotItemsInput,
    ListSourceDocumentsInput,
    MetricDetailEnvelope,
    MetricLineageEnvelope,
    NormalizedFinancialFactsEnvelope,
    ReportedFinancialFactsEnvelope,
    SnapshotItemsEnvelope,
    SnapshotOrAsOfInput,
    SourceDocumentMetadataEnvelope,
    SourceDocumentsEnvelope,
    ToolEnvelope,
    ToolProvenance,
    ToolQuality,
)
from stock_research_agent.tools.schemas_live_evidence import (
    LiveEvidenceReadOutput,
    LiveEvidenceResourceInput,
)
from stock_research_agent.tools.schemas_providers import (
    ProviderCodeInput,
    ProviderCodePageInput,
    ProviderReadOutput,
    ProviderRunInput,
    ProviderRunPageInput,
    ProviderSecurityInput,
)
from stock_research_agent.tools.schemas_rag import (
    GetCitationInput,
    GetDocumentChunkInput,
    GetDocumentMetadataInput,
    GetEvidenceBundleInput,
    GetRetrievalRunInput,
    ListDocumentVersionsInput,
    RagReadEnvelope,
    SearchDocumentChunksInput,
    VerifyCitationInput,
)
from stock_research_agent.tools.schemas_reports import (
    ReportIdInput,
    ReportPageInput,
    ReportReadOutput,
)
from stock_research_agent.tools.schemas_research_agent import (
    GetResearchAgentRunOutput,
    GetResearchClaimsOutput,
    GetResearchEvidenceOutput,
    GetResearchPackageOutput,
    GetResearchPlanOutput,
    GetResearchRunEventsOutput,
    GetResearchStepsOutput,
    GetResearchToolInvocationsOutput,
    ResearchRunIdInput,
    ResearchRunPageInput,
)

_SEMANTIC_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
RecordT = TypeVar("RecordT")
EnvelopeT = TypeVar("EnvelopeT", bound=ToolEnvelope[Any])
_STAGE7_QUERY_TOOL_NAMES = (
    "get_research_agent_run",
    "get_research_claims",
    "get_research_evidence",
    "get_research_package",
    "get_research_plan",
    "get_research_run_events",
    "get_research_steps",
    "get_research_tool_invocations",
)
_STAGE8_REPORT_QUERY_TOOL_NAMES = (
    "get_research_report",
    "get_report_sections",
    "get_report_blocks",
    "get_report_claim_bindings",
    "get_report_evidence_bindings",
    "get_report_citations",
    "get_report_reflection_runs",
    "get_report_reflection_findings",
    "get_report_revision_runs",
    "get_report_release_gate",
)
_STAGE9_PROVIDER_QUERY_TOOL_NAMES = (
    "get_provider",
    "list_provider_capabilities",
    "get_provider_health",
    "get_provider_license_status",
    "get_provider_sync_run",
    "get_provider_sync_checkpoint",
    "list_provider_raw_artifacts",
    "list_provider_quality_issues",
    "list_provider_dead_letters",
    "get_provider_readiness",
)
_STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES = (
    "get_live_authorization",
    "list_live_authorization_events",
    "list_live_authorization_consumptions",
    "get_live_execution_approval",
    "get_manual_evidence_import",
    "get_evidence_ingestion_manifest",
    "get_real_company_validation_run",
    "list_end_to_end_validations",
    "get_live_incident",
    "list_live_incident_events",
)


class ToolErrorCode(StrEnum):
    DUPLICATE_TOOL = "DUPLICATE_TOOL"
    INVALID_REGISTRATION = "INVALID_REGISTRATION"
    FORBIDDEN_REGISTRATION = "FORBIDDEN_REGISTRATION"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"


_ERROR_MESSAGES = {
    ToolErrorCode.DUPLICATE_TOOL: "Tool registration was rejected",
    ToolErrorCode.INVALID_REGISTRATION: "Tool registration was rejected",
    ToolErrorCode.FORBIDDEN_REGISTRATION: "Tool registration was rejected",
    ToolErrorCode.TOOL_NOT_FOUND: "Tool was not found",
    ToolErrorCode.INVALID_INPUT: "Tool input was invalid",
    ToolErrorCode.INVALID_OUTPUT: "Tool output was invalid",
    ToolErrorCode.EXECUTION_FAILED: "Tool execution failed safely",
}


class ToolRegistryError(RuntimeError):
    """Fixed, typed registry error that never includes caller or repository values."""

    def __init__(self, code: ToolErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])

    def __repr__(self) -> str:
        return f"ToolRegistryError(code={self.code.value!r})"


class ToolMetadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=5, max_length=64)
    domain: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=512)
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    permission: ToolPermission
    read_only: bool
    requires_network: bool
    writes: bool
    snapshot_behavior: SnapshotBehavior


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    metadata: ToolMetadata
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]


@dataclass(frozen=True, slots=True)
class CanonicalToolDefinition:
    version: str
    domain: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    snapshot_behavior: SnapshotBehavior


_CANONICAL_TOOL_DEFINITIONS = MappingProxyType(
    {
        "get_latest_close": CanonicalToolDefinition(
            version="1.0.0",
            domain="market_data",
            description="Read one latest persisted daily close.",
            input_model=GetLatestCloseInput,
            output_model=LatestCloseEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_daily_price_history": CanonicalToolDefinition(
            version="1.0.0",
            domain="market_data",
            description="Read bounded persisted daily price history.",
            input_model=GetDailyPriceHistoryInput,
            output_model=DailyPriceHistoryEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_corporate_actions": CanonicalToolDefinition(
            version="1.0.0",
            domain="market_data",
            description="Read bounded persisted corporate actions.",
            input_model=GetCorporateActionsInput,
            output_model=CorporateActionsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_reported_financial_facts": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_data",
            description="Read bounded raw reported financial facts.",
            input_model=GetReportedFinancialFactsInput,
            output_model=ReportedFinancialFactsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "list_source_documents": CanonicalToolDefinition(
            version="1.0.0",
            domain="documents",
            description="List bounded persisted source-document metadata.",
            input_model=ListSourceDocumentsInput,
            output_model=SourceDocumentsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_source_document_metadata": CanonicalToolDefinition(
            version="1.0.0",
            domain="documents",
            description="Read one persisted source-document metadata record.",
            input_model=GetSourceDocumentMetadataInput,
            output_model=SourceDocumentMetadataEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_data_snapshot": CanonicalToolDefinition(
            version="1.0.0",
            domain="snapshots",
            description="Read one exact persisted data snapshot.",
            input_model=GetDataSnapshotInput,
            output_model=DataSnapshotEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_REQUIRED,
        ),
        "list_snapshot_items": CanonicalToolDefinition(
            version="1.0.0",
            domain="snapshots",
            description="List exact bounded public snapshot items.",
            input_model=ListSnapshotItemsInput,
            output_model=SnapshotItemsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_REQUIRED,
        ),
        "get_normalized_financial_facts": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_normalization",
            description="Read bounded persisted normalized financial facts.",
            input_model=GetNormalizedFinancialFactsInput,
            output_model=NormalizedFinancialFactsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_REQUIRED,
        ),
        "get_financial_periods": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_normalization",
            description="Read bounded persisted fiscal periods.",
            input_model=GetFinancialPeriodsInput,
            output_model=FinancialPeriodsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_REQUIRED,
        ),
        "get_financial_metrics": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_metrics",
            description="Read bounded persisted deterministic financial metrics.",
            input_model=GetFinancialMetricsInput,
            output_model=FinancialMetricsEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_REQUIRED,
        ),
        "get_metric_detail": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_metrics",
            description="Read one persisted deterministic metric detail.",
            input_model=GetMetricDetailInput,
            output_model=MetricDetailEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_REQUIRED,
        ),
        "get_metric_lineage": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_metrics",
            description="Read persisted calculation input lineage.",
            input_model=GetMetricLineageInput,
            output_model=MetricLineageEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_calculation_run": CanonicalToolDefinition(
            version="1.0.0",
            domain="financial_metrics",
            description="Read one persisted calculation run.",
            input_model=GetCalculationRunInput,
            output_model=CalculationRunEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "list_document_versions": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="List persisted immutable document versions.",
            input_model=ListDocumentVersionsInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_document_metadata": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Read persisted document-version metadata.",
            input_model=GetDocumentMetadataInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "search_document_chunks": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Read one precomputed document retrieval result.",
            input_model=SearchDocumentChunksInput,
            output_model=EvidenceBundle,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_document_chunk": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Read one persisted bounded document chunk.",
            input_model=GetDocumentChunkInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_citation": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Read one immutable citation anchor.",
            input_model=GetCitationInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "verify_citation": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Verify one citation without modifying evidence.",
            input_model=VerifyCitationInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.SNAPSHOT_OR_AS_OF,
        ),
        "get_evidence_bundle": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Read one persisted verified evidence bundle.",
            input_model=GetEvidenceBundleInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_retrieval_run": CanonicalToolDefinition(
            version="1.0.0",
            domain="rag",
            description="Read one immutable retrieval run.",
            input_model=GetRetrievalRunInput,
            output_model=RagReadEnvelope,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_agent_run": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read one persisted controlled Research Agent run.",
            input_model=ResearchRunIdInput,
            output_model=GetResearchAgentRunOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_plan": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read one persisted immutable Research Agent plan.",
            input_model=ResearchRunIdInput,
            output_model=GetResearchPlanOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_steps": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read bounded persisted Research Agent steps.",
            input_model=ResearchRunPageInput,
            output_model=GetResearchStepsOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_tool_invocations": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read bounded persisted Research Agent Tool invocations.",
            input_model=ResearchRunPageInput,
            output_model=GetResearchToolInvocationsOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_evidence": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read bounded persisted validated Research Agent evidence.",
            input_model=ResearchRunPageInput,
            output_model=GetResearchEvidenceOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_claims": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read bounded persisted Research Agent claims.",
            input_model=ResearchRunPageInput,
            output_model=GetResearchClaimsOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_package": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read one persisted structured Research Package.",
            input_model=ResearchRunIdInput,
            output_model=GetResearchPackageOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_run_events": CanonicalToolDefinition(
            version="1.0.0",
            domain="research_agent",
            description="Read bounded append-only Research Agent run events.",
            input_model=ResearchRunPageInput,
            output_model=GetResearchRunEventsOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_provider": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="Read one persisted Provider definition summary.",
            input_model=ProviderCodeInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "list_provider_capabilities": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="List bounded persisted Provider capability summaries.",
            input_model=ProviderCodePageInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_provider_health": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="Read the latest persisted Provider health summary.",
            input_model=ProviderCodeInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_provider_license_status": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="Read one persisted safe Provider license summary.",
            input_model=ProviderCodeInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_provider_sync_run": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="Read one persisted Provider Sync Run summary.",
            input_model=ProviderRunInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_provider_sync_checkpoint": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="List bounded persisted Provider checkpoint summaries.",
            input_model=ProviderCodePageInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "list_provider_raw_artifacts": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="List bounded safe Provider raw-artifact metadata.",
            input_model=ProviderRunPageInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "list_provider_quality_issues": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="List bounded persisted Provider quality issue summaries.",
            input_model=ProviderRunPageInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "list_provider_dead_letters": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="List bounded persisted Provider dead-letter summaries.",
            input_model=ProviderRunPageInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_provider_readiness": CanonicalToolDefinition(
            version="1.0.0",
            domain="provider_governance",
            description="Read persisted Provider readiness for one Security.",
            input_model=ProviderSecurityInput,
            output_model=ProviderReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_research_report": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="Read one persisted immutable research report.",
            input_model=ReportIdInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_sections": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report sections.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_blocks": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report blocks.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_claim_bindings": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report Claim bindings.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_evidence_bindings": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report Evidence bindings.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_citations": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report Citation bindings.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_reflection_runs": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report Reflection runs.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_reflection_findings": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted report Reflection findings.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_revision_runs": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="List bounded persisted deterministic report revisions.",
            input_model=ReportPageInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        "get_report_release_gate": CanonicalToolDefinition(
            version="1.0.0",
            domain="reports",
            description="Read one persisted internal report Release Gate.",
            input_model=ReportIdInput,
            output_model=ReportReadOutput,
            snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
        ),
        **{
            name: CanonicalToolDefinition(
                version="1.0.0",
                domain="live_evidence_governance",
                description=f"Read bounded persisted {name} governance data.",
                input_model=LiveEvidenceResourceInput,
                output_model=LiveEvidenceReadOutput,
                snapshot_behavior=SnapshotBehavior.PERSISTED_METADATA,
            )
            for name in _STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES
        },
    }
)


class ToolRegistry:
    """Accept and execute only approved, non-resource-using read-only tools."""

    def __init__(self) -> None:
        self._registrations: dict[tuple[str, str], ToolRegistration] = {}

    def register(self, registration: ToolRegistration) -> None:
        metadata = self._validated_metadata(registration.metadata)
        key = (metadata.name, metadata.version)
        if key in self._registrations:
            raise ToolRegistryError(ToolErrorCode.DUPLICATE_TOOL)
        canonical = _CANONICAL_TOOL_DEFINITIONS.get(metadata.name)
        if canonical is None:
            raise ToolRegistryError(ToolErrorCode.FORBIDDEN_REGISTRATION)
        if (
            metadata.version != canonical.version
            or metadata.domain != canonical.domain
            or metadata.description != canonical.description
            or registration.input_model is not canonical.input_model
            or registration.output_model is not canonical.output_model
            or metadata.snapshot_behavior is not canonical.snapshot_behavior
        ):
            raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
        if (
            metadata.permission is not ToolPermission.READ_ONLY
            or not metadata.read_only
            or metadata.requires_network
            or metadata.writes
        ):
            raise ToolRegistryError(ToolErrorCode.FORBIDDEN_REGISTRATION)
        if (
            metadata.input_schema != registration.input_model.model_json_schema()
            or metadata.output_schema != registration.output_model.model_json_schema()
        ):
            raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
        self._registrations[key] = registration

    def list(self) -> tuple[ToolMetadata, ...]:
        return tuple(self._registrations[key].metadata for key in sorted(self._registrations))

    def describe(self, name: str, version: str = "1.0.0") -> ToolMetadata:
        return self._registration(name, version).metadata

    def execute(
        self,
        name: str,
        version: str,
        payload: Mapping[str, Any] | str | bytes,
    ) -> BaseModel:
        registration = self._registration(name, version)
        try:
            if isinstance(payload, (str, bytes)):
                validated = registration.input_model.model_validate_json(payload)
            else:
                validated = registration.input_model.model_validate(payload)
        except (ValidationError, ValueError, TypeError):
            raise ToolRegistryError(ToolErrorCode.INVALID_INPUT) from None
        try:
            result = registration.handler(validated)
        except ToolRegistryError:
            raise
        except Exception:
            raise ToolRegistryError(ToolErrorCode.EXECUTION_FAILED) from None
        try:
            return registration.output_model.model_validate(result)
        except (ValidationError, ValueError, TypeError):
            raise ToolRegistryError(ToolErrorCode.INVALID_OUTPUT) from None

    def _registration(self, name: str, version: str) -> ToolRegistration:
        try:
            return self._registrations[(name, version)]
        except KeyError:
            raise ToolRegistryError(ToolErrorCode.TOOL_NOT_FOUND) from None

    @staticmethod
    def _validated_metadata(metadata: ToolMetadata) -> ToolMetadata:
        try:
            validated = ToolMetadata.model_validate(metadata.model_dump())
        except ValidationError:
            raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION) from None
        if not _SEMANTIC_VERSION.fullmatch(validated.version):
            raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
        return validated


@dataclass(frozen=True, slots=True)
class EvidenceSelection[RecordT]:
    status: QualityStatus
    records: tuple[RecordT, ...]
    warnings: tuple[str, ...]
    snapshot_id: UUID | None
    research_as_of_time: Any


class ReadOnlyToolSupport:
    """Shared safe selection/envelope behavior used by the eight thin adapters."""

    def __init__(self, query_service: DataAccessQueryService) -> None:
        self._query_service = query_service

    def select_evidence(
        self,
        request: SnapshotOrAsOfInput,
        *,
        category: DataCategory,
        source_record_type: str,
        as_of_reader: Callable[[], DataQueryResult[RecordT]],
        snapshot_reader: Callable[[tuple[UUID, ...]], DataQueryResult[RecordT]],
    ) -> EvidenceSelection[RecordT]:
        if request.research_as_of_time is not None:
            try:
                result = as_of_reader()
            except Exception:
                return EvidenceSelection(
                    status=QualityStatus.FAIL,
                    records=(),
                    warnings=("DATA_ACCESS_QUERY_FAILED",),
                    snapshot_id=None,
                    research_as_of_time=request.research_as_of_time,
                )
            return EvidenceSelection(
                status=result.status,
                records=result.records,
                warnings=result.warnings,
                snapshot_id=None,
                research_as_of_time=request.research_as_of_time,
            )

        snapshot_id = request.snapshot_id
        if snapshot_id is None:
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("DATA_ACCESS_QUERY_FAILED",),
                snapshot_id=None,
                research_as_of_time=None,
            )
        try:
            snapshot_result = self._query_service.snapshot(snapshot_id)
        except Exception:
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("DATA_ACCESS_QUERY_FAILED",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        if not snapshot_result.records:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_NOT_FOUND",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        snapshot = snapshot_result.records[0]
        if snapshot.security_id != request.security_id:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_SECURITY_MISMATCH",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        if snapshot.status == "FAILED":
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("SNAPSHOT_FAILED",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        if snapshot.status not in {"COMPLETE", "PARTIAL"}:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_NOT_TERMINAL",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        try:
            item_result = self._query_service.snapshot_items_by_category(
                snapshot_id,
                category,
                100,
            )
        except Exception:
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("DATA_ACCESS_QUERY_FAILED",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        items = tuple(
            item for item in item_result.records if item.source_record_type == source_record_type
        )
        if not items:
            return EvidenceSelection(
                status=QualityStatus.PARTIAL,
                records=(),
                warnings=(f"SNAPSHOT_CATEGORY_ABSENT:{category.value}",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        source_ids = tuple(item.source_record_id for item in items)
        try:
            record_result = snapshot_reader(source_ids)
        except Exception:
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("DATA_ACCESS_QUERY_FAILED",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        captured = set(source_ids)
        records = tuple(
            record
            for record in record_result.records
            if getattr(record, "id", None) in captured
            and getattr(record, "security_id", None) == request.security_id
        )
        returned = {getattr(record, "id", None) for record in records}
        missing = tuple(value for value in source_ids if value not in returned)
        warnings = list(record_result.warnings)
        if snapshot.status == "PARTIAL":
            warnings.append("SNAPSHOT_PARTIAL")
        if missing:
            warnings.append("SNAPSHOT_RECORDS_UNAVAILABLE")
        status = record_result.status
        if warnings and status is QualityStatus.PASS:
            status = QualityStatus.PARTIAL
        return EvidenceSelection(
            status=status,
            records=records,
            warnings=self._stable_warnings(warnings),
            snapshot_id=snapshot_id,
            research_as_of_time=None,
        )

    def selection_provider_ids(
        self,
        selection: EvidenceSelection[Any],
        record_provider_ids: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        """Preserve snapshot provenance even when the selected category has no records."""

        provider_ids = tuple(dict.fromkeys(record_provider_ids))
        if provider_ids or selection.snapshot_id is None:
            return provider_ids
        try:
            items = self._query_service.snapshot_items(selection.snapshot_id, 100).records
        except Exception:
            return ()
        return tuple(dict.fromkeys(item.provider_id for item in items))

    def envelope(
        self,
        envelope_type: type[EnvelopeT],
        *,
        tool_name: str,
        status: QualityStatus,
        data: tuple[Any, ...],
        source_record_ids: tuple[UUID, ...],
        provider_ids: tuple[UUID, ...],
        snapshot_id: UUID | None,
        research_as_of_time: Any,
        retrieved_at: Any,
        warnings: tuple[str, ...],
    ) -> EnvelopeT:
        provenance, provenance_warnings, provenance_failed = self._provenance(provider_ids)
        if provenance_failed:
            status = QualityStatus.FAIL
            data = ()
            source_record_ids = ()
            provider_ids = ()
            retrieved_at = None
        combined = self._stable_warnings([*warnings, *provenance_warnings])
        return envelope_type(
            tool_name=tool_name,
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=source_record_ids,
            provider_ids=provider_ids,
            snapshot_id=snapshot_id,
            research_as_of_time=research_as_of_time,
            retrieved_at=retrieved_at,
            warnings=combined,
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=provenance,
        )

    def _provenance(
        self, provider_ids: tuple[UUID, ...]
    ) -> tuple[ToolProvenance, tuple[str, ...], bool]:
        if not provider_ids:
            return self._unknown_provenance(), ("PROVENANCE_UNKNOWN",), False
        unique_ids = tuple(dict.fromkeys(provider_ids))
        if len(unique_ids) > 396:
            return self._unknown_provenance(), ("PROVENANCE_PROVIDER_LIMIT_EXCEEDED",), True
        records: list[ProviderProvenanceRecord] = []
        try:
            for offset in range(0, len(unique_ids), 100):
                result = self._query_service.provider_provenance(unique_ids[offset : offset + 100])
                records.extend(result.records)
        except Exception:
            return self._unknown_provenance(), ("DATA_ACCESS_QUERY_FAILED",), True
        by_id = {record.id: record for record in records}
        if any(value not in by_id for value in unique_ids):
            return self._unknown_provenance(), ("PROVENANCE_PROVIDER_UNKNOWN",), True
        classified = tuple(
            classify_provider_evidence(
                provider_type=by_id[value].provider_type,
                status=by_id[value].status,
                terms_status=by_id[value].terms_status,
            )
            for value in unique_ids
        )
        marker_triples = {
            (item.data_origin, item.access_mode, item.live_status) for item in classified
        }
        warnings = self._stable_warnings(
            [warning for item in classified for warning in item.warnings]
        )
        if marker_triples == {("FIXTURE", "OFFLINE", "NOT_LIVE")}:
            return (
                ToolProvenance(
                    data_origin="FIXTURE",
                    access_mode="OFFLINE",
                    live_status="NOT_LIVE",
                ),
                (),
                False,
            )
        if marker_triples == {("LIVE", "ONLINE", "LIVE")}:
            return (
                ToolProvenance(
                    data_origin="LIVE",
                    access_mode="ONLINE",
                    live_status="LIVE",
                ),
                (),
                False,
            )
        if marker_triples == {("UNKNOWN", "UNKNOWN", "UNKNOWN")}:
            return self._unknown_provenance(), warnings, False
        return (
            ToolProvenance(
                data_origin="MIXED",
                access_mode="MIXED",
                live_status="MIXED",
            ),
            self._stable_warnings([*warnings, "PROVENANCE_MIXED"]),
            False,
        )

    @staticmethod
    def _unknown_provenance() -> ToolProvenance:
        return ToolProvenance(
            data_origin="UNKNOWN",
            access_mode="UNKNOWN",
            live_status="UNKNOWN",
        )

    @staticmethod
    def _stable_warnings(values: list[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))


def _metadata(
    *,
    name: str,
    domain: str,
    description: str,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
    snapshot_behavior: SnapshotBehavior,
) -> ToolMetadata:
    return ToolMetadata(
        name=name,
        version="1.0.0",
        domain=domain,
        description=description,
        input_schema=input_model.model_json_schema(),
        output_schema=output_model.model_json_schema(),
        permission=ToolPermission.READ_ONLY,
        read_only=True,
        requires_network=False,
        writes=False,
        snapshot_behavior=snapshot_behavior,
    )


def create_tool_registry(query_service: DataAccessQueryService) -> ToolRegistry:
    from stock_research_agent.tools.documents import (
        GetSourceDocumentMetadataTool,
        ListSourceDocumentsTool,
    )
    from stock_research_agent.tools.financial_data import GetReportedFinancialFactsTool
    from stock_research_agent.tools.market_data import (
        GetCorporateActionsTool,
        GetDailyPriceHistoryTool,
        GetLatestCloseTool,
    )
    from stock_research_agent.tools.snapshots import GetDataSnapshotTool, ListSnapshotItemsTool

    definitions: tuple[
        tuple[
            str,
            str,
            str,
            type[BaseModel],
            type[BaseModel],
            SnapshotBehavior,
            Callable[[BaseModel], BaseModel],
        ],
        ...,
    ] = (
        (
            "get_latest_close",
            "market_data",
            "Read one latest persisted daily close.",
            GetLatestCloseInput,
            LatestCloseEnvelope,
            SnapshotBehavior.SNAPSHOT_OR_AS_OF,
            cast(Callable[[BaseModel], BaseModel], GetLatestCloseTool(query_service)),
        ),
        (
            "get_daily_price_history",
            "market_data",
            "Read bounded persisted daily price history.",
            GetDailyPriceHistoryInput,
            DailyPriceHistoryEnvelope,
            SnapshotBehavior.SNAPSHOT_OR_AS_OF,
            cast(Callable[[BaseModel], BaseModel], GetDailyPriceHistoryTool(query_service)),
        ),
        (
            "get_corporate_actions",
            "market_data",
            "Read bounded persisted corporate actions.",
            GetCorporateActionsInput,
            CorporateActionsEnvelope,
            SnapshotBehavior.SNAPSHOT_OR_AS_OF,
            cast(Callable[[BaseModel], BaseModel], GetCorporateActionsTool(query_service)),
        ),
        (
            "get_reported_financial_facts",
            "financial_data",
            "Read bounded raw reported financial facts.",
            GetReportedFinancialFactsInput,
            ReportedFinancialFactsEnvelope,
            SnapshotBehavior.SNAPSHOT_OR_AS_OF,
            cast(
                Callable[[BaseModel], BaseModel],
                GetReportedFinancialFactsTool(query_service),
            ),
        ),
        (
            "list_source_documents",
            "documents",
            "List bounded persisted source-document metadata.",
            ListSourceDocumentsInput,
            SourceDocumentsEnvelope,
            SnapshotBehavior.SNAPSHOT_OR_AS_OF,
            cast(Callable[[BaseModel], BaseModel], ListSourceDocumentsTool(query_service)),
        ),
        (
            "get_source_document_metadata",
            "documents",
            "Read one persisted source-document metadata record.",
            GetSourceDocumentMetadataInput,
            SourceDocumentMetadataEnvelope,
            SnapshotBehavior.PERSISTED_METADATA,
            cast(
                Callable[[BaseModel], BaseModel],
                GetSourceDocumentMetadataTool(query_service),
            ),
        ),
        (
            "get_data_snapshot",
            "snapshots",
            "Read one exact persisted data snapshot.",
            GetDataSnapshotInput,
            DataSnapshotEnvelope,
            SnapshotBehavior.SNAPSHOT_REQUIRED,
            cast(Callable[[BaseModel], BaseModel], GetDataSnapshotTool(query_service)),
        ),
        (
            "list_snapshot_items",
            "snapshots",
            "List exact bounded public snapshot items.",
            ListSnapshotItemsInput,
            SnapshotItemsEnvelope,
            SnapshotBehavior.SNAPSHOT_REQUIRED,
            cast(Callable[[BaseModel], BaseModel], ListSnapshotItemsTool(query_service)),
        ),
    )
    registry = ToolRegistry()
    for (
        name,
        domain,
        description,
        input_model,
        output_model,
        snapshot_behavior,
        handler,
    ) in definitions:
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=domain,
                    description=description,
                    input_model=input_model,
                    output_model=output_model,
                    snapshot_behavior=snapshot_behavior,
                ),
                input_model=input_model,
                output_model=output_model,
                handler=handler,
            )
        )
    return registry


def create_tool_metadata_registry() -> ToolRegistry:
    """Build the canonical catalog without composing query services or executable tools."""

    def metadata_only_handler(_request: BaseModel) -> BaseModel:
        raise ToolRegistryError(ToolErrorCode.EXECUTION_FAILED)

    registry = ToolRegistry()
    for name, definition in _CANONICAL_TOOL_DEFINITIONS.items():
        if name in {
            *_STAGE7_QUERY_TOOL_NAMES,
            *_STAGE8_REPORT_QUERY_TOOL_NAMES,
            *_STAGE9_PROVIDER_QUERY_TOOL_NAMES,
            *_STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES,
        }:
            continue
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=metadata_only_handler,
            )
        )
    return registry


def create_final_tool_metadata_registry() -> ToolRegistry:
    """Build the 30-Tool post-Stage-7 catalog without executable handlers."""

    def metadata_only_handler(_request: BaseModel) -> BaseModel:
        raise ToolRegistryError(ToolErrorCode.EXECUTION_FAILED)

    registry = ToolRegistry()
    for name, definition in _CANONICAL_TOOL_DEFINITIONS.items():
        if name in {
            *_STAGE8_REPORT_QUERY_TOOL_NAMES,
            *_STAGE9_PROVIDER_QUERY_TOOL_NAMES,
            *_STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES,
        }:
            continue
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=metadata_only_handler,
            )
        )
    return registry


def create_stage8_final_tool_metadata_registry() -> ToolRegistry:
    """Build the additive 40-Tool Stage 8 metadata catalog."""

    def metadata_only_handler(_request: BaseModel) -> BaseModel:
        raise ToolRegistryError(ToolErrorCode.EXECUTION_FAILED)

    registry = ToolRegistry()
    for name, definition in _CANONICAL_TOOL_DEFINITIONS.items():
        if name in {
            *_STAGE9_PROVIDER_QUERY_TOOL_NAMES,
            *_STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES,
        }:
            continue
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=metadata_only_handler,
            )
        )
    return registry


def create_stage9_final_tool_metadata_registry() -> ToolRegistry:
    """Build the additive 50-Tool Stage 9 metadata catalog."""

    def metadata_only_handler(_request: BaseModel) -> BaseModel:
        raise ToolRegistryError(ToolErrorCode.EXECUTION_FAILED)

    registry = ToolRegistry()
    for name, definition in _CANONICAL_TOOL_DEFINITIONS.items():
        if name in _STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES:
            continue
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=metadata_only_handler,
            )
        )
    return registry


def create_research_agent_tool_registry(service: object) -> ToolRegistry:
    """Compose exactly the eight Stage 7 persisted-state query tools."""

    from stock_research_agent.domain.research_agent.queries import (
        ResearchAgentQueryService,
    )
    from stock_research_agent.tools.research_agent import ResearchAgentReadTool

    if not isinstance(service, ResearchAgentQueryService):
        raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
    registry = ToolRegistry()
    for name in _STAGE7_QUERY_TOOL_NAMES:
        definition = _CANONICAL_TOOL_DEFINITIONS[name]
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=cast(
                    Callable[[BaseModel], BaseModel],
                    ResearchAgentReadTool(service, name),
                ),
            )
        )
    return registry


def create_report_tool_registry(service: object) -> ToolRegistry:
    """Compose exactly the ten Stage 8 persisted report query tools."""

    from stock_research_agent.domain.reports.queries import ReportQueryService
    from stock_research_agent.tools.reports import ReportReadTool

    if not isinstance(service, ReportQueryService):
        raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
    registry = ToolRegistry()
    for name in _STAGE8_REPORT_QUERY_TOOL_NAMES:
        definition = _CANONICAL_TOOL_DEFINITIONS[name]
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=cast(
                    Callable[[BaseModel], BaseModel],
                    ReportReadTool(service, cast(Any, name)),
                ),
            )
        )
    return registry


def create_provider_tool_registry(service: object) -> ToolRegistry:
    """Compose exactly the ten Stage 9 persisted Provider query tools."""

    from stock_research_agent.domain.providers.queries import ProviderQueryService
    from stock_research_agent.tools.providers import ProviderReadTool

    if not isinstance(service, ProviderQueryService):
        raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
    registry = ToolRegistry()
    for name in _STAGE9_PROVIDER_QUERY_TOOL_NAMES:
        definition = _CANONICAL_TOOL_DEFINITIONS[name]
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=cast(
                    Callable[[BaseModel], BaseModel],
                    ProviderReadTool(service, cast(Any, name)),
                ),
            )
        )
    return registry


def create_live_evidence_tool_registry(service: object) -> ToolRegistry:
    """Compose exactly ten persisted, offline Stage 10 governance queries."""

    from stock_research_agent.domain.live_evidence.queries import LiveEvidenceQueryService
    from stock_research_agent.tools.live_evidence import LiveEvidenceReadTool

    if not isinstance(service, LiveEvidenceQueryService):
        raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
    registry = ToolRegistry()
    for name in _STAGE10_LIVE_EVIDENCE_QUERY_TOOL_NAMES:
        definition = _CANONICAL_TOOL_DEFINITIONS[name]
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=cast(
                    Callable[[BaseModel], BaseModel],
                    LiveEvidenceReadTool(service, cast(Any, name)),
                ),
            )
        )
    return registry


def create_financial_tool_registry(service: object) -> ToolRegistry:
    """Compose the six Stage 5 read-only financial tools."""

    from stock_research_agent.domain.financials.queries import FinancialQueryService
    from stock_research_agent.tools.financials import (
        GetCalculationRunTool,
        GetFinancialMetricsTool,
        GetFinancialPeriodsTool,
        GetMetricDetailTool,
        GetMetricLineageTool,
        GetNormalizedFinancialFactsTool,
    )

    if not isinstance(service, FinancialQueryService):
        raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
    handlers: dict[str, Callable[[BaseModel], BaseModel]] = {
        "get_normalized_financial_facts": cast(
            Callable[[BaseModel], BaseModel], GetNormalizedFinancialFactsTool(service)
        ),
        "get_financial_periods": cast(
            Callable[[BaseModel], BaseModel], GetFinancialPeriodsTool(service)
        ),
        "get_financial_metrics": cast(
            Callable[[BaseModel], BaseModel], GetFinancialMetricsTool(service)
        ),
        "get_metric_detail": cast(Callable[[BaseModel], BaseModel], GetMetricDetailTool(service)),
        "get_metric_lineage": cast(Callable[[BaseModel], BaseModel], GetMetricLineageTool(service)),
        "get_calculation_run": cast(
            Callable[[BaseModel], BaseModel], GetCalculationRunTool(service)
        ),
    }
    registry = ToolRegistry()
    for name, handler in handlers.items():
        definition = _CANONICAL_TOOL_DEFINITIONS[name]
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=handler,
            )
        )
    return registry


def create_rag_tool_registry(service: object) -> ToolRegistry:
    """Compose the eight Stage 6 cache-only/read-only RAG tools."""

    from stock_research_agent.domain.retrieval.service import PrecomputedRetrievalQueryService
    from stock_research_agent.tools.rag import RagReadTool, SearchDocumentChunksTool

    if not isinstance(service, PrecomputedRetrievalQueryService):
        raise ToolRegistryError(ToolErrorCode.INVALID_REGISTRATION)
    registry = ToolRegistry()
    for name in (
        "list_document_versions",
        "get_document_metadata",
        "search_document_chunks",
        "get_document_chunk",
        "get_citation",
        "verify_citation",
        "get_evidence_bundle",
        "get_retrieval_run",
    ):
        definition = _CANONICAL_TOOL_DEFINITIONS[name]
        handler = (
            SearchDocumentChunksTool(service)
            if name == "search_document_chunks"
            else RagReadTool(service, name)
        )
        registry.register(
            ToolRegistration(
                metadata=_metadata(
                    name=name,
                    domain=definition.domain,
                    description=definition.description,
                    input_model=definition.input_model,
                    output_model=definition.output_model,
                    snapshot_behavior=definition.snapshot_behavior,
                ),
                input_model=definition.input_model,
                output_model=definition.output_model,
                handler=cast(Callable[[BaseModel], BaseModel], handler),
            )
        )
    return registry


__all__ = [
    "ToolErrorCode",
    "ToolMetadata",
    "ToolRegistration",
    "ToolRegistry",
    "ToolRegistryError",
    "create_provider_tool_registry",
    "create_live_evidence_tool_registry",
    "create_financial_tool_registry",
    "create_final_tool_metadata_registry",
    "create_rag_tool_registry",
    "create_report_tool_registry",
    "create_research_agent_tool_registry",
    "create_stage8_final_tool_metadata_registry",
    "create_stage9_final_tool_metadata_registry",
    "create_tool_metadata_registry",
    "create_tool_registry",
]
