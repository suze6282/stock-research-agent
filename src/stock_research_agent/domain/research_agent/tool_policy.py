"""Deny-by-default authorization for Research Tool execution."""

from typing import NoReturn

from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.schemas import (
    AuthorizedToolCall,
    ControlledRunContext,
    ResearchPolicyRecord,
    ResearchStepRecord,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot


class ResearchToolAuthorizationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ResearchToolPolicy:
    def authorize(
        self,
        context: ControlledRunContext,
        step: ResearchStepRecord,
        catalog: ToolCatalogSnapshot,
        policy: ResearchPolicyRecord,
    ) -> AuthorizedToolCall:
        if context.tool_catalog_version != catalog.catalog_version:
            self._reject("TOOL_CATALOG_VERSION_MISMATCH")
        if context.policy_version != policy.version:
            self._reject("POLICY_VERSION_MISMATCH")
        if step.run_id != context.research_agent_run_id:
            self._reject("STEP_RUN_MISMATCH")

        name = step.definition.tool_name
        version = step.definition.tool_version
        if name is None or version is None:
            self._reject("STEP_HAS_NO_TOOL")

        same_name = tuple(entry for entry in catalog.entries if entry.tool_name == name)
        if not same_name:
            self._reject("TOOL_NOT_IN_CATALOG")
        entry = next(
            (item for item in same_name if item.tool_version == version),
            None,
        )
        if entry is None:
            self._reject("TOOL_VERSION_NOT_IN_CATALOG")
        if (
            entry.permission != "READ_ONLY"
            or entry.read_only is not True
            or entry.writes is not False
            or entry.requires_network is not False
        ):
            self._reject("TOOL_PERMISSION_DENIED")

        key = (name, version)
        denied = {(item.tool_name, item.tool_version) for item in policy.denied_tools}
        if key in denied:
            self._reject("TOOL_DENIED_BY_POLICY")
        allowed = {(item.tool_name, item.tool_version) for item in policy.allowed_tools}
        if key not in allowed:
            self._reject("TOOL_NOT_ALLOWED_BY_POLICY")

        payload = step.definition.input_binding
        return AuthorizedToolCall(
            tool_name=name,
            tool_version=version,
            payload=payload,
            input_checksum=stable_checksum(payload),
        )

    @staticmethod
    def _reject(code: str) -> NoReturn:
        raise ResearchToolAuthorizationError(code)
