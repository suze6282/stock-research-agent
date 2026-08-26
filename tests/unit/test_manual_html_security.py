from __future__ import annotations

import inspect

import pytest

from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.html_security import inspect_html


def test_inert_html_without_active_content_passes() -> None:
    result = inspect_html(b"<!doctype html><html><body><p>SYNTHETIC_TEST_ONLY</p></body></html>")

    assert result.status is ManualValidationStatus.PASS
    assert result.finding_codes == ()


def test_html_script_element_is_blocked() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_html(b"<html><script>alert(1)</script></html>")

    assert exc_info.value.code == "HTML_SCRIPT"


@pytest.mark.parametrize("attribute", [b"onload", b"onclick", b"onerror"])
def test_html_event_handler_is_blocked(attribute: bytes) -> None:
    content = b"<html><body " + attribute + b'="synthetic()"></body></html>'

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_html(content)

    assert exc_info.value.code == "HTML_EVENT_HANDLER"


@pytest.mark.parametrize(
    "content",
    [
        b'<a href="javascript:synthetic()">x</a>',
        b'<form action="JaVaScRiPt:synthetic()"></form>',
    ],
)
def test_javascript_url_is_blocked(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_html(content)

    assert exc_info.value.code == "HTML_JAVASCRIPT_URL"


def test_visible_script_prose_is_not_executed_or_misclassified() -> None:
    result = inspect_html(b"<p>The filing discusses script controls.</p>")

    assert result.status is ManualValidationStatus.PASS
    source = inspect.getsource(inspect_html)
    assert "subprocess" not in source
    assert "requests" not in source


@pytest.mark.parametrize(
    "content",
    [
        b'<img src="https://example.invalid/x.png">',
        b'<link rel="stylesheet" href="/style.css">',
        b'<iframe src="frame.html"></iframe>',
        b'<object data="object.bin"></object>',
        b'<embed src="asset.bin">',
    ],
)
def test_external_or_loadable_html_resource_is_blocked(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_html(content)

    assert exc_info.value.code == "HTML_EXTERNAL_RESOURCE"


@pytest.mark.parametrize(
    "content",
    [
        b'<a href="file:///C:/secret.txt">x</a>',
        b'<img src="\\\\server\\share\\x.png">',
        b'<a href="C:\\secret.txt">x</a>',
    ],
)
def test_html_local_file_reference_is_blocked(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_html(content)

    assert exc_info.value.code == "HTML_LOCAL_FILE_REFERENCE"


def test_html_meta_refresh_is_blocked() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        inspect_html(b'<meta http-equiv="refresh" content="0;url=https://example.invalid">')

    assert exc_info.value.code == "HTML_META_REFRESH"
