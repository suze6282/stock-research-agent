class LiveEvidenceValidationError(ValueError):
    """A stable, safe domain validation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
