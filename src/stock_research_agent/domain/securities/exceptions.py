"""Security master domain exceptions safe for translation at application boundaries."""


class SecurityMasterError(Exception):
    """Base class for expected security master failures."""


class InvalidSecurityQuery(SecurityMasterError, ValueError):
    """Raised when an identity query cannot be normalized safely."""


class SeedConflictError(SecurityMasterError):
    """Raised when versioned seed data conflicts with an existing record."""
