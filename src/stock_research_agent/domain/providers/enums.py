from enum import StrEnum


class ProviderDefinitionStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"
    BLOCKED = "BLOCKED"


class ProviderCapabilityStatus(StrEnum):
    IMPLEMENTED_OFFLINE = "IMPLEMENTED_OFFLINE"
    ENABLED = "ENABLED"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


class ProviderLicenseStatus(StrEnum):
    APPROVED = "APPROVED"
    RESTRICTED_REVIEW_REQUIRED = "RESTRICTED_REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"


class ProviderCredentialStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_READ = "NOT_READ"
    CONFIGURED_METADATA_ONLY = "CONFIGURED_METADATA_ONLY"
    MISSING = "MISSING"
    BLOCKED = "BLOCKED"


class ProviderConfigurationStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"


class ProviderLiveAuthorizationStatus(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    AUTHORIZED = "AUTHORIZED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"
    BLOCKED = "BLOCKED"


class ProviderProductionStatus(StrEnum):
    ENABLED = "ENABLED"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"
    TEST_ONLY = "TEST_ONLY"


class ProviderRunStatus(StrEnum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProviderSyncSliceStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProviderCircuitStatus(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ProviderDataQualityStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ProviderSyntheticStatus(StrEnum):
    REAL_VERIFIED = "REAL_VERIFIED"
    FIXTURE_REAL_EXCERPT = "FIXTURE_REAL_EXCERPT"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"
    UNKNOWN = "UNKNOWN"


class ProviderLiveValidationStatus(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
