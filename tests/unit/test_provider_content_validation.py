import hashlib

import pytest

from stock_research_agent.providers.http_response import (
    BoundedProviderPayload,
    ProviderContentValidator,
)


def _payload(body: bytes) -> BoundedProviderPayload:
    return BoundedProviderPayload(
        body=body,
        byte_count=len(body),
        checksum=hashlib.sha256(body).hexdigest(),
    )


def test_content_validator_accepts_bounded_utf8_json() -> None:
    result = ProviderContentValidator.validate(
        {"Content-Type": "application/json; charset=utf-8"},
        _payload(b'{"status":"OFFLINE"}'),
        ("application/json",),
    )
    assert result.content_type == "application/json"
    assert result.charset == "utf-8"
    assert result.parsed_json == {"status": "OFFLINE"}


@pytest.mark.parametrize(
    ("headers", "body", "reason"),
    [
        (
            {"Content-Type": "application/xml"},
            b"<root></root>",
            "PROVIDER_CONTENT_TYPE_NOT_ALLOWED",
        ),
        (
            {"Content-Type": "application/json"},
            b"<html>blocked</html>",
            "PROVIDER_CONTENT_SNIFF_MISMATCH",
        ),
        (
            {"Content-Type": "application/json; charset=utf-16"},
            b"{}",
            "PROVIDER_CHARSET_NOT_ALLOWED",
        ),
        (
            {"Content-Type": "application/json"},
            b'{"a":1,"a":2}',
            "PROVIDER_JSON_DUPLICATE_KEY",
        ),
        (
            {"Content-Type": "application/json"},
            b'{"a":"\\u0000"}',
            "PROVIDER_CONTENT_CONTROL_CHARACTER",
        ),
        (
            {"Content-Type": "text/html"},
            b"<script>alert(1)</script>",
            "PROVIDER_ACTIVE_CONTENT_FORBIDDEN",
        ),
    ],
)
def test_content_validator_rejects_mime_charset_duplicate_json_and_active_content(
    headers: dict[str, str],
    body: bytes,
    reason: str,
) -> None:
    accepted = ("application/json", "text/html")
    with pytest.raises(ValueError, match=reason):
        ProviderContentValidator.validate(headers, _payload(body), accepted)


def test_content_validator_rejects_deep_or_oversized_json_structure() -> None:
    deep = ("[" * 40 + "0" + "]" * 40).encode()
    with pytest.raises(ValueError, match="PROVIDER_JSON_STRUCTURE_BOUNDS"):
        ProviderContentValidator.validate(
            {"Content-Type": "application/json"},
            _payload(deep),
            ("application/json",),
        )
