"""Deterministic semantic Plan primitives."""

from types import MappingProxyType

from pydantic import JsonValue

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    ResearchStepType,
    ResearchType,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchPlanDraft,
    ResearchPolicyRecord,
    ResearchRequestRecord,
    ResearchStepDefinition,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot

PLANNER_VERSION = "deterministic-template-v1"
PLAN_VERSION = "research-plan-v1"
_DOCUMENT_TOOLS = frozenset({"list_document_versions", "search_document_chunks"})
_TEMPLATES = MappingProxyType(
    {
        ResearchType.COMPANY_OVERVIEW: (
            "list_snapshot_items",
            "list_document_versions",
            "search_document_chunks",
        ),
        ResearchType.FINANCIAL_HEALTH: (
            "get_financial_periods",
            "get_normalized_financial_facts",
            "get_financial_metrics",
            "get_metric_lineage",
        ),
        ResearchType.VALUATION_SNAPSHOT: (
            "get_latest_close",
            "get_financial_metrics",
            "get_metric_detail",
            "get_metric_lineage",
        ),
        ResearchType.CATALYSTS_AND_RISKS: (
            "get_corporate_actions",
            "list_document_versions",
            "search_document_chunks",
        ),
        ResearchType.DATA_QUALITY_REVIEW: (
            "list_snapshot_items",
            "get_normalized_financial_facts",
            "list_document_versions",
        ),
        ResearchType.FULL_RESEARCH_PACKAGE: (
            "get_financial_periods",
            "get_normalized_financial_facts",
            "get_financial_metrics",
            "get_metric_lineage",
            "get_corporate_actions",
            "search_document_chunks",
        ),
    }
)


def plan_checksum(draft: ResearchPlanDraft) -> str:
    """Hash only versioned semantic Plan content."""

    return stable_checksum(draft.model_dump(mode="python"))


class DeterministicTemplatePlanner:
    """Compile one approved finite template without inspecting evidence content."""

    def create_plan(
        self,
        request: ResearchRequestRecord,
        policy: ResearchPolicyRecord,
        tool_catalog: ToolCatalogSnapshot,
    ) -> ResearchPlanDraft:
        if request.planner_version != PLANNER_VERSION:
            raise ValueError("PLANNER_VERSION_MISMATCH")
        if (
            request.tool_catalog_version != tool_catalog.catalog_version
            or request.tool_catalog_checksum != tool_catalog.catalog_checksum
        ):
            raise ValueError("TOOL_CATALOG_VERSION_MISMATCH")
        if request.policy_version != policy.version:
            raise ValueError("POLICY_VERSION_MISMATCH")
        if request.research_type not in policy.allowed_research_types:
            raise ValueError("RESEARCH_TYPE_NOT_ALLOWED")

        steps: list[ResearchStepDefinition] = [
            self._component_step(
                0,
                "resolve_security",
                ResearchStepType.RESOLVE_SECURITY,
                (),
                "security-resolution-v1",
            ),
            self._tool_step(
                1,
                "get_data_snapshot",
                ResearchStepType.LOAD_SNAPSHOT,
                ("resolve_security",),
            ),
        ]
        data_keys: list[str] = []
        for tool_name in _TEMPLATES[request.research_type]:
            dependency = (
                ("get_financial_metrics",)
                if tool_name == "get_metric_lineage"
                else ("list_document_versions",)
                if tool_name == "search_document_chunks" and "list_document_versions" in data_keys
                else ("get_data_snapshot",)
            )
            steps.append(
                self._tool_step(
                    len(steps),
                    tool_name,
                    (
                        ResearchStepType.QUERY_DOCUMENT_EVIDENCE
                        if tool_name in _DOCUMENT_TOOLS
                        else ResearchStepType.QUERY_STRUCTURED_DATA
                    ),
                    dependency,
                )
            )
            data_keys.append(tool_name)

        steps.extend(
            (
                self._component_step(
                    len(steps),
                    "validate_evidence",
                    ResearchStepType.VALIDATE_EVIDENCE,
                    tuple(sorted(data_keys)),
                    "evidence-ledger-v1",
                ),
                self._component_step(
                    len(steps) + 1,
                    "build_claims",
                    ResearchStepType.BUILD_CLAIMS,
                    ("validate_evidence",),
                    "deterministic-claim-builder-v1",
                ),
                self._component_step(
                    len(steps) + 2,
                    "validate_claims",
                    ResearchStepType.VALIDATE_CLAIMS,
                    ("build_claims",),
                    "claim-support-v1",
                ),
                self._component_step(
                    len(steps) + 3,
                    "assemble_package",
                    ResearchStepType.ASSEMBLE_PACKAGE,
                    ("validate_claims",),
                    "research-package-v1",
                ),
            )
        )
        return ResearchPlanDraft(
            planner_version=PLANNER_VERSION,
            plan_version=PLAN_VERSION,
            tool_catalog_version=tool_catalog.catalog_version,
            steps=tuple(steps),
        )

    @staticmethod
    def _tool_step(
        index: int,
        tool_name: str,
        step_type: ResearchStepType,
        dependencies: tuple[str, ...],
    ) -> ResearchStepDefinition:
        binding: dict[str, JsonValue] = (
            {"query_template": "company_disclosures_bilingual-v1"}
            if tool_name == "search_document_chunks"
            else {}
        )
        return ResearchStepDefinition(
            step_index=index,
            step_key=tool_name,
            step_type=step_type,
            title=tool_name.replace("_", " ").title(),
            required=True,
            dependency_keys=dependencies,
            tool_name=tool_name,
            tool_version="1.0.0",
            input_binding=binding,
            fanout_limit=5 if tool_name == "get_metric_lineage" else 1,
        )

    @staticmethod
    def _component_step(
        index: int,
        key: str,
        step_type: ResearchStepType,
        dependencies: tuple[str, ...],
        component_name: str,
    ) -> ResearchStepDefinition:
        return ResearchStepDefinition(
            step_index=index,
            step_key=key,
            step_type=step_type,
            title=key.replace("_", " ").title(),
            required=True,
            dependency_keys=dependencies,
            component_name=component_name,
            input_binding={},
            fanout_limit=1,
        )
