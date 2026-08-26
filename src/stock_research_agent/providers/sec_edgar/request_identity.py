"""Execution-time SEC contact identity composition."""

from __future__ import annotations

from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
)
from stock_research_agent.domain.providers.credentials import (
    CredentialReferenceRecord,
    CredentialResolverKind,
)
from stock_research_agent.domain.providers.enums import ProviderCredentialStatus
from stock_research_agent.providers.credentials import (
    EnvironmentCredentialResolver,
    ProtectedRequestIdentity,
    ProviderRequestIdentityExecutionRequest,
)


def resolve_sec_request_identity(
    execution: AuthorizedGateBExecution,
    reference: CredentialReferenceRecord,
    resolver: EnvironmentCredentialResolver,
) -> ProtectedRequestIdentity:
    """Resolve the approved SEC contact value without returning printable material."""

    if (
        execution.provider != "SEC_EDGAR_PUBLIC_V1"
        or reference.id != execution.user_agent_reference_id
        or reference.resolver_kind is not CredentialResolverKind.ENVIRONMENT
        or reference.declared_name != "SEC_EDGAR_CONTACT_IDENTITY"
        or reference.status is not ProviderCredentialStatus.CONFIGURED_METADATA_ONLY
    ):
        raise ValueError("SEC_CONTACT_REFERENCE_INVALID")
    try:
        return resolver.resolve_request_identity(
            reference,
            ProviderRequestIdentityExecutionRequest(
                provider_definition_id=reference.provider_definition_id,
                credential_reference_id=reference.id,
                declared_name="SEC_EDGAR_CONTACT_IDENTITY",
                license_allowed=True,
                configuration_allowed=True,
                live_authorized=True,
            ),
        )
    except ValueError as error:
        if str(error) == "SEC_CONTACT_IDENTITY_INVALID":
            raise
        raise ValueError("SEC_CONTACT_REFERENCE_INVALID") from None
