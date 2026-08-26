from __future__ import annotations

import pytest

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.file_security import validate_filename


def test_filename_nfkc_is_used_for_validation_without_overwriting_original() -> None:
    original = "Ｆｉｌｉｎｇ.pdf"

    result = validate_filename(original)

    assert result.original == original
    assert result.normalized == "Filing.pdf"
    assert result.extension == ".pdf"


@pytest.mark.parametrize(
    "value",
    ["CON.pdf", "prn.JSON", "AUX.html", "NUL.htm", "COM1.pdf", "LPT9.json"],
)
def test_windows_device_names_are_rejected(value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_filename(value)

    assert exc_info.value.code == "WINDOWS_DEVICE_NAME"


@pytest.mark.parametrize(
    "value",
    ["filing.pdf.exe", "filing.final.pdf", ".filing.pdf"],
)
def test_double_or_hidden_extensions_are_rejected(value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_filename(value)

    assert exc_info.value.code == "DOUBLE_EXTENSION"


@pytest.mark.parametrize(
    "value",
    ["filing．pdf", "filing.ｐｄｆ", "filing.ＰＤＦ"],
)
def test_unicode_extension_confusion_is_rejected(value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_filename(value)

    assert exc_info.value.code == "UNICODE_EXTENSION_CONFUSION"


@pytest.mark.parametrize(
    "value",
    [
        "filing.pdf:stream",
        "filing.pdf.",
        "filing.pdf ",
        "../filing.pdf",
        "folder/filing.pdf",
        "filing.exe",
        "x" * 157 + ".pdf",
    ],
)
def test_other_invalid_names_fail_closed(value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        validate_filename(value)

    assert exc_info.value.code == "FILENAME_INVALID"


@pytest.mark.parametrize("value", ["filing.pdf", "filing.HTML", "filing.htm", "filing.json"])
def test_initial_extension_allowlist_is_exact(value: str) -> None:
    assert validate_filename(value).extension in {".pdf", ".html", ".htm", ".json"}
