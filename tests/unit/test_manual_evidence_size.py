from __future__ import annotations

from typing import cast

import pytest

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.file_security import validate_file_size


@pytest.mark.parametrize("value", [1, 1024, 26_214_400])
def test_file_size_accepts_positive_values_up_to_25_mib(value: int) -> None:
    assert validate_file_size(value) is None


@pytest.mark.parametrize("value", [0, -1])
def test_empty_or_negative_file_is_rejected(value: int) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_file_size(value)

    assert exc_info.value.code == "FILE_EMPTY"


def test_oversized_file_is_rejected() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_file_size(26_214_401)

    assert exc_info.value.code == "FILE_TOO_LARGE"


@pytest.mark.parametrize("value", [True, False, 1.0, "1"])
def test_non_integer_size_is_rejected_without_coercion(value: object) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_file_size(cast(int, value))

    assert exc_info.value.code == "FILE_EMPTY"


def test_explicit_smaller_limit_is_enforced() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_file_size(11, limit=10)

    assert exc_info.value.code == "FILE_TOO_LARGE"
