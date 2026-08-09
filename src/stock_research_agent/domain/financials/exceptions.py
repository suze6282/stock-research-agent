"""Safe domain exceptions for financial normalization operations."""


class FinancialSeedConflictError(RuntimeError):
    """Persisted reference data conflicts with the immutable seed manifest."""
