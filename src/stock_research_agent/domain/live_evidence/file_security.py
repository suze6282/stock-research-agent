"""Local-inbox path resolution with no persisted absolute path."""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from types import MappingProxyType

from stock_research_agent.domain.live_evidence.enums import ManualContentType
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)

_ALLOWED_EXTENSIONS = frozenset({".pdf", ".html", ".htm", ".json"})
_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
}
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


@dataclass(frozen=True, slots=True)
class SafeFilename:
    original: str
    normalized: str
    extension: str


@dataclass(frozen=True, slots=True)
class FileContentIdentity:
    extension: str
    declared_mime: str
    detected_content_type: ManualContentType
    allowed: bool


class ResolvedInboxFile:
    __slots__ = ("_path", "relative_name", "safe_filename")

    def __init__(self, path: Path, relative_name: str, safe_filename: str) -> None:
        self._path = path
        self.relative_name = relative_name
        self.safe_filename = safe_filename

    def read_bytes(self) -> bytes:
        return self._path.read_bytes()

    def safe_summary(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "relative_name": self.relative_name,
                "safe_filename": self.safe_filename,
            }
        )


def validate_filename(original: str) -> SafeFilename:
    if not isinstance(original, str) or not original or len(original) > 255:
        raise LiveEvidenceValidationError("FILENAME_INVALID")
    if original != original.strip() or original.endswith((".", " ")):
        raise LiveEvidenceValidationError("FILENAME_INVALID")
    if any(unicodedata.category(character).startswith("C") for character in original):
        raise LiveEvidenceValidationError("FILENAME_INVALID")
    if any(character in original for character in ("/", "\\", ":")):
        raise LiveEvidenceValidationError("FILENAME_INVALID")

    normalized = unicodedata.normalize("NFKC", original)
    if len(normalized) > 160 or not normalized:
        raise LiveEvidenceValidationError("FILENAME_INVALID")
    extension = Path(normalized).suffix.lower()
    original_extension = Path(original).suffix
    if extension in _ALLOWED_EXTENSIONS and (
        not original_extension or any(ord(character) > 127 for character in original_extension)
    ):
        raise LiveEvidenceValidationError("UNICODE_EXTENSION_CONFUSION")
    if normalized.startswith(".") or normalized.count(".") != 1:
        raise LiveEvidenceValidationError("DOUBLE_EXTENSION")

    stem = normalized.rsplit(".", maxsplit=1)[0]
    if stem.upper() in _WINDOWS_DEVICE_NAMES:
        raise LiveEvidenceValidationError("WINDOWS_DEVICE_NAME")
    if extension not in _ALLOWED_EXTENSIONS:
        raise LiveEvidenceValidationError("FILENAME_INVALID")
    return SafeFilename(
        original=original,
        normalized=normalized,
        extension=extension,
    )


def validate_mime(
    content: bytes,
    extension: str,
    declared_mime: str,
) -> FileContentIdentity:
    normalized_extension = extension.lower()
    allowed_mimes = frozenset(_MIME_BY_EXTENSION.values())
    if normalized_extension not in _MIME_BY_EXTENSION or declared_mime not in allowed_mimes:
        raise LiveEvidenceValidationError("MIME_NOT_ALLOWED")
    if _MIME_BY_EXTENSION[normalized_extension] != declared_mime:
        raise LiveEvidenceValidationError("MIME_EXTENSION_MISMATCH")
    detected = detect_content_type(content)
    expected_type = {
        "application/pdf": ManualContentType.PDF,
        "text/html": ManualContentType.HTML,
        "application/json": ManualContentType.JSON,
    }[declared_mime]
    if detected is not expected_type:
        raise LiveEvidenceValidationError("MAGIC_BYTES_MISMATCH")
    return FileContentIdentity(
        extension=normalized_extension,
        declared_mime=declared_mime,
        detected_content_type=detected,
        allowed=True,
    )


def detect_content_type(content: bytes) -> ManualContentType:
    if not isinstance(content, bytes) or not content:
        raise LiveEvidenceValidationError("MAGIC_BYTES_MISMATCH")
    if content.startswith((b"MZ", b"\x7fELF")):
        raise LiveEvidenceValidationError("EXECUTABLE_MAGIC_FORBIDDEN")
    if content.startswith((b"PK\x03\x04", b"\x1f\x8b", b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c")):
        raise LiveEvidenceValidationError("ARCHIVE_FORBIDDEN")
    if content.startswith(b"%PDF-"):
        return ManualContentType.PDF

    prefix = content.removeprefix(b"\xef\xbb\xbf").lstrip()
    lower_prefix = prefix[:64].lower()
    if lower_prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return ManualContentType.HTML
    if prefix.startswith((b"{", b"[")):
        return ManualContentType.JSON
    raise LiveEvidenceValidationError("MAGIC_BYTES_MISMATCH")


def validate_file_size(size: int, limit: int = 26_214_400) -> None:
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise LiveEvidenceValidationError("FILE_EMPTY")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise LiveEvidenceValidationError("FILE_TOO_LARGE")
    if size > limit:
        raise LiveEvidenceValidationError("FILE_TOO_LARGE")


def resolve_inbox_file(root: Path, relative_name: str) -> ResolvedInboxFile:
    if not isinstance(relative_name, str) or not relative_name:
        raise LiveEvidenceValidationError("PATH_TRAVERSAL")
    if any(unicodedata.category(character).startswith("C") for character in relative_name):
        raise LiveEvidenceValidationError("PATH_TRAVERSAL")
    if relative_name.startswith(("\\\\", "//")):
        raise LiveEvidenceValidationError("UNC_PATH")
    if relative_name.startswith(("\\", "/")):
        raise LiveEvidenceValidationError("ABSOLUTE_PATH")

    windows_path = PureWindowsPath(relative_name)
    native_path = Path(relative_name)
    if windows_path.drive or windows_path.is_absolute() or native_path.is_absolute():
        raise LiveEvidenceValidationError("ABSOLUTE_PATH")

    normalized = relative_name.replace("\\", "/")
    parts = normalized.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise LiveEvidenceValidationError("PATH_TRAVERSAL")

    root_resolved = root.resolve(strict=True)
    candidate = root_resolved.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise LiveEvidenceValidationError("PATH_TRAVERSAL") from error
    try:
        under_root = os.path.commonpath((root_resolved, resolved)) == str(root_resolved)
    except ValueError as error:
        raise LiveEvidenceValidationError("SYMLINK_ESCAPE") from error
    if not under_root:
        raise LiveEvidenceValidationError("SYMLINK_ESCAPE")
    if not resolved.is_file():
        raise LiveEvidenceValidationError("PATH_TRAVERSAL")
    return ResolvedInboxFile(
        resolved,
        "/".join(parts),
        parts[-1],
    )
