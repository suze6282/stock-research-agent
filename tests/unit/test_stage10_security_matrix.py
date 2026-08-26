from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.file_security import (
    detect_content_type,
    resolve_inbox_file,
    validate_file_size,
)
from stock_research_agent.domain.live_evidence.html_security import inspect_html
from stock_research_agent.domain.live_evidence.json_security import (
    JsonSafetyPolicy,
    load_bounded_json,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live_evidence"


@pytest.mark.parametrize(
    ("operation", "code"),
    (
        (lambda: resolve_inbox_file(FIXTURES, "../secret.pdf"), "PATH_TRAVERSAL"),
        (lambda: validate_file_size(26_214_401), "FILE_TOO_LARGE"),
        (lambda: detect_content_type(b"MZsynthetic"), "EXECUTABLE_MAGIC_FORBIDDEN"),
        (
            lambda: inspect_html((FIXTURES / "active-resource.html").read_bytes()),
            "HTML_SCRIPT",
        ),
        (
            lambda: load_bounded_json(
                (FIXTURES / "bounded-attack.json").read_bytes(), JsonSafetyPolicy()
            ),
            "JSON_DUPLICATE_KEY",
        ),
    ),
)
def test_manual_evidence_security_failures_are_exact_and_safe(
    operation: Callable[[], object],
    code: str,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as error:
        operation()
    assert error.value.code == code
    assert str(error.value) == code


def test_stage10_sources_do_not_contain_force_bypass_or_secret_logging() -> None:
    sources = [
        path.read_text(encoding="utf-8")
        for path in (
            Path(__file__).resolve().parents[2]
            / "src"
            / "stock_research_agent"
            / "domain"
            / "live_evidence"
        ).glob("*.py")
    ]
    joined = "\n".join(sources).casefold()
    assert "force_publish" not in joined
    assert "credential_value" not in joined
    assert "database_url" not in joined
