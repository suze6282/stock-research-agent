"""Bounded response streaming and deterministic content validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from time import monotonic
from typing import Protocol

from pydantic import Field

from stock_research_agent.domain.providers.schemas import (
    Checksum,
    FrozenProviderContract,
)


class ProviderResponseLimits(FrozenProviderContract):
    max_bytes: int = Field(ge=1, le=52_428_800)
    max_chunks: int = Field(ge=1, le=100_000)
    max_decompression_ratio: Decimal = Field(gt=0, le=1000)
    max_duration_seconds: Decimal = Field(gt=0, le=86_400)


class BoundedProviderPayload(FrozenProviderContract):
    body: bytes
    byte_count: int = Field(ge=0)
    checksum: Checksum


class ValidatedProviderPayload(BoundedProviderPayload):
    content_type: str
    charset: str
    parsed_json: object | None


class ProviderByteStream(Protocol):
    declared_length: int | None
    compressed_length: int | None

    def iter_chunks(self) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class BoundedResponseReader:
    """Read a finite fake or HTTP stream and always close it."""

    def __init__(self, clock: Callable[[], Decimal | float] = monotonic) -> None:
        self._clock = clock

    def read(
        self,
        stream: ProviderByteStream,
        limits: ProviderResponseLimits,
    ) -> BoundedProviderPayload:
        started = Decimal(str(self._clock()))
        chunks: list[bytes] = []
        total = 0
        try:
            if stream.declared_length is not None and stream.declared_length > limits.max_bytes:
                raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
            for count, chunk in enumerate(stream.iter_chunks(), start=1):
                if count > limits.max_chunks:
                    raise ValueError("PROVIDER_RESPONSE_CHUNK_LIMIT")
                if not isinstance(chunk, bytes):
                    raise TypeError("PROVIDER_RESPONSE_CHUNK_INVALID")
                total += len(chunk)
                if total > limits.max_bytes:
                    raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
                chunks.append(chunk)

            if stream.declared_length is not None and stream.declared_length != total:
                raise ValueError("PROVIDER_RESPONSE_LENGTH_MISMATCH")
            if stream.compressed_length is not None:
                if stream.compressed_length <= 0:
                    raise ValueError("PROVIDER_RESPONSE_COMPRESSION_RATIO")
                ratio = Decimal(total) / Decimal(stream.compressed_length)
                if ratio > limits.max_decompression_ratio:
                    raise ValueError("PROVIDER_RESPONSE_COMPRESSION_RATIO")
            elapsed = Decimal(str(self._clock())) - started
            if elapsed > limits.max_duration_seconds:
                raise ValueError("PROVIDER_RESPONSE_DURATION")

            body = b"".join(chunks)
            return BoundedProviderPayload(
                body=body,
                byte_count=total,
                checksum=hashlib.sha256(body).hexdigest(),
            )
        finally:
            stream.close()


class ProviderContentValidator:
    """Validate MIME, decoding and bounded structure without executing content."""

    @staticmethod
    def validate(
        headers: dict[str, str],
        payload: BoundedProviderPayload,
        accepted_types: tuple[str, ...],
    ) -> ValidatedProviderPayload:
        content_type_value = _single_header(headers, "content-type")
        media_type, charset = _parse_content_type(content_type_value)
        if media_type not in accepted_types:
            raise ValueError("PROVIDER_CONTENT_TYPE_NOT_ALLOWED")
        if media_type == "application/pdf":
            if not payload.body.startswith(b"%PDF-"):
                raise ValueError("PROVIDER_CONTENT_SNIFF_MISMATCH")
            return ValidatedProviderPayload(
                body=payload.body,
                byte_count=payload.byte_count,
                checksum=payload.checksum,
                content_type=media_type,
                charset="binary",
                parsed_json=None,
            )
        if charset not in {"utf-8", "us-ascii"}:
            raise ValueError("PROVIDER_CHARSET_NOT_ALLOWED")
        try:
            text = payload.body.decode(charset)
        except UnicodeDecodeError as exc:
            raise ValueError("PROVIDER_CHARSET_DECODE_FAILED") from exc
        if "\x00" in text:
            raise ValueError("PROVIDER_CONTENT_CONTROL_CHARACTER")

        parsed_json: object | None = None
        stripped = text.lstrip()
        if media_type == "application/json":
            if not stripped.startswith(("{", "[")):
                raise ValueError("PROVIDER_CONTENT_SNIFF_MISMATCH")
            try:
                parsed_json = json.loads(
                    text,
                    object_pairs_hook=_reject_duplicate_keys,
                )
            except _DuplicateJsonKey as exc:
                raise ValueError("PROVIDER_JSON_DUPLICATE_KEY") from exc
            except json.JSONDecodeError as exc:
                raise ValueError("PROVIDER_JSON_INVALID") from exc
            if _contains_control_character(parsed_json):
                raise ValueError("PROVIDER_CONTENT_CONTROL_CHARACTER")
            if not _json_within_bounds(parsed_json):
                raise ValueError("PROVIDER_JSON_STRUCTURE_BOUNDS")
        elif media_type == "text/html":
            lowered = stripped.casefold()
            if not lowered.startswith(("<!doctype html", "<html", "<body", "<div", "<p", "<")):
                raise ValueError("PROVIDER_CONTENT_SNIFF_MISMATCH")
            if any(
                marker in lowered
                for marker in (
                    "<script",
                    "<iframe",
                    "<object",
                    "<embed",
                    "javascript:",
                )
            ):
                raise ValueError("PROVIDER_ACTIVE_CONTENT_FORBIDDEN")
        return ValidatedProviderPayload(
            body=payload.body,
            byte_count=payload.byte_count,
            checksum=payload.checksum,
            content_type=media_type,
            charset=charset,
            parsed_json=parsed_json,
        )


class _DuplicateJsonKey(ValueError):
    pass


def _single_header(headers: dict[str, str], name: str) -> str:
    values = [value for key, value in headers.items() if key.casefold() == name]
    if len(values) != 1:
        raise ValueError("PROVIDER_CONTENT_TYPE_AMBIGUOUS")
    return values[0]


def _parse_content_type(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in value.split(";")]
    media_type = parts[0].casefold()
    charset = "utf-8"
    for parameter in parts[1:]:
        key, separator, item = parameter.partition("=")
        if separator and key.strip().casefold() == "charset":
            charset = item.strip().strip('"').casefold()
    return media_type, charset


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _contains_control_character(value: object) -> bool:
    if isinstance(value, str):
        return any(ord(character) < 32 or ord(character) == 127 for character in value)
    if isinstance(value, list):
        return any(_contains_control_character(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_control_character(key) or _contains_control_character(item)
            for key, item in value.items()
        )
    return False


def _json_within_bounds(value: object) -> bool:
    stack: list[tuple[object, int]] = [(value, 1)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > 32 or count > 100_000:
            return False
        if isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
    return True
