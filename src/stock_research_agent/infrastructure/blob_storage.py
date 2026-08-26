"""Opaque, immutable byte storage for raw provider evidence."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
import weakref
from collections.abc import Callable, Mapping
from ctypes import Structure, byref, c_char, c_void_p, create_unicode_buffer, sizeof, wintypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import RLock
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

_KEY_PATTERN = re.compile(r"[0-9a-f]{32}")
_CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{64}")
_MAX_URI_LENGTH = 256
_MAX_CONTENT_TYPE_LENGTH = 255
_MAX_METADATA_ENTRIES = 32
_MAX_METADATA_KEY_LENGTH = 64
_MAX_METADATA_VALUE_LENGTH = 1024
_MAX_METADATA_TOTAL_LENGTH = 8192
_MAX_SIDECAR_BYTES = 128 * 1024
_SIDECAR_SUFFIX = ".metadata.json"


class BlobStorageError(Exception):
    """Base class for safe blob-storage failures."""


class InvalidBlobURIError(BlobStorageError):
    """Raised for an invalid blob URI or generated key."""


class BlobNotFoundError(BlobStorageError):
    """Raised when an opaque URI does not reference a stored blob."""


class BlobAlreadyExistsError(BlobStorageError):
    """Raised when an internally generated key collides with existing data."""


class BlobSizeLimitExceededError(BlobStorageError):
    """Raised when exact bytes exceed the configured storage limit."""


class BlobCleanupError(BlobStorageError):
    """Raised when an operation cannot safely finish precise cleanup."""


@dataclass(frozen=True, slots=True)
class BlobMetadata:
    """Immutable metadata describing exact stored bytes."""

    uri: str
    checksum_sha256: str
    size_bytes: int
    content_type: str
    metadata: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _validate_caller_metadata(self.metadata))


@runtime_checkable
class BlobStorage(Protocol):
    """Port for immutable opaque blob persistence."""

    def put(
        self,
        data: bytes,
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> BlobMetadata: ...

    def get(self, uri: str) -> bytes: ...

    def exists(self, uri: str) -> bool: ...

    def delete(self, uri: str) -> None: ...

    def checksum(self, uri: str) -> str: ...

    def metadata(self, uri: str) -> BlobMetadata: ...


@dataclass(frozen=True, slots=True)
class _MemoryEntry:
    data: bytes
    metadata: BlobMetadata


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def _validate_size_limit(max_blob_bytes: int) -> int:
    if isinstance(max_blob_bytes, bool) or not isinstance(max_blob_bytes, int):
        raise TypeError("max_blob_bytes must be an integer")
    if max_blob_bytes <= 0:
        raise ValueError("max_blob_bytes must be positive")
    return max_blob_bytes


def _validate_data(data: bytes, max_blob_bytes: int) -> bytes:
    if not isinstance(data, bytes):
        raise BlobStorageError("blob data must be bytes")
    if len(data) > max_blob_bytes:
        raise BlobSizeLimitExceededError("blob exceeds configured size limit")
    return data


def _validate_content_type(content_type: str) -> str:
    if not isinstance(content_type, str):
        raise BlobStorageError("content type must be a string")
    if not content_type.strip():
        raise BlobStorageError("content type must not be empty")
    if len(content_type) > _MAX_CONTENT_TYPE_LENGTH or _has_control(content_type):
        raise BlobStorageError("content type is invalid")
    return content_type


def _looks_like_absolute_path(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _validate_caller_metadata(
    metadata: Mapping[str, str] | None,
) -> Mapping[str, str]:
    if metadata is None:
        return MappingProxyType({})
    if not isinstance(metadata, Mapping):
        raise BlobStorageError("blob metadata must be a mapping")
    if len(metadata) > _MAX_METADATA_ENTRIES:
        raise BlobStorageError("blob metadata has too many entries")

    copied: dict[str, str] = {}
    total_length = 0
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise BlobStorageError("blob metadata keys and values must be strings")
        if not key.strip() or not value.strip():
            raise BlobStorageError("blob metadata keys and values must not be empty")
        if len(key) > _MAX_METADATA_KEY_LENGTH or len(value) > _MAX_METADATA_VALUE_LENGTH:
            raise BlobStorageError("blob metadata entry exceeds configured bounds")
        if _has_control(key) or _has_control(value):
            raise BlobStorageError("blob metadata contains invalid characters")
        if _looks_like_absolute_path(key) or _looks_like_absolute_path(value):
            raise BlobStorageError("blob metadata must not contain a local absolute path")
        total_length += len(key) + len(value)
        if total_length > _MAX_METADATA_TOTAL_LENGTH:
            raise BlobStorageError("blob metadata exceeds configured bounds")
        copied[key] = value
    return MappingProxyType(copied)


def _validate_key(key: object) -> str:
    if not isinstance(key, str) or _KEY_PATTERN.fullmatch(key) is None:
        raise InvalidBlobURIError("invalid blob key")
    return key


def _generate_key(key_factory: Callable[[], str]) -> str:
    try:
        key = key_factory()
    except Exception:
        raise InvalidBlobURIError("invalid blob key") from None
    return _validate_key(key)


def _parse_uri(uri: str, *, expected_backend: str) -> str:
    if (
        not isinstance(uri, str)
        or len(uri) > _MAX_URI_LENGTH
        or _has_control(uri)
        or "%" in uri
        or "\\" in uri
    ):
        raise InvalidBlobURIError("invalid blob URI")
    try:
        parsed = urlsplit(uri)
    except ValueError:
        raise InvalidBlobURIError("invalid blob URI") from None
    if (
        parsed.scheme != "blob"
        or parsed.netloc != expected_backend
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.count("/") != 1
    ):
        raise InvalidBlobURIError("invalid blob URI")
    return _validate_key(parsed.path[1:])


def _new_metadata(
    *,
    backend: str,
    key: str,
    data: bytes,
    content_type: str,
    metadata: Mapping[str, str],
) -> BlobMetadata:
    return BlobMetadata(
        uri=f"blob://{backend}/{key}",
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        content_type=content_type,
        metadata=metadata,
    )


class InMemoryBlobStorage:
    """Process-local immutable blob storage for tests and composition."""

    def __init__(
        self,
        *,
        max_blob_bytes: int,
        key_factory: Callable[[], str] | None = None,
    ) -> None:
        self._max_blob_bytes = _validate_size_limit(max_blob_bytes)
        self._key_factory = key_factory or (lambda: uuid.uuid4().hex)
        self._entries: dict[str, _MemoryEntry] = {}
        self._lock = RLock()

    def put(
        self,
        data: bytes,
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> BlobMetadata:
        validated_data = _validate_data(data, self._max_blob_bytes)
        validated_content_type = _validate_content_type(content_type)
        validated_metadata = _validate_caller_metadata(metadata)
        key = _generate_key(self._key_factory)
        result = _new_metadata(
            backend="memory",
            key=key,
            data=validated_data,
            content_type=validated_content_type,
            metadata=validated_metadata,
        )
        with self._lock:
            if key in self._entries:
                raise BlobAlreadyExistsError("blob key already exists")
            self._entries[key] = _MemoryEntry(data=validated_data, metadata=result)
        return result

    def get(self, uri: str) -> bytes:
        return self._entry(uri).data

    def exists(self, uri: str) -> bool:
        key = _parse_uri(uri, expected_backend="memory")
        with self._lock:
            return key in self._entries

    def delete(self, uri: str) -> None:
        key = _parse_uri(uri, expected_backend="memory")
        with self._lock:
            if key not in self._entries:
                raise BlobNotFoundError("blob not found")
            del self._entries[key]

    def checksum(self, uri: str) -> str:
        entry = self._entry(uri)
        checksum = hashlib.sha256(entry.data).hexdigest()
        if checksum != entry.metadata.checksum_sha256:
            raise BlobStorageError("blob integrity check failed")
        return checksum

    def metadata(self, uri: str) -> BlobMetadata:
        entry = self._entry(uri)
        if hashlib.sha256(entry.data).hexdigest() != entry.metadata.checksum_sha256:
            raise BlobStorageError("blob integrity check failed")
        return entry.metadata

    def _entry(self, uri: str) -> _MemoryEntry:
        key = _parse_uri(uri, expected_backend="memory")
        with self._lock:
            try:
                return self._entries[key]
            except KeyError:
                raise BlobNotFoundError("blob not found") from None


class _EntryMissing(Exception):
    pass


class _EntryCollision(Exception):
    pass


class _LocalAnchor(Protocol):
    def close(self) -> None: ...

    def pair_exists(self, content_name: str, sidecar_name: str) -> tuple[bool, bool]: ...

    def read_pair(
        self,
        content_name: str,
        sidecar_name: str,
        *,
        content_limit: int,
        sidecar_limit: int,
    ) -> tuple[bytes, bytes]: ...

    def write_pair(
        self,
        content_name: str,
        content: bytes,
        sidecar_name: str,
        sidecar: bytes,
    ) -> None: ...

    def delete_pair(self, content_name: str, sidecar_name: str) -> None: ...


_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_DELETE = 0x00010000
_FILE_LIST_DIRECTORY = 0x00000001
_FILE_READ_ATTRIBUTES = 0x00000080
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_CREATE_NEW = 1
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_FILE_ATTRIBUTE_TEMPORARY = 0x00000100
_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_FILE_DISPOSITION_INFO_CLASS = 4
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_ERROR_FILE_EXISTS = 80
_ERROR_ALREADY_EXISTS = 183
_INVALID_HANDLE_VALUE = c_void_p(-1).value
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_RENAME_NOREPLACE = 1
_POSIX_QUARANTINE_DIR_NAME = ".blob-quarantine"
_POSIX_LIBC: Any | None = None
_POSIX_RENAMEAT2: Any | None = None
if os.name == "posix":
    _POSIX_LIBC = ctypes.CDLL(None, use_errno=True)
    _POSIX_RENAMEAT2 = getattr(_POSIX_LIBC, "renameat2", None)
    if _POSIX_RENAMEAT2 is not None:
        _POSIX_RENAMEAT2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        _POSIX_RENAMEAT2.restype = ctypes.c_int


class _ByHandleFileInformation(Structure):
    _fields_ = [
        ("file_attributes", wintypes.DWORD),
        ("creation_time", wintypes.FILETIME),
        ("last_access_time", wintypes.FILETIME),
        ("last_write_time", wintypes.FILETIME),
        ("volume_serial_number", wintypes.DWORD),
        ("file_size_high", wintypes.DWORD),
        ("file_size_low", wintypes.DWORD),
        ("number_of_links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD),
        ("file_index_low", wintypes.DWORD),
    ]


class _FileDispositionInformation(Structure):
    _fields_ = [("delete_file", wintypes.BOOL)]


_CTYPES_WIN_DLL: Any | None = getattr(ctypes, "WinDLL", None)
_CTYPES_GET_LAST_ERROR: Callable[[], int] | None = getattr(ctypes, "get_last_error", None)
_KERNEL32: Any | None = None
if os.name == "nt":
    if _CTYPES_WIN_DLL is None or _CTYPES_GET_LAST_ERROR is None:
        raise BlobStorageError("required Windows filesystem capabilities are unavailable")
    _KERNEL32 = _CTYPES_WIN_DLL("kernel32", use_last_error=True)
    _KERNEL32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _KERNEL32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    ]
    _KERNEL32.GetFileInformationByHandle.restype = wintypes.BOOL
    _KERNEL32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _KERNEL32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _KERNEL32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _KERNEL32.ReadFile.restype = wintypes.BOOL
    _KERNEL32.WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _KERNEL32.WriteFile.restype = wintypes.BOOL
    _KERNEL32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    _KERNEL32.FlushFileBuffers.restype = wintypes.BOOL
    _KERNEL32.CreateHardLinkW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID]
    _KERNEL32.CreateHardLinkW.restype = wintypes.BOOL
    _KERNEL32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _KERNEL32.SetFileInformationByHandle.restype = wintypes.BOOL


def _win_handle(handle: int) -> wintypes.HANDLE:
    return wintypes.HANDLE(handle)


def _win_close(handle: int, cleanup: bool) -> bool:
    del cleanup
    return _KERNEL32 is not None and bool(_KERNEL32.CloseHandle(_win_handle(handle)))


def _win_close_best_effort(handle: int) -> None:
    if _KERNEL32 is not None:
        _KERNEL32.CloseHandle(_win_handle(handle))


def _win_last_error() -> int:
    if _CTYPES_GET_LAST_ERROR is None:
        raise BlobStorageError("blob storage operation failed")
    return int(_CTYPES_GET_LAST_ERROR())


def _win_open(
    path: str,
    *,
    access: int,
    creation: int,
    flags: int,
) -> int:
    if _KERNEL32 is None:
        raise BlobStorageError("blob storage operation failed")
    raw_handle = _KERNEL32.CreateFileW(
        path,
        access,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        creation,
        flags,
        None,
    )
    value = c_void_p(raw_handle).value
    if value == _INVALID_HANDLE_VALUE:
        error = _win_last_error()
        if error in {_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND}:
            raise _EntryMissing
        if error in {_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS}:
            raise _EntryCollision
        raise BlobStorageError("blob storage operation failed")
    if value is None:
        raise BlobStorageError("blob storage operation failed")
    return int(value)


def _win_information(handle: int) -> _ByHandleFileInformation:
    if _KERNEL32 is None:
        raise BlobStorageError("blob storage operation failed")
    information = _ByHandleFileInformation()
    if not _KERNEL32.GetFileInformationByHandle(_win_handle(handle), byref(information)):
        raise BlobStorageError("blob storage operation failed")
    return information


def _win_identity(information: _ByHandleFileInformation) -> tuple[int, int]:
    index = (int(information.file_index_high) << 32) | int(information.file_index_low)
    return int(information.volume_serial_number), index


def _normalize_windows_path(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return os.path.normcase(os.path.normpath(path))


def _win_final_path(handle: int) -> str:
    if _KERNEL32 is None:
        raise BlobStorageError("blob storage operation failed")
    required = _KERNEL32.GetFinalPathNameByHandleW(_win_handle(handle), None, 0, 0)
    if required == 0:
        raise BlobStorageError("blob storage operation failed")
    buffer = create_unicode_buffer(required + 1)
    written = _KERNEL32.GetFinalPathNameByHandleW(_win_handle(handle), buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        raise BlobStorageError("blob storage operation failed")
    return _normalize_windows_path(buffer.value)


def _win_read_bounded(handle: int, limit: int) -> bytes:
    if _KERNEL32 is None:
        raise BlobStorageError("blob storage operation failed")
    result = bytearray()
    maximum = limit + 1
    while len(result) < maximum:
        chunk_size = min(64 * 1024, maximum - len(result))
        buffer = (c_char * chunk_size)()
        read = wintypes.DWORD()
        if not _KERNEL32.ReadFile(_win_handle(handle), buffer, chunk_size, byref(read), None):
            raise BlobStorageError("blob storage operation failed")
        if read.value == 0:
            break
        result.extend(ctypes.string_at(buffer, read.value))
    if len(result) > limit:
        raise BlobSizeLimitExceededError("blob exceeds configured size limit")
    return bytes(result)


def _win_write_all(handle: int, data: bytes) -> None:
    if _KERNEL32 is None:
        raise BlobStorageError("blob storage operation failed")
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + 64 * 1024]
        written = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(chunk)
        if not _KERNEL32.WriteFile(_win_handle(handle), buffer, len(chunk), byref(written), None):
            raise BlobStorageError("blob storage operation failed")
        if written.value <= 0:
            raise BlobStorageError("blob storage operation failed")
        offset += int(written.value)
    if not _KERNEL32.FlushFileBuffers(_win_handle(handle)):
        raise BlobStorageError("blob storage operation failed")


def _create_hard_link(source: str, destination: str) -> None:
    if _KERNEL32 is None:
        try:
            os.link(source, destination, follow_symlinks=False)
            return
        except FileExistsError:
            raise _EntryCollision from None
        except OSError:
            raise BlobStorageError("blob storage operation failed") from None
    if not _KERNEL32.CreateHardLinkW(destination, source, None):
        error = _win_last_error()
        if error in {_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS}:
            raise _EntryCollision
        raise BlobStorageError("blob storage operation failed")


def _set_delete_disposition(handle: int) -> None:
    if _KERNEL32 is None:
        raise BlobCleanupError("blob cleanup failed")
    information = _FileDispositionInformation(delete_file=True)
    if not _KERNEL32.SetFileInformationByHandle(
        _win_handle(handle),
        _FILE_DISPOSITION_INFO_CLASS,
        byref(information),
        sizeof(information),
    ):
        raise BlobCleanupError("blob cleanup failed")


class _WindowsHeldFile:
    def __init__(self, handle: int, identity: tuple[int, int]) -> None:
        self.handle = handle
        self.identity = identity

    def close(self, *, cleanup: bool = False) -> None:
        if self.handle != 0:
            if not _win_close(self.handle, cleanup):
                error_type = BlobCleanupError if cleanup else BlobStorageError
                raise error_type(
                    "blob cleanup failed" if cleanup else "blob storage operation failed"
                )
            self.handle = 0


def _close_windows_files(entries: list[_WindowsHeldFile], *, cleanup: bool) -> None:
    close_failed = False
    for entry in entries:
        try:
            entry.close(cleanup=cleanup)
        except BlobStorageError:
            close_failed = True
    if close_failed:
        error_type = BlobCleanupError if cleanup else BlobStorageError
        raise error_type("blob cleanup failed" if cleanup else "blob storage operation failed")


class _WindowsRootAnchor:
    def __init__(self, root: Path) -> None:
        configured = root.absolute()
        try:
            configured.mkdir(parents=True, exist_ok=True)
            resolved = configured.resolve(strict=True)
        except OSError:
            raise BlobStorageError("blob storage operation failed") from None
        handle = _win_open(
            str(resolved),
            access=_FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES,
            creation=_OPEN_EXISTING,
            flags=_FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        )
        try:
            information = _win_information(handle)
            if not information.file_attributes & _FILE_ATTRIBUTE_DIRECTORY:
                raise BlobStorageError("blob storage root is invalid")
            if information.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise InvalidBlobURIError("invalid blob URI")
            final_path = _win_final_path(handle)
            if final_path != _normalize_windows_path(str(resolved)):
                raise BlobStorageError("blob storage root is invalid")
        except Exception:
            if not _win_close(handle, True):
                raise BlobCleanupError("blob cleanup failed") from None
            raise
        self._handle = handle
        self._identity = _win_identity(information)
        self._final_path = final_path
        self._finalizer = weakref.finalize(self, _win_close_best_effort, handle)

    def close(self) -> None:
        if self._handle == 0:
            return
        if not _win_close(self._handle, True):
            raise BlobCleanupError("blob cleanup failed")
        self._finalizer.detach()
        self._handle = 0

    def pair_exists(self, content_name: str, sidecar_name: str) -> tuple[bool, bool]:
        self._assert_root()
        return self._exists(content_name), self._exists(sidecar_name)

    def read_pair(
        self,
        content_name: str,
        sidecar_name: str,
        *,
        content_limit: int,
        sidecar_limit: int,
    ) -> tuple[bytes, bytes]:
        self._assert_root()
        content = self._open_entry(content_name, access=_GENERIC_READ | _FILE_READ_ATTRIBUTES)
        try:
            sidecar = self._open_entry(sidecar_name, access=_GENERIC_READ | _FILE_READ_ATTRIBUTES)
        except Exception:
            content.close(cleanup=True)
            raise
        try:
            return (
                _win_read_bounded(content.handle, content_limit),
                _win_read_bounded(sidecar.handle, sidecar_limit),
            )
        finally:
            _close_windows_files([sidecar, content], cleanup=True)

    def write_pair(
        self,
        content_name: str,
        content: bytes,
        sidecar_name: str,
        sidecar: bytes,
    ) -> None:
        self._assert_root()
        token = uuid.uuid4().hex
        temporary_content_name = f".{token}.blob.tmp"
        temporary_sidecar_name = f".{token}.metadata.tmp"
        temporary_files: list[tuple[str, _WindowsHeldFile]] = []
        published: list[tuple[str, tuple[int, int]]] = []
        primary_error: BlobStorageError | None = None
        cleanup_failed = False
        try:
            temporary_content = self._create_temporary(temporary_content_name, content)
            temporary_files.append((temporary_content_name, temporary_content))
            temporary_sidecar = self._create_temporary(temporary_sidecar_name, sidecar)
            temporary_files.append((temporary_sidecar_name, temporary_sidecar))
            self._publish_link(temporary_content_name, temporary_content, content_name)
            published.append((content_name, temporary_content.identity))
            self._publish_link(temporary_sidecar_name, temporary_sidecar, sidecar_name)
            published.append((sidecar_name, temporary_sidecar.identity))
        except _EntryCollision:
            primary_error = BlobAlreadyExistsError("blob key already exists")
        except BlobStorageError as error:
            primary_error = error
        except OSError:
            primary_error = BlobStorageError("blob storage operation failed")
        finally:
            for _, temporary in temporary_files:
                try:
                    _set_delete_disposition(temporary.handle)
                except BlobStorageError:
                    cleanup_failed = True
                finally:
                    try:
                        temporary.close(cleanup=True)
                    except BlobStorageError:
                        cleanup_failed = True
            if primary_error is not None or cleanup_failed:
                for name, identity in reversed(published):
                    try:
                        self._delete_expected(name, identity)
                    except BlobStorageError:
                        cleanup_failed = True
        if cleanup_failed:
            raise BlobCleanupError("blob cleanup failed")
        if primary_error is not None:
            raise primary_error

    def delete_pair(self, content_name: str, sidecar_name: str) -> None:
        self._assert_root()
        held: list[_WindowsHeldFile] = []
        try:
            for name in (content_name, sidecar_name):
                try:
                    held.append(self._open_entry(name, access=_DELETE | _FILE_READ_ATTRIBUTES))
                except _EntryMissing:
                    continue
        except Exception:
            _close_windows_files(held, cleanup=True)
            raise
        if not held:
            raise _EntryMissing
        cleanup_failed = False
        for entry in held:
            try:
                _set_delete_disposition(entry.handle)
            except BlobStorageError:
                cleanup_failed = True
            finally:
                try:
                    entry.close(cleanup=True)
                except BlobStorageError:
                    cleanup_failed = True
        if cleanup_failed:
            raise BlobCleanupError("blob cleanup failed")

    def _assert_root(self) -> None:
        if self._handle == 0:
            raise BlobStorageError("blob storage is closed")
        information = _win_information(self._handle)
        if _win_identity(information) != self._identity:
            raise BlobStorageError("blob storage root changed")
        if _win_final_path(self._handle) != self._final_path:
            raise BlobStorageError("blob storage root changed")

    def _path(self, name: str) -> str:
        _validate_local_name(name)
        return os.path.join(self._final_path, name)

    def _open_entry(self, name: str, *, access: int) -> _WindowsHeldFile:
        path = self._path(name)
        handle = _win_open(
            path,
            access=access,
            creation=_OPEN_EXISTING,
            flags=_FILE_FLAG_BACKUP_SEMANTICS
            | _FILE_FLAG_OPEN_REPARSE_POINT
            | _FILE_FLAG_SEQUENTIAL_SCAN,
        )
        try:
            information = _win_information(handle)
            if information.file_attributes & (
                _FILE_ATTRIBUTE_REPARSE_POINT | _FILE_ATTRIBUTE_DIRECTORY
            ):
                raise InvalidBlobURIError("invalid blob URI")
            if _win_final_path(handle) != _normalize_windows_path(path):
                raise InvalidBlobURIError("invalid blob URI")
            return _WindowsHeldFile(handle, _win_identity(information))
        except Exception:
            if not _win_close(handle, True):
                raise BlobCleanupError("blob cleanup failed") from None
            raise

    def _exists(self, name: str) -> bool:
        try:
            entry = self._open_entry(name, access=_FILE_READ_ATTRIBUTES)
        except _EntryMissing:
            return False
        entry.close(cleanup=True)
        return True

    def _create_temporary(self, name: str, data: bytes) -> _WindowsHeldFile:
        path = self._path(name)
        handle = _win_open(
            path,
            access=_GENERIC_READ | _GENERIC_WRITE | _DELETE | _FILE_READ_ATTRIBUTES,
            creation=_CREATE_NEW,
            flags=_FILE_ATTRIBUTE_NORMAL
            | _FILE_ATTRIBUTE_TEMPORARY
            | _FILE_FLAG_OPEN_REPARSE_POINT,
        )
        try:
            information = _win_information(handle)
            if information.file_attributes & (
                _FILE_ATTRIBUTE_REPARSE_POINT | _FILE_ATTRIBUTE_DIRECTORY
            ):
                raise InvalidBlobURIError("invalid blob URI")
            if _win_final_path(handle) != _normalize_windows_path(path):
                raise InvalidBlobURIError("invalid blob URI")
            _win_write_all(handle, data)
            return _WindowsHeldFile(handle, _win_identity(information))
        except Exception as error:
            cleanup_failed = False
            try:
                _set_delete_disposition(handle)
            except BlobStorageError:
                cleanup_failed = True
            finally:
                if not _win_close(handle, True):
                    cleanup_failed = True
            if cleanup_failed:
                raise BlobCleanupError("blob cleanup failed") from None
            raise error

    def _publish_link(
        self,
        source_name: str,
        source: _WindowsHeldFile,
        destination_name: str,
    ) -> None:
        _create_hard_link(self._path(source_name), self._path(destination_name))
        published: _WindowsHeldFile | None = None
        try:
            published = self._open_entry(destination_name, access=_FILE_READ_ATTRIBUTES)
            if published.identity != source.identity:
                raise BlobCleanupError("blob cleanup failed")
            published.close(cleanup=True)
            published = None
        except Exception as error:
            if published is not None:
                try:
                    published.close(cleanup=True)
                except BlobStorageError:
                    pass
            try:
                self._delete_expected(destination_name, source.identity)
            except BlobStorageError:
                raise BlobCleanupError("blob cleanup failed") from None
            if isinstance(error, BlobStorageError):
                raise error
            raise BlobStorageError("blob storage operation failed") from None

    def _delete_expected(self, name: str, expected_identity: tuple[int, int]) -> None:
        try:
            entry = self._open_entry(name, access=_DELETE | _FILE_READ_ATTRIBUTES)
        except _EntryMissing:
            return
        try:
            if entry.identity != expected_identity:
                raise BlobCleanupError("blob cleanup failed")
            _set_delete_disposition(entry.handle)
        finally:
            entry.close(cleanup=True)


class _PosixRootAnchor:
    def __init__(self, root: Path) -> None:
        _require_posix_capabilities()
        configured = root.absolute()
        try:
            configured.mkdir(parents=True, exist_ok=True)
            resolved = configured.resolve(strict=True)
        except OSError:
            raise BlobStorageError("blob storage operation failed") from None
        root_fd = _posix_open_root_fd(resolved)
        quarantine_fd: int | None = None
        try:
            information = _posix_fstat(root_fd)
            if not stat.S_ISDIR(information.st_mode):
                raise BlobStorageError("blob storage root is invalid")
            quarantine_fd, quarantine_identity = _posix_open_private_quarantine(root_fd)
            _probe_posix_rename_semantics(root_fd, quarantine_fd)
        except Exception:
            if quarantine_fd is not None:
                try:
                    _posix_close_fd(quarantine_fd, True)
                except BlobStorageError:
                    pass
            _posix_close_fd(root_fd, True)
            raise
        self._root_fd = root_fd
        self._identity = _posix_identity(information)
        self._quarantine_fd = quarantine_fd
        self._quarantine_identity = quarantine_identity
        self._finalizer = weakref.finalize(
            self,
            _posix_close_anchors_best_effort,
            quarantine_fd,
            root_fd,
        )

    def close(self) -> None:
        if self._root_fd < 0:
            return
        cleanup_failed = False
        for descriptor in (self._quarantine_fd, self._root_fd):
            try:
                _posix_close_fd(descriptor, True)
            except BlobStorageError:
                cleanup_failed = True
        self._finalizer.detach()
        self._quarantine_fd = -1
        self._root_fd = -1
        if cleanup_failed:
            raise BlobCleanupError("blob cleanup failed")

    def pair_exists(self, content_name: str, sidecar_name: str) -> tuple[bool, bool]:
        self._assert_root()
        return self._exists(content_name), self._exists(sidecar_name)

    def read_pair(
        self,
        content_name: str,
        sidecar_name: str,
        *,
        content_limit: int,
        sidecar_limit: int,
    ) -> tuple[bytes, bytes]:
        self._assert_root()
        content_fd = self._open_existing(content_name, os.O_RDONLY)
        try:
            sidecar_fd = self._open_existing(sidecar_name, os.O_RDONLY)
        except Exception:
            _posix_close_fd(content_fd, False)
            raise
        try:
            return (
                _posix_read_bounded(content_fd, content_limit),
                _posix_read_bounded(sidecar_fd, sidecar_limit),
            )
        finally:
            close_failed = False
            for descriptor in (sidecar_fd, content_fd):
                try:
                    _posix_close_fd(descriptor, False)
                except BlobStorageError:
                    close_failed = True
            if close_failed:
                raise BlobStorageError("blob storage operation failed")

    def write_pair(
        self,
        content_name: str,
        content: bytes,
        sidecar_name: str,
        sidecar: bytes,
    ) -> None:
        self._assert_root()
        token = uuid.uuid4().hex
        temporary_names = [f".{token}.blob.tmp", f".{token}.metadata.tmp"]
        temporary: list[tuple[str, int, tuple[int, int]]] = []
        published: list[tuple[str, tuple[int, int]]] = []
        primary_error: BlobStorageError | None = None
        cleanup_failed = False
        try:
            for name, data in zip(temporary_names, (content, sidecar), strict=True):
                descriptor, identity = self._create_temporary(name, data)
                temporary.append((name, descriptor, identity))
            for (source_name, _, identity), destination_name in zip(
                temporary, (content_name, sidecar_name), strict=True
            ):
                _posix_link_names(self._root_fd, source_name, destination_name)
                published.append((destination_name, identity))
                try:
                    published_descriptor = self._open_existing(destination_name, os.O_RDONLY)
                except Exception as error:
                    try:
                        self._unlink_expected(destination_name, identity)
                    except BlobStorageError:
                        raise BlobCleanupError("blob cleanup failed") from None
                    if isinstance(error, BlobStorageError):
                        raise error
                    raise BlobStorageError("blob storage operation failed") from None
                try:
                    if _posix_identity(_posix_fstat(published_descriptor)) != identity:
                        raise BlobCleanupError("blob cleanup failed")
                finally:
                    _posix_close_fd(published_descriptor, False)
        except _EntryCollision:
            primary_error = BlobAlreadyExistsError("blob key already exists")
        except BlobStorageError as error:
            primary_error = error
        except OSError:
            primary_error = BlobStorageError("blob storage operation failed")
        finally:
            for name, descriptor, identity in temporary:
                try:
                    self._unlink_expected(name, identity)
                except BlobStorageError:
                    cleanup_failed = True
                finally:
                    try:
                        _posix_close_fd(descriptor, True)
                    except BlobStorageError:
                        cleanup_failed = True
            if primary_error is not None or cleanup_failed:
                for name, identity in reversed(published):
                    try:
                        self._unlink_expected(name, identity)
                    except BlobStorageError:
                        cleanup_failed = True
        if cleanup_failed:
            raise BlobCleanupError("blob cleanup failed")
        if primary_error is not None:
            raise primary_error

    def delete_pair(self, content_name: str, sidecar_name: str) -> None:
        self._assert_root()
        entries: list[tuple[str, int, tuple[int, int]]] = []
        try:
            for name in (content_name, sidecar_name):
                try:
                    descriptor = self._open_existing(name, os.O_RDONLY)
                except _EntryMissing:
                    continue
                try:
                    identity = _posix_identity(_posix_fstat(descriptor))
                except Exception:
                    _posix_close_fd(descriptor, False)
                    raise
                entries.append((name, descriptor, identity))
        except Exception:
            for _, descriptor, _ in entries:
                _posix_close_fd(descriptor, False)
            raise
        if not entries:
            raise _EntryMissing
        quarantined: list[_PosixQuarantined] = []
        quarantine_failed = False
        try:
            for name, _, identity in entries:
                try:
                    quarantined.append(
                        _posix_quarantine_expected(
                            self._root_fd,
                            self._quarantine_fd,
                            name,
                            identity,
                        )
                    )
                except _EntryMissing:
                    continue
        except BlobStorageError:
            quarantine_failed = True
            for quarantined_entry in reversed(quarantined):
                try:
                    _posix_restore_quarantined(
                        self._root_fd,
                        self._quarantine_fd,
                        quarantined_entry,
                    )
                except BlobStorageError:
                    pass
        if quarantine_failed:
            for _, descriptor, _ in entries:
                try:
                    _posix_close_fd(descriptor, True)
                except BlobStorageError:
                    pass
            raise BlobCleanupError("blob cleanup failed")

        cleanup_failed = False
        for index, quarantined_entry in enumerate(quarantined):
            try:
                _posix_commit_quarantined(self._quarantine_fd, quarantined_entry)
            except BlobStorageError:
                cleanup_failed = True
                for remaining in reversed(quarantined[index + 1 :]):
                    try:
                        _posix_restore_quarantined(
                            self._root_fd,
                            self._quarantine_fd,
                            remaining,
                        )
                    except BlobStorageError:
                        pass
                break
        for _, descriptor, _ in entries:
            try:
                _posix_close_fd(descriptor, True)
            except BlobStorageError:
                cleanup_failed = True
        if cleanup_failed:
            raise BlobCleanupError("blob cleanup failed")

    def _assert_root(self) -> None:
        if self._root_fd < 0:
            raise BlobStorageError("blob storage is closed")
        if _posix_identity(_posix_fstat(self._root_fd)) != self._identity:
            raise BlobStorageError("blob storage root changed")
        quarantine_information = _posix_fstat(self._quarantine_fd)
        if _posix_identity(
            quarantine_information
        ) != self._quarantine_identity or not _is_safe_private_quarantine(quarantine_information):
            raise BlobStorageError("private blob quarantine is unsafe")

    def _open_existing(self, name: str, access: int) -> int:
        _validate_local_name(name)
        descriptor = _posix_open_existing_fd(self._root_fd, name, access)
        try:
            information = _posix_fstat(descriptor)
            if not stat.S_ISREG(information.st_mode):
                raise InvalidBlobURIError("invalid blob URI")
        except Exception:
            _posix_close_fd(descriptor, False)
            raise
        return descriptor

    def _exists(self, name: str) -> bool:
        try:
            descriptor = self._open_existing(name, os.O_RDONLY)
        except _EntryMissing:
            return False
        _posix_close_fd(descriptor, False)
        return True

    def _create_temporary(self, name: str, data: bytes) -> tuple[int, tuple[int, int]]:
        _validate_local_name(name)
        descriptor = _posix_open_new_fd(self._root_fd, name)
        identity: tuple[int, int] | None = None
        try:
            information = _posix_fstat(descriptor)
            if not stat.S_ISREG(information.st_mode):
                raise InvalidBlobURIError("invalid blob URI")
            identity = _posix_identity(information)
            _posix_write_all(descriptor, data)
            return descriptor, identity
        except Exception as error:
            cleanup_failed = False
            if identity is not None:
                try:
                    self._unlink_expected(name, identity)
                except BlobStorageError:
                    cleanup_failed = True
            else:
                cleanup_failed = True
            try:
                _posix_close_fd(descriptor, True)
            except BlobStorageError:
                cleanup_failed = True
            if cleanup_failed:
                raise BlobCleanupError("blob cleanup failed") from None
            raise error

    def _unlink_expected(self, name: str, expected_identity: tuple[int, int]) -> None:
        _posix_quarantine_unlink(
            self._root_fd,
            self._quarantine_fd,
            name,
            expected_identity,
        )


def _validate_local_name(name: str) -> None:
    if (
        re.fullmatch(
            r"(?:[0-9a-f]{32}(?:\.metadata\.json)?|\.[0-9a-f]{32}\.(?:blob|metadata)\.tmp|\.[0-9a-f]{32}\.quarantine)",
            name,
        )
        is None
    ):
        raise InvalidBlobURIError("invalid blob URI")


def _require_posix_capabilities() -> None:
    required_dir_fd = {os.open, os.link, os.mkdir, os.stat, os.unlink, os.rename}
    if (
        os.name != "posix"
        or _O_NOFOLLOW == 0
        or _O_DIRECTORY == 0
        or _POSIX_RENAMEAT2 is None
        or not required_dir_fd <= os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
        or os.link not in os.supports_follow_symlinks
    ):
        raise BlobStorageError("required POSIX filesystem capabilities are unavailable")


def _posix_open_root_fd(path: Path) -> int:
    try:
        return os.open(path, os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC | _O_NOFOLLOW)
    except OSError:
        raise BlobStorageError("blob storage operation failed") from None


def _posix_mkdir_private(root_fd: int, name: str, mode: int) -> None:
    try:
        os.mkdir(name, mode, dir_fd=root_fd)
    except FileExistsError:
        return
    except OSError:
        raise BlobStorageError("blob storage operation failed") from None


def _posix_open_directory_at(root_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC | _O_NOFOLLOW,
            dir_fd=root_fd,
        )
    except OSError:
        raise BlobStorageError("private blob quarantine is unsafe") from None


def _posix_effective_uid() -> int:
    get_effective_uid = getattr(os, "geteuid", None)
    if get_effective_uid is None:
        raise BlobStorageError("required POSIX filesystem capabilities are unavailable")
    return int(get_effective_uid())


def _is_safe_private_quarantine(information: Any) -> bool:
    return (
        stat.S_ISDIR(information.st_mode)
        and stat.S_IMODE(information.st_mode) == 0o700
        and int(information.st_uid) == _posix_effective_uid()
    )


def _posix_open_private_quarantine(root_fd: int) -> tuple[int, tuple[int, int]]:
    _posix_mkdir_private(root_fd, _POSIX_QUARANTINE_DIR_NAME, 0o700)
    descriptor = _posix_open_directory_at(root_fd, _POSIX_QUARANTINE_DIR_NAME)
    try:
        information = _posix_fstat(descriptor)
        if not _is_safe_private_quarantine(information):
            raise BlobStorageError("private blob quarantine is unsafe")
        return descriptor, _posix_identity(information)
    except Exception:
        _posix_close_fd(descriptor, True)
        raise


def _posix_open_existing_fd(root_fd: int, name: str, flags: int) -> int:
    try:
        return os.open(name, flags | _O_CLOEXEC | _O_NOFOLLOW, dir_fd=root_fd)
    except FileNotFoundError:
        raise _EntryMissing from None
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise InvalidBlobURIError("invalid blob URI") from None
        raise BlobStorageError("blob storage operation failed") from None


def _posix_open_new_fd(root_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | _O_CLOEXEC | _O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
    except FileExistsError:
        raise _EntryCollision from None
    except OSError:
        raise BlobStorageError("blob storage operation failed") from None


def _posix_fstat(descriptor: int) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except OSError:
        raise BlobStorageError("blob storage operation failed") from None


def _posix_identity(information: Any) -> tuple[int, int]:
    return int(information.st_dev), int(information.st_ino)


def _posix_close_fd(descriptor: int, cleanup: bool) -> None:
    try:
        os.close(descriptor)
    except OSError:
        error_type = BlobCleanupError if cleanup else BlobStorageError
        raise error_type(
            "blob cleanup failed" if cleanup else "blob storage operation failed"
        ) from None


def _posix_close_best_effort(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _posix_close_anchors_best_effort(quarantine_fd: int, root_fd: int) -> None:
    _posix_close_best_effort(quarantine_fd)
    _posix_close_best_effort(root_fd)


def _posix_link_names(root_fd: int, source_name: str, destination_name: str) -> None:
    try:
        os.link(
            source_name,
            destination_name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        raise _EntryCollision from None
    except OSError:
        raise BlobStorageError("blob storage operation failed") from None


def _posix_rename_noreplace(
    source_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
) -> None:
    if _POSIX_RENAMEAT2 is None:
        raise BlobStorageError("required POSIX rename capability is unavailable")
    result = _POSIX_RENAMEAT2(
        source_fd,
        os.fsencode(source_name),
        destination_fd,
        os.fsencode(destination_name),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.ENOENT:
        raise _EntryMissing
    if error == errno.EEXIST:
        raise _EntryCollision
    unsupported_errors = {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}
    if error in unsupported_errors:
        raise BlobStorageError("required POSIX rename capability is unavailable")
    raise BlobCleanupError("blob cleanup failed")


def _posix_unlink_name(root_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=root_fd)
    except FileNotFoundError:
        raise _EntryMissing from None
    except OSError:
        raise BlobCleanupError("blob cleanup failed") from None


def _probe_posix_rename_semantics(root_fd: int, quarantine_fd: int) -> None:
    token = uuid.uuid4().hex
    source_name = f".{token}.probe-source"
    root_name = f".{token}.probe-root"
    moved_name = f".{token}.probe-moved"
    collision_source = f".{token}.probe-collision-source"
    collision_target = f".{token}.probe-collision-target"
    active_entries: list[tuple[int, str]] = []
    descriptors: list[int] = []
    primary_error: BlobStorageError | None = None
    cleanup_failed = False

    try:
        descriptors.append(_posix_open_new_fd(quarantine_fd, source_name))
        active_entries.append((quarantine_fd, source_name))
        _posix_rename_noreplace(
            quarantine_fd,
            source_name,
            root_fd,
            root_name,
        )
        active_entries[-1] = (root_fd, root_name)
        _posix_rename_noreplace(
            root_fd,
            root_name,
            quarantine_fd,
            moved_name,
        )
        active_entries[-1] = (quarantine_fd, moved_name)

        descriptors.append(_posix_open_new_fd(quarantine_fd, collision_target))
        active_entries.append((quarantine_fd, collision_target))
        descriptors.append(_posix_open_new_fd(quarantine_fd, collision_source))
        active_entries.append((quarantine_fd, collision_source))
        try:
            _posix_rename_noreplace(
                quarantine_fd,
                collision_source,
                quarantine_fd,
                collision_target,
            )
        except _EntryCollision:
            pass
        else:
            active_entries.pop()
            raise BlobStorageError("required POSIX rename capability is unavailable")
    except (_EntryCollision, _EntryMissing):
        primary_error = BlobStorageError("required POSIX rename capability is unavailable")
    except BlobStorageError as error:
        primary_error = error
    finally:
        for descriptor in reversed(descriptors):
            try:
                _posix_close_fd(descriptor, True)
            except BlobStorageError:
                cleanup_failed = True
        for directory_fd, name in reversed(active_entries):
            try:
                _posix_unlink_name(directory_fd, name)
            except BlobStorageError:
                cleanup_failed = True

    if cleanup_failed:
        raise BlobCleanupError("blob cleanup failed")
    if primary_error is not None:
        raise primary_error


def _posix_restore_quarantine(
    root_fd: int,
    quarantine_fd: int,
    quarantine_name: str,
    original_name: str,
) -> None:
    try:
        _posix_rename_noreplace(
            quarantine_fd,
            quarantine_name,
            root_fd,
            original_name,
        )
    except (_EntryCollision, _EntryMissing, BlobStorageError):
        raise BlobCleanupError("blob cleanup failed") from None


@dataclass(frozen=True, slots=True)
class _PosixQuarantined:
    original_name: str
    quarantine_name: str
    descriptor: int
    identity: tuple[int, int]


def _posix_quarantine_expected(
    root_fd: int,
    quarantine_fd: int,
    name: str,
    expected_identity: tuple[int, int],
    *,
    token_factory: Callable[[], str] | None = None,
) -> _PosixQuarantined:
    make_token = token_factory or (lambda: uuid.uuid4().hex)
    quarantine_name: str | None = None
    for _ in range(8):
        token = _validate_key(make_token())
        candidate = f".{token}.quarantine"
        try:
            _posix_rename_noreplace(root_fd, name, quarantine_fd, candidate)
        except (_EntryCollision, FileExistsError):
            continue
        except _EntryMissing:
            raise
        quarantine_name = candidate
        break
    if quarantine_name is None:
        raise BlobCleanupError("blob cleanup failed")

    descriptor: int | None = None
    try:
        descriptor = _posix_open_existing_fd(quarantine_fd, quarantine_name, os.O_RDONLY)
        information = _posix_fstat(descriptor)
        if not stat.S_ISREG(information.st_mode):
            raise BlobCleanupError("blob cleanup failed")
        if _posix_identity(information) != expected_identity:
            raise BlobCleanupError("blob cleanup failed")
        return _PosixQuarantined(
            original_name=name,
            quarantine_name=quarantine_name,
            descriptor=descriptor,
            identity=expected_identity,
        )
    except Exception as error:
        if descriptor is not None:
            try:
                _posix_close_fd(descriptor, True)
            except BlobStorageError:
                pass
            descriptor = None
        try:
            _posix_restore_quarantine(
                root_fd,
                quarantine_fd,
                quarantine_name,
                name,
            )
        except BlobStorageError:
            pass
        if isinstance(error, BlobStorageError):
            raise BlobCleanupError("blob cleanup failed") from None
        raise BlobCleanupError("blob cleanup failed") from None


def _posix_restore_quarantined(
    root_fd: int,
    quarantine_fd: int,
    quarantined: _PosixQuarantined,
) -> None:
    close_failed = False
    try:
        _posix_close_fd(quarantined.descriptor, True)
    except BlobStorageError:
        close_failed = True
    try:
        _posix_restore_quarantine(
            root_fd,
            quarantine_fd,
            quarantined.quarantine_name,
            quarantined.original_name,
        )
    except BlobStorageError:
        raise BlobCleanupError("blob cleanup failed") from None
    if close_failed:
        raise BlobCleanupError("blob cleanup failed")


def _posix_commit_quarantined(
    quarantine_fd: int,
    quarantined: _PosixQuarantined,
) -> None:
    unlink_failed = False
    try:
        _posix_unlink_name(quarantine_fd, quarantined.quarantine_name)
    except BlobStorageError:
        unlink_failed = True
    close_failed = False
    try:
        _posix_close_fd(quarantined.descriptor, True)
    except BlobStorageError:
        close_failed = True
    if unlink_failed or close_failed:
        raise BlobCleanupError("blob cleanup failed")


def _posix_quarantine_unlink(
    root_fd: int,
    quarantine_fd: int,
    name: str,
    expected_identity: tuple[int, int],
    *,
    token_factory: Callable[[], str] | None = None,
) -> None:
    try:
        quarantined = _posix_quarantine_expected(
            root_fd,
            quarantine_fd,
            name,
            expected_identity,
            token_factory=token_factory,
        )
    except _EntryMissing:
        return
    _posix_commit_quarantined(quarantine_fd, quarantined)


def _posix_read_bounded(descriptor: int, limit: int) -> bytes:
    result = bytearray()
    maximum = limit + 1
    while len(result) < maximum:
        try:
            chunk = os.read(descriptor, min(64 * 1024, maximum - len(result)))
        except OSError:
            raise BlobStorageError("blob storage operation failed") from None
        if not chunk:
            break
        result.extend(chunk)
    if len(result) > limit:
        raise BlobSizeLimitExceededError("blob exceeds configured size limit")
    return bytes(result)


def _posix_write_all(descriptor: int, data: bytes) -> None:
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise BlobStorageError("blob storage operation failed")
            offset += written
        os.fsync(descriptor)
    except BlobStorageError:
        raise
    except OSError:
        raise BlobStorageError("blob storage operation failed") from None


def _open_local_anchor(root: Path) -> _LocalAnchor:
    if os.name == "nt":
        return _WindowsRootAnchor(root)
    return _PosixRootAnchor(root)


class LocalBlobStorage:
    """Filesystem implementation anchored to one non-replaceable root handle."""

    def __init__(
        self,
        root: Path,
        *,
        max_blob_bytes: int,
        key_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise TypeError("root must be a Path")
        self._max_blob_bytes = _validate_size_limit(max_blob_bytes)
        self._key_factory = key_factory or (lambda: uuid.uuid4().hex)
        self._anchor = _open_local_anchor(root)
        self._lock = RLock()

    def __repr__(self) -> str:
        return "<LocalBlobStorage backend='local'>"

    def close(self) -> None:
        with self._lock:
            self._anchor.close()

    def put(
        self,
        data: bytes,
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> BlobMetadata:
        validated_data = _validate_data(data, self._max_blob_bytes)
        validated_content_type = _validate_content_type(content_type)
        validated_metadata = _validate_caller_metadata(metadata)
        key = _generate_key(self._key_factory)
        result = _new_metadata(
            backend="local",
            key=key,
            data=validated_data,
            content_type=validated_content_type,
            metadata=validated_metadata,
        )
        sidecar_bytes = _serialize_metadata(result)
        with self._lock:
            try:
                self._anchor.write_pair(
                    key,
                    validated_data,
                    f"{key}{_SIDECAR_SUFFIX}",
                    sidecar_bytes,
                )
            except _EntryCollision:
                raise BlobAlreadyExistsError("blob key already exists") from None
        return result

    def get(self, uri: str) -> bytes:
        _, data = self._read_verified(uri)
        return data

    def exists(self, uri: str) -> bool:
        key = _parse_uri(uri, expected_backend="local")
        with self._lock:
            content_exists, sidecar_exists = self._anchor.pair_exists(
                key, f"{key}{_SIDECAR_SUFFIX}"
            )
        if not content_exists and not sidecar_exists:
            return False
        if not content_exists or not sidecar_exists:
            raise BlobStorageError("blob storage entry is incomplete")
        return True

    def delete(self, uri: str) -> None:
        key = _parse_uri(uri, expected_backend="local")
        with self._lock:
            try:
                self._anchor.delete_pair(key, f"{key}{_SIDECAR_SUFFIX}")
            except _EntryMissing:
                raise BlobNotFoundError("blob not found") from None

    def checksum(self, uri: str) -> str:
        metadata, _ = self._read_verified(uri)
        return metadata.checksum_sha256

    def metadata(self, uri: str) -> BlobMetadata:
        metadata, _ = self._read_verified(uri)
        return metadata

    def _read_verified(self, uri: str) -> tuple[BlobMetadata, bytes]:
        key = _parse_uri(uri, expected_backend="local")
        with self._lock:
            try:
                data, raw_sidecar = self._anchor.read_pair(
                    key,
                    f"{key}{_SIDECAR_SUFFIX}",
                    content_limit=self._max_blob_bytes,
                    sidecar_limit=_MAX_SIDECAR_BYTES,
                )
            except _EntryMissing:
                content_exists, sidecar_exists = self._anchor.pair_exists(
                    key, f"{key}{_SIDECAR_SUFFIX}"
                )
                if not content_exists and not sidecar_exists:
                    raise BlobNotFoundError("blob not found") from None
                raise BlobStorageError("blob storage entry is incomplete") from None
        metadata = _deserialize_metadata(
            raw_sidecar,
            expected_uri=uri,
            max_blob_bytes=self._max_blob_bytes,
        )
        if len(data) != metadata.size_bytes:
            raise BlobStorageError("blob integrity check failed")
        if hashlib.sha256(data).hexdigest() != metadata.checksum_sha256:
            raise BlobStorageError("blob integrity check failed")
        return metadata, data


def _serialize_metadata(metadata: BlobMetadata) -> bytes:
    value = {
        "checksum_sha256": metadata.checksum_sha256,
        "content_type": metadata.content_type,
        "metadata": dict(metadata.metadata),
        "size_bytes": metadata.size_bytes,
        "uri": metadata.uri,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _deserialize_metadata(
    raw: bytes,
    *,
    expected_uri: str,
    max_blob_bytes: int,
) -> BlobMetadata:
    try:
        value: Any = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BlobStorageError("blob metadata is invalid") from None
    if not isinstance(value, dict) or set(value) != {
        "checksum_sha256",
        "content_type",
        "metadata",
        "size_bytes",
        "uri",
    }:
        raise BlobStorageError("blob metadata is invalid")
    uri = value["uri"]
    checksum = value["checksum_sha256"]
    size_bytes = value["size_bytes"]
    caller_metadata = value["metadata"]
    if uri != expected_uri or not isinstance(uri, str):
        raise BlobStorageError("blob metadata is invalid")
    if not isinstance(checksum, str) or _CHECKSUM_PATTERN.fullmatch(checksum) is None:
        raise BlobStorageError("blob metadata is invalid")
    if (
        isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 0
        or size_bytes > max_blob_bytes
    ):
        raise BlobStorageError("blob metadata is invalid")
    if not isinstance(caller_metadata, dict):
        raise BlobStorageError("blob metadata is invalid")
    validated_content_type = _validate_content_type(value["content_type"])
    validated_metadata = _validate_caller_metadata(caller_metadata)
    return BlobMetadata(
        uri=uri,
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        content_type=validated_content_type,
        metadata=validated_metadata,
    )


__all__ = [
    "BlobAlreadyExistsError",
    "BlobCleanupError",
    "BlobMetadata",
    "BlobNotFoundError",
    "BlobSizeLimitExceededError",
    "BlobStorage",
    "BlobStorageError",
    "InMemoryBlobStorage",
    "InvalidBlobURIError",
    "LocalBlobStorage",
]
