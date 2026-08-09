"""Database repository implementations."""

from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderArtifactRepository,
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderQueryRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.db.repositories.reports import SqlAlchemyReportRepository
from stock_research_agent.db.repositories.research_agent import (
    SqlAlchemyResearchAgentRepository,
)
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)

__all__ = [
    "SqlAlchemyDataAccessRepository",
    "SqlAlchemyKnowledgeRepository",
    "SqlAlchemyProviderDefinitionRepository",
    "SqlAlchemyProviderArtifactRepository",
    "SqlAlchemyProviderGovernanceRepository",
    "SqlAlchemyProviderQueryRepository",
    "SqlAlchemyProviderSyncRepository",
    "SqlAlchemyResearchAgentRepository",
    "SqlAlchemyReportRepository",
    "SqlAlchemySecurityMasterRepository",
]
