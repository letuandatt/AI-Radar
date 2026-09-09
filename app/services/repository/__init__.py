"""Repository management services package."""

from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.bootstrap import (
    create_application_services,
    initialize_knowledge_repository,
)
from app.services.repository.config import RepositoryConfig
from app.services.repository.health_monitor import (
    HealthCheckResult,
    HealthReport,
    RepositoryHealthMonitor,
)
from app.services.repository.initializer import (
    ComponentStatus,
    RepositoryInitializer,
    RepositoryState,
    ValidationError,
)
from app.services.repository.lifecycle_service import (
    BackupError,
    BackupResult,
    RepositoryLifecycleService,
    RestoreError,
    RestoreResult,
)
from app.services.repository.query_models import (
    InvalidQueryError,
    KnowledgeDetailResponse,
    KnowledgeItemSummary,
    KnowledgeListResponse,
    KnowledgeQuery,
    PageInfo,
    RepositoryNotFoundError,
    RepositoryStatistics,
    RepositoryUnavailableError,
    SourceHealth,
)

__all__ = [
    # Bootstrap
    "initialize_knowledge_repository",
    "create_application_services",
    # Config
    "RepositoryConfig",
    # Initializer
    "RepositoryInitializer",
    "RepositoryState",
    "ComponentStatus",
    "ValidationError",
    # Access Service
    "RepositoryAccessService",
    # Query Models
    "KnowledgeQuery",
    "KnowledgeListResponse",
    "KnowledgeDetailResponse",
    "KnowledgeItemSummary",
    "PageInfo",
    "RepositoryStatistics",
    "SourceHealth",
    # Error Contract
    "RepositoryNotFoundError",
    "RepositoryUnavailableError",
    "InvalidQueryError",
    # Lifecycle Service
    "RepositoryLifecycleService",
    "BackupResult",
    "RestoreResult",
    "BackupError",
    "RestoreError",
    # Health Monitor
    "RepositoryHealthMonitor",
    "HealthCheckResult",
    "HealthReport",
]
