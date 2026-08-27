from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
import re
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from stock_research_agent.infrastructure.blob_storage import (
    BlobAlreadyExistsError,
    BlobCleanupError,
    BlobMetadata,
    BlobNotFoundError,
    BlobSizeLimitExceededError,
    BlobStorage,
    BlobStorageError,
    InMemoryBlobStorage,
    InvalidBlobURIError,
    LocalBlobStorage,
)

LOCAL_KEY = "a" * 32
MEMORY_KEY = "b" * 32


def _fixed_key(value: str) -> Callable[[], str]:
    return lambda: value


def _write_external_blob(root: Path, key: str, data: bytes) -> None:
    root.mkdir(parents=True, exist_ok=True)
    uri = f"blob://local/{key}"
    metadata = {
        "checksum_sha256": hashlib.sha256(data).hexdigest(),
        "content_type": "application/octet-stream",
        "metadata": {},
        "size_bytes": len(data),
        "uri": uri,
    }
    (root / key).write_bytes(data)
    (root / f"{key}.metadata.json").write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


@contextmanager
def _attempt_root_replacement(root: Path, outside: Path) -> Iterator[bool]:
    backup = root.with_name(f"{root.name}-original")
    replaced = False
    try:
        root.rename(backup)
        if os.name == "nt":
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(root), str(outside)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            root.symlink_to(outside, target_is_directory=True)
        replaced = True
    except OSError:
        # Windows storage pins the root with a handle that denies delete/rename.
        pass
    try:
        yield replaced
    finally:
        if replaced:
            if os.name == "nt":
                root.rmdir()
            else:
                root.unlink()
            backup.rename(root)


@pytest.fixture(params=["memory", "local"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> BlobStorage:
    if request.param == "memory":
        return InMemoryBlobStorage(max_blob_bytes=64, key_factory=_fixed_key(MEMORY_KEY))
    return LocalBlobStorage(
        tmp_path / "blobs", max_blob_bytes=64, key_factory=_fixed_key(LOCAL_KEY)
    )


def test_round_trip_has_exact_checksum_size_and_immutable_metadata(storage: BlobStorage) -> None:
    data = b"\x00verified fixture bytes\xff"
    caller_metadata = {"provider": "STAGE1_FIXTURE", "mode": "OFFLINE"}

    result = storage.put(
        data,
        content_type="application/json",
        metadata=caller_metadata,
    )
    caller_metadata["mode"] = "LIVE"

    expected_checksum = hashlib.sha256(data).hexdigest()
    assert storage.get(result.uri) == data
    assert storage.exists(result.uri) is True
    assert storage.checksum(result.uri) == expected_checksum
    assert result == storage.metadata(result.uri)
    assert result.checksum_sha256 == expected_checksum
    assert result.size_bytes == len(data)
    assert result.content_type == "application/json"
    assert dict(result.metadata) == {
        "provider": "STAGE1_FIXTURE",
        "mode": "OFFLINE",
    }
    with pytest.raises(TypeError):
        result.metadata["mode"] = "LIVE"  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.uri = "blob://memory/" + ("c" * 32)  # type: ignore[misc]


def test_empty_payload_is_explicitly_supported(storage: BlobStorage) -> None:
    result = storage.put(b"", content_type="application/octet-stream")

    assert result.size_bytes == 0
    assert storage.get(result.uri) == b""
    assert dict(result.metadata) == {}


def test_generated_uri_is_opaque_and_uses_strict_key(tmp_path: Path) -> None:
    memory = InMemoryBlobStorage(max_blob_bytes=10)
    local = LocalBlobStorage(tmp_path / "private-root", max_blob_bytes=10)

    memory_result = memory.put(b"x", content_type="text/plain")
    local_result = local.put(b"x", content_type="text/plain")

    assert re.fullmatch(r"blob://memory/[0-9a-f]{32}", memory_result.uri)
    assert re.fullmatch(r"blob://local/[0-9a-f]{32}", local_result.uri)
    assert str(tmp_path) not in local_result.uri
    assert str(tmp_path) not in repr(local_result)
    assert str(tmp_path) not in repr(local)


@pytest.mark.parametrize("backend", ["memory", "local"])
def test_generated_key_collision_never_overwrites(tmp_path: Path, backend: str) -> None:
    key = "d" * 32
    instance: BlobStorage
    if backend == "memory":
        instance = InMemoryBlobStorage(max_blob_bytes=20, key_factory=_fixed_key(key))
    else:
        instance = LocalBlobStorage(
            tmp_path / "blobs",
            max_blob_bytes=20,
            key_factory=_fixed_key(key),
        )

    first = instance.put(b"original", content_type="text/plain", metadata={"v": "1"})
    with pytest.raises(BlobAlreadyExistsError):
        instance.put(b"replacement", content_type="text/plain", metadata={"v": "2"})

    assert instance.get(first.uri) == b"original"
    assert dict(instance.metadata(first.uri).metadata) == {"v": "1"}


@pytest.mark.parametrize(
    ("backend", "uri"),
    [
        ("local", f"blob://memory/{LOCAL_KEY}"),
        ("memory", f"blob://local/{MEMORY_KEY}"),
        ("local", f"file://local/{LOCAL_KEY}"),
        ("local", f"blob:///C:/private/{LOCAL_KEY}"),
        ("local", "blob://local/.."),
        ("local", f"blob://local/path/{LOCAL_KEY}"),
        ("local", r"blob://local/path\escape"),
        ("local", "blob://local/%2e%2e"),
        ("local", "blob://local/%2Fetc"),
        ("local", "blob://local/%5cwindows"),
        ("local", f"blob://local/{LOCAL_KEY}?download=1"),
        ("local", f"blob://local/{LOCAL_KEY}#fragment"),
        ("local", f"blob://user:pass@local/{LOCAL_KEY}"),
        ("local", f"blob://local/{LOCAL_KEY}\n"),
        ("local", "blob://local/ABCDEF0123456789ABCDEF0123456789"),
        ("local", "blob://local/too-short"),
    ],
)
def test_invalid_uri_forms_are_rejected_without_echo(
    tmp_path: Path,
    backend: str,
    uri: str,
) -> None:
    instance: BlobStorage = (
        LocalBlobStorage(tmp_path / "blobs", max_blob_bytes=10)
        if backend == "local"
        else InMemoryBlobStorage(max_blob_bytes=10)
    )

    with pytest.raises(InvalidBlobURIError) as captured:
        instance.get(uri)

    assert uri not in str(captured.value)
    assert str(tmp_path) not in str(captured.value)


@pytest.mark.parametrize("backend", ["memory", "local"])
def test_size_boundary_is_accepted_and_oversize_leaves_no_blob(
    tmp_path: Path,
    backend: str,
) -> None:
    key = "e" * 32
    instance: BlobStorage
    uri: str
    if backend == "memory":
        instance = InMemoryBlobStorage(max_blob_bytes=4, key_factory=_fixed_key(key))
        uri = f"blob://memory/{key}"
    else:
        instance = LocalBlobStorage(
            tmp_path / "blobs",
            max_blob_bytes=4,
            key_factory=_fixed_key(key),
        )
        uri = f"blob://local/{key}"

    result = instance.put(b"1234", content_type="text/plain")
    assert result.size_bytes == 4
    instance.delete(result.uri)

    with pytest.raises(BlobSizeLimitExceededError):
        instance.put(b"12345", content_type="text/plain")
    assert instance.exists(uri) is False


@pytest.mark.parametrize("backend", ["memory", "local"])
def test_missing_blob_has_false_exists_and_typed_errors(tmp_path: Path, backend: str) -> None:
    uri = f"blob://{backend}/" + ("f" * 32)
    instance: BlobStorage = (
        LocalBlobStorage(tmp_path / "blobs", max_blob_bytes=10)
        if backend == "local"
        else InMemoryBlobStorage(max_blob_bytes=10)
    )

    assert instance.exists(uri) is False
    for operation in (instance.get, instance.checksum, instance.metadata, instance.delete):
        with pytest.raises(BlobNotFoundError):
            operation(uri)


def test_local_sidecar_survives_new_instance(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    first = LocalBlobStorage(root, max_blob_bytes=100, key_factory=_fixed_key(LOCAL_KEY))
    expected = first.put(
        b"persistent",
        content_type="application/json",
        metadata={"source": "fixture"},
    )

    reopened = LocalBlobStorage(root, max_blob_bytes=100)

    assert reopened.get(expected.uri) == b"persistent"
    assert reopened.metadata(expected.uri) == expected
    assert reopened.checksum(expected.uri) == expected.checksum_sha256


def test_local_rejects_symlink_escape_without_reading_external_file(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    root.mkdir()
    external = tmp_path / "outside"
    external.mkdir()
    marker = external / "secret.txt"
    marker.write_bytes(b"outside")
    key = "1" * 32
    link = root / key
    if os.name == "nt":
        subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(external)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        link.symlink_to(external, target_is_directory=True)
    uri = f"blob://local/{key}"
    instance = LocalBlobStorage(root, max_blob_bytes=100)

    for operation in (instance.get, instance.checksum, instance.metadata, instance.delete):
        with pytest.raises(InvalidBlobURIError) as captured:
            operation(uri)
        assert str(external) not in str(captured.value)
    assert marker.read_bytes() == b"outside"


def test_delete_removes_only_selected_blob_and_sidecar(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    keys = iter(("2" * 32, "3" * 32))
    instance = LocalBlobStorage(root, max_blob_bytes=100, key_factory=lambda: next(keys))
    first = instance.put(b"first", content_type="text/plain")
    second = instance.put(b"second", content_type="text/plain")
    external = tmp_path / "unregistered.txt"
    external.write_text("preserve", encoding="utf-8")

    instance.delete(first.uri)

    assert instance.exists(first.uri) is False
    assert instance.get(second.uri) == b"second"
    assert external.read_text(encoding="utf-8") == "preserve"
    expected_names = [
        "3" * 32,
        ("3" * 32) + ".metadata.json",
    ]
    if os.name == "posix":
        expected_names.append(".blob-quarantine")
    assert sorted(path.name for path in root.iterdir()) == sorted(expected_names)


def test_failed_local_publication_cleans_only_files_created_by_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root = tmp_path / "blobs"
    unrelated = root / "unrelated"
    root.mkdir()
    unrelated.write_bytes(b"preserve")
    instance = LocalBlobStorage(
        root,
        max_blob_bytes=100,
        key_factory=_fixed_key("4" * 32),
    )
    calls = 0
    if os.name == "nt":
        real_link = module._create_hard_link

        def fail_second_link(source: str, destination: str) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated sidecar publication failure")
            real_link(source, destination)

        monkeypatch.setattr(module, "_create_hard_link", fail_second_link)
    else:
        real_link_posix = module.os.link

        def fail_second_posix_link(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated sidecar publication failure")
            real_link_posix(*args, **kwargs)

        monkeypatch.setattr(module.os, "link", fail_second_posix_link)

    with pytest.raises(BlobStorageError) as captured:
        instance.put(b"content", content_type="text/plain")

    assert str(root) not in str(captured.value)
    assert unrelated.read_bytes() == b"preserve"
    expected_names = ["unrelated"]
    if os.name == "posix":
        expected_names.append(".blob-quarantine")
    assert sorted(path.name for path in root.iterdir()) == sorted(expected_names)


@pytest.mark.parametrize(
    ("content_type", "metadata"),
    [
        ("", None),
        ("   ", None),
        ("text/plain\nInjected: yes", None),
        ("x" * 256, None),
        ("text/plain", {"": "value"}),
        ("text/plain", {"key": ""}),
        ("text/plain", {"key\n": "value"}),
        ("text/plain", {"key": "value\x00"}),
        ("text/plain", {"k" * 65: "value"}),
        ("text/plain", {"key": "v" * 1025}),
    ],
)
def test_content_type_and_caller_metadata_are_bounded(
    content_type: str,
    metadata: dict[str, str] | None,
) -> None:
    instance = InMemoryBlobStorage(max_blob_bytes=10)

    with pytest.raises(BlobStorageError):
        instance.put(b"x", content_type=content_type, metadata=metadata)


def test_metadata_rejects_non_string_key_or_value() -> None:
    instance = InMemoryBlobStorage(max_blob_bytes=10)

    with pytest.raises(BlobStorageError):
        instance.put(
            b"x",
            content_type="text/plain",
            metadata={"attempt": 1},  # type: ignore[dict-item]
        )


def test_constructor_rejects_non_positive_size_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        InMemoryBlobStorage(max_blob_bytes=0)


def test_protocol_is_runtime_checkable_for_both_implementations(tmp_path: Path) -> None:
    assert isinstance(InMemoryBlobStorage(max_blob_bytes=10), BlobStorage)
    assert isinstance(LocalBlobStorage(tmp_path / "blobs", max_blob_bytes=10), BlobStorage)


def test_module_import_performs_no_filesystem_or_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "stock_research_agent.infrastructure.blob_storage"
    existing = sys.modules.pop(module_name, None)

    def unexpected(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("I/O during module import")

    monkeypatch.setattr(Path, "mkdir", unexpected)
    monkeypatch.setattr(Path, "read_bytes", unexpected)
    monkeypatch.setattr(Path, "write_bytes", unexpected)
    monkeypatch.setattr(socket, "create_connection", unexpected)
    try:
        imported = importlib.import_module(module_name)
        assert imported.BlobStorage is not None
    finally:
        sys.modules.pop(module_name, None)
        if existing is not None:
            sys.modules[module_name] = existing


def test_exception_hierarchy_is_typed() -> None:
    assert issubclass(InvalidBlobURIError, BlobStorageError)
    assert issubclass(BlobNotFoundError, BlobStorageError)
    assert issubclass(BlobAlreadyExistsError, BlobStorageError)
    assert issubclass(BlobSizeLimitExceededError, BlobStorageError)
    assert issubclass(BlobCleanupError, BlobStorageError)


def test_invalid_key_from_factory_is_rejected_without_leaking_value() -> None:
    invalid_key = r"C:\private\secret"
    instance = InMemoryBlobStorage(max_blob_bytes=10, key_factory=_fixed_key(invalid_key))

    with pytest.raises(InvalidBlobURIError) as captured:
        instance.put(b"x", content_type="text/plain")

    assert invalid_key not in str(captured.value)


def test_local_blob_metadata_contains_no_absolute_path(tmp_path: Path) -> None:
    instance = LocalBlobStorage(
        tmp_path / "private-root",
        max_blob_bytes=10,
        key_factory=_fixed_key("5" * 32),
    )

    result: BlobMetadata = instance.put(b"x", content_type="text/plain")

    assert str(tmp_path) not in repr(result)
    assert str(tmp_path) not in result.uri
    assert all(str(tmp_path) not in value for value in result.metadata.values())


def test_direct_blob_metadata_construction_copies_and_freezes_mapping() -> None:
    caller_metadata = {"mode": "OFFLINE"}

    result = BlobMetadata(
        uri=f"blob://memory/{MEMORY_KEY}",
        checksum_sha256=hashlib.sha256(b"x").hexdigest(),
        size_bytes=1,
        content_type="text/plain",
        metadata=caller_metadata,
    )
    caller_metadata["mode"] = "LIVE"

    assert dict(result.metadata) == {"mode": "OFFLINE"}
    with pytest.raises(TypeError):
        result.metadata["mode"] = "LIVE"  # type: ignore[index]


def test_root_replacement_cannot_redirect_get_to_external_junction(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    outside = tmp_path / "outside"
    key = "6" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=100, key_factory=_fixed_key(key))
    result = instance.put(b"inside", content_type="application/octet-stream")
    _write_external_blob(outside, key, b"outside")

    with _attempt_root_replacement(root, outside) as replaced:
        if os.name == "nt":
            assert replaced is False
        assert instance.get(result.uri) == b"inside"

    assert (outside / key).read_bytes() == b"outside"


def test_root_replacement_cannot_redirect_put_to_external_junction(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    key = "7" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=100, key_factory=_fixed_key(key))

    with _attempt_root_replacement(root, outside) as replaced:
        if os.name == "nt":
            assert replaced is False
        result = instance.put(b"inside", content_type="application/octet-stream")
        assert not (outside / key).exists()

    assert instance.get(result.uri) == b"inside"


def test_root_replacement_cannot_redirect_delete_to_external_junction(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    outside = tmp_path / "outside"
    key = "8" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=100, key_factory=_fixed_key(key))
    result = instance.put(b"inside", content_type="application/octet-stream")
    _write_external_blob(outside, key, b"outside")

    with _attempt_root_replacement(root, outside) as replaced:
        if os.name == "nt":
            assert replaced is False
        instance.delete(result.uri)
        assert (outside / key).read_bytes() == b"outside"

    assert instance.exists(result.uri) is False


@pytest.mark.parametrize("backend", ["memory", "local"])
def test_key_factory_failure_is_typed_redacted_and_has_no_cause(
    tmp_path: Path,
    backend: str,
) -> None:
    secret_path = str(tmp_path / "private-key-source")

    def fail() -> str:
        raise RuntimeError(secret_path)

    instance: BlobStorage = (
        LocalBlobStorage(tmp_path / "blobs", max_blob_bytes=10, key_factory=fail)
        if backend == "local"
        else InMemoryBlobStorage(max_blob_bytes=10, key_factory=fail)
    )

    with pytest.raises(InvalidBlobURIError) as captured:
        instance.put(b"x", content_type="text/plain")

    assert secret_path not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize(
    "metadata",
    [
        {r"C:\private\key": "value"},
        {r"\\server\share\key": "value"},
        {"/private/key": "value"},
        {"key": r"C:\private\value"},
        {"key": r"\\server\share\value"},
        {"key": "/private/value"},
    ],
)
def test_metadata_rejects_absolute_paths_in_keys_and_values(metadata: dict[str, str]) -> None:
    instance = InMemoryBlobStorage(max_blob_bytes=10)

    with pytest.raises(BlobStorageError) as captured:
        instance.put(b"x", content_type="text/plain", metadata=metadata)

    assert "private" not in str(captured.value)
    assert "server" not in str(captured.value)


def test_local_read_does_not_use_unbounded_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = LocalBlobStorage(
        tmp_path / "blobs",
        max_blob_bytes=10,
        key_factory=_fixed_key("9" * 32),
    )
    result = instance.put(b"bounded", content_type="text/plain")

    def reject_unbounded_read(path: Path) -> bytes:
        raise AssertionError(f"unbounded path read: {path.name}")

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read)

    assert instance.get(result.uri) == b"bounded"


def test_local_oversize_content_is_rejected_by_bounded_handle_read(tmp_path: Path) -> None:
    root = tmp_path / "blobs"
    key = "a" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=4, key_factory=_fixed_key(key))
    result = instance.put(b"1234", content_type="text/plain")
    (root / key).write_bytes(b"12345")

    with pytest.raises(BlobSizeLimitExceededError):
        instance.get(result.uri)


@pytest.mark.parametrize("missing_part", ["content", "sidecar"])
def test_delete_safely_recovers_from_single_side_residual(
    tmp_path: Path,
    missing_part: str,
) -> None:
    root = tmp_path / "blobs"
    key = "b" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=10, key_factory=_fixed_key(key))
    result = instance.put(b"x", content_type="text/plain")
    target = root / (key if missing_part == "content" else f"{key}.metadata.json")
    target.unlink()

    instance.delete(result.uri)

    assert instance.exists(result.uri) is False


def test_failed_temporary_cleanup_raises_typed_safe_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root = tmp_path / "blobs"
    instance = LocalBlobStorage(
        root,
        max_blob_bytes=10,
        key_factory=_fixed_key("c" * 32),
    )
    cleanup_attempts = 0
    if os.name == "nt":
        real_delete = module._set_delete_disposition

        def fail_first_cleanup(handle: int) -> None:
            nonlocal cleanup_attempts
            cleanup_attempts += 1
            if cleanup_attempts == 1:
                raise BlobCleanupError("blob cleanup failed")
            real_delete(handle)

        monkeypatch.setattr(module, "_set_delete_disposition", fail_first_cleanup)
    else:
        real_unlink = module._PosixRootAnchor._unlink_expected

        def fail_first_cleanup_posix(
            anchor: object,
            name: str,
            expected_identity: tuple[int, int],
        ) -> None:
            nonlocal cleanup_attempts
            cleanup_attempts += 1
            if cleanup_attempts == 1:
                raise BlobCleanupError("blob cleanup failed")
            real_unlink(anchor, name, expected_identity)

        monkeypatch.setattr(
            module._PosixRootAnchor,
            "_unlink_expected",
            fail_first_cleanup_posix,
        )

    with pytest.raises(BlobCleanupError) as captured:
        instance.put(b"x", content_type="text/plain")

    assert str(root) not in str(captured.value)


def test_failed_temporary_write_removes_only_its_own_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root = tmp_path / "blobs"
    unrelated = root / "unrelated"
    root.mkdir()
    unrelated.write_bytes(b"preserve")
    instance = LocalBlobStorage(
        root,
        max_blob_bytes=10,
        key_factory=_fixed_key("d" * 32),
    )

    def fail_write(handle: int, data: bytes) -> None:
        del handle, data
        raise BlobStorageError("simulated safe write failure")

    write_function = "_win_write_all" if os.name == "nt" else "_posix_write_all"
    monkeypatch.setattr(module, write_function, fail_write)

    with pytest.raises(BlobStorageError):
        instance.put(b"x", content_type="text/plain")

    expected_names = ["unrelated"]
    if os.name == "posix":
        expected_names.append(".blob-quarantine")
    assert sorted(path.name for path in root.iterdir()) == sorted(expected_names)
    assert unrelated.read_bytes() == b"preserve"


def test_failed_published_link_verification_rolls_back_created_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root = tmp_path / "blobs"
    key = "e" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=10, key_factory=_fixed_key(key))
    failed = False
    if os.name == "nt":
        anchor_type = module._WindowsRootAnchor
        real_open = anchor_type._open_entry

        def fail_first_published_open(anchor: object, name: str, *, access: int) -> object:
            nonlocal failed
            if name == key and not failed:
                failed = True
                raise BlobStorageError("simulated safe verification failure")
            return real_open(anchor, name, access=access)

        monkeypatch.setattr(anchor_type, "_open_entry", fail_first_published_open)
    else:
        anchor_type = module._PosixRootAnchor
        real_open_posix = anchor_type._open_existing

        def fail_first_published_open_posix(
            anchor: object,
            name: str,
            access: int,
        ) -> int:
            nonlocal failed
            if name == key and not failed:
                failed = True
                raise BlobStorageError("simulated safe verification failure")
            return real_open_posix(anchor, name, access)

        monkeypatch.setattr(anchor_type, "_open_existing", fail_first_published_open_posix)

    with pytest.raises(BlobStorageError):
        instance.put(b"x", content_type="text/plain")

    assert not (root / key).exists()
    assert not (root / f"{key}.metadata.json").exists()


def test_delete_closes_first_handle_when_second_open_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root = tmp_path / "blobs"
    key = "f" * 32
    instance = LocalBlobStorage(root, max_blob_bytes=10, key_factory=_fixed_key(key))
    result = instance.put(b"x", content_type="text/plain")
    if os.name == "nt":
        anchor_type = module._WindowsRootAnchor
        real_open = anchor_type._open_entry

        def fail_sidecar_open(anchor: object, name: str, *, access: int) -> object:
            if name.endswith(".metadata.json"):
                raise BlobStorageError("simulated safe open failure")
            return real_open(anchor, name, access=access)

        monkeypatch.setattr(anchor_type, "_open_entry", fail_sidecar_open)
    else:
        anchor_type = module._PosixRootAnchor
        real_open_posix = anchor_type._open_existing

        def fail_sidecar_open_posix(anchor: object, name: str, access: int) -> int:
            if name.endswith(".metadata.json"):
                raise BlobStorageError("simulated safe open failure")
            return real_open_posix(anchor, name, access)

        monkeypatch.setattr(anchor_type, "_open_existing", fail_sidecar_open_posix)

    with pytest.raises(BlobStorageError):
        instance.delete(result.uri)

    (root / key).unlink()


def test_posix_capabilities_fail_closed_when_required_flag_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    monkeypatch.setattr(module, "_O_NOFOLLOW", 0)

    with pytest.raises(BlobStorageError) as captured:
        module._require_posix_capabilities()

    assert str(captured.value) == "required POSIX filesystem capabilities are unavailable"


def test_posix_capability_contract_is_exercised_on_every_platform(tmp_path: Path) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    if os.name == "posix":
        module._require_posix_capabilities()
        instance = LocalBlobStorage(
            tmp_path / "blobs",
            max_blob_bytes=10,
            key_factory=_fixed_key("0" * 32),
        )
        result = instance.put(b"x", content_type="text/plain")
        instance.delete(result.uri)
        assert instance.exists(result.uri) is False
    else:
        with pytest.raises(BlobStorageError):
            module._require_posix_capabilities()


def test_posix_quarantine_delete_preserves_name_swapped_after_atomic_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    expected_identity = (1, 10)
    attacker_identity = (1, 99)
    original_name = "1" * 32
    quarantine_name = "." + ("2" * 32) + ".quarantine"
    root_fd = 7
    quarantine_fd = 8
    entries = {
        root_fd: {original_name: expected_identity},
        quarantine_fd: {},
    }
    descriptors: dict[int, tuple[int, int]] = {}
    deleted: list[tuple[int, int]] = []

    def rename_noreplace(
        source_fd: int,
        source: str,
        destination_fd: int,
        destination: str,
    ) -> None:
        entries[destination_fd][destination] = entries[source_fd].pop(source)
        if source == original_name:
            entries[root_fd][original_name] = attacker_identity

    def open_existing(root_fd: int, name: str, flags: int) -> int:
        del flags
        descriptors[41] = entries[root_fd][name]
        return 41

    def fstat(descriptor: int) -> object:
        device, inode = descriptors[descriptor]
        return SimpleNamespace(st_dev=device, st_ino=inode, st_mode=0o100600)

    def unlink(root_fd: int, name: str) -> None:
        deleted.append(entries[root_fd].pop(name))

    monkeypatch.setattr(module, "_posix_rename_noreplace", rename_noreplace)
    monkeypatch.setattr(module, "_posix_open_existing_fd", open_existing)
    monkeypatch.setattr(module, "_posix_fstat", fstat)
    monkeypatch.setattr(module, "_posix_unlink_name", unlink)
    monkeypatch.setattr(module, "_posix_close_fd", lambda descriptor, cleanup: None)

    module._posix_quarantine_unlink(
        root_fd,
        quarantine_fd,
        original_name,
        expected_identity,
        token_factory=lambda: "2" * 32,
    )

    assert entries[root_fd] == {original_name: attacker_identity}
    assert entries[quarantine_fd] == {}
    assert deleted == [expected_identity]
    assert quarantine_name not in entries[quarantine_fd]


def test_posix_quarantine_identity_mismatch_restores_without_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    expected_identity = (1, 10)
    attacker_identity = (1, 99)
    original_name = "3" * 32
    root_fd = 7
    quarantine_fd = 8
    entries = {
        root_fd: {original_name: attacker_identity},
        quarantine_fd: {},
    }
    descriptors: dict[int, tuple[int, int]] = {}
    deleted: list[tuple[int, int]] = []

    def rename_noreplace(
        source_fd: int,
        source: str,
        destination_fd: int,
        destination: str,
    ) -> None:
        if destination in entries[destination_fd]:
            raise FileExistsError
        entries[destination_fd][destination] = entries[source_fd].pop(source)

    def open_existing(root_fd: int, name: str, flags: int) -> int:
        del flags
        descriptors[42] = entries[root_fd][name]
        return 42

    def fstat(descriptor: int) -> object:
        device, inode = descriptors[descriptor]
        return SimpleNamespace(st_dev=device, st_ino=inode, st_mode=0o100600)

    def unlink(root_fd: int, name: str) -> None:
        deleted.append(entries[root_fd].pop(name))

    monkeypatch.setattr(module, "_posix_rename_noreplace", rename_noreplace)
    monkeypatch.setattr(module, "_posix_open_existing_fd", open_existing)
    monkeypatch.setattr(module, "_posix_fstat", fstat)
    monkeypatch.setattr(module, "_posix_unlink_name", unlink)
    monkeypatch.setattr(module, "_posix_close_fd", lambda descriptor, cleanup: None)

    with pytest.raises(BlobCleanupError):
        module._posix_quarantine_unlink(
            root_fd,
            quarantine_fd,
            original_name,
            expected_identity,
            token_factory=lambda: "4" * 32,
        )

    assert entries[root_fd] == {original_name: attacker_identity}
    assert entries[quarantine_fd] == {}
    assert deleted == []


def test_posix_temporary_write_failure_closes_and_cleans_by_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    anchor = object.__new__(module._PosixRootAnchor)
    anchor._root_fd = 7
    anchor._quarantine_fd = 8
    identity = (1, 10)
    cleaned: list[tuple[str, tuple[int, int]]] = []
    closed: list[tuple[int, bool]] = []
    monkeypatch.setattr(module, "_posix_open_new_fd", lambda root_fd, name: 43)
    monkeypatch.setattr(
        module,
        "_posix_fstat",
        lambda descriptor: SimpleNamespace(st_dev=1, st_ino=10, st_mode=0o100600),
    )
    monkeypatch.setattr(
        module,
        "_posix_write_all",
        lambda descriptor, data: (_ for _ in ()).throw(BlobStorageError("safe failure")),
    )
    monkeypatch.setattr(
        module,
        "_posix_quarantine_unlink",
        lambda root_fd, quarantine_fd, name, expected_identity: cleaned.append(
            (name, expected_identity)
        ),
    )
    monkeypatch.setattr(
        module,
        "_posix_close_fd",
        lambda descriptor, cleanup: closed.append((descriptor, cleanup)),
    )

    with pytest.raises(BlobStorageError):
        anchor._create_temporary("." + ("5" * 32) + ".blob.tmp", b"x")

    assert cleaned == [("." + ("5" * 32) + ".blob.tmp", identity)]
    assert closed == [(43, True)]


def test_posix_post_open_fstat_failure_closes_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    anchor = object.__new__(module._PosixRootAnchor)
    anchor._root_fd = 7
    anchor._quarantine_fd = 8
    closed: list[tuple[int, bool]] = []
    monkeypatch.setattr(module, "_posix_open_existing_fd", lambda root_fd, name, flags: 44)
    monkeypatch.setattr(
        module,
        "_posix_fstat",
        lambda descriptor: (_ for _ in ()).throw(BlobStorageError("safe failure")),
    )
    monkeypatch.setattr(
        module,
        "_posix_close_fd",
        lambda descriptor, cleanup: closed.append((descriptor, cleanup)),
    )

    with pytest.raises(BlobStorageError):
        anchor._open_existing("6" * 32, os.O_RDONLY)

    assert closed == [(44, False)]


def test_posix_two_entry_delete_restores_first_quarantine_when_second_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    anchor = object.__new__(module._PosixRootAnchor)
    anchor._root_fd = 7
    anchor._quarantine_fd = 8
    anchor._identity = (1, 1)
    content_name = "7" * 32
    sidecar_name = content_name + ".metadata.json"
    identities = {51: (1, 10), 52: (1, 11)}
    descriptors = iter((51, 52))
    first_quarantine = SimpleNamespace(
        original_name=content_name,
        quarantine_name="." + ("8" * 32) + ".quarantine",
        descriptor=61,
        identity=(1, 10),
    )
    restored: list[object] = []
    closed: list[tuple[int, bool]] = []
    monkeypatch.setattr(anchor, "_assert_root", lambda: None)
    monkeypatch.setattr(anchor, "_open_existing", lambda name, access: next(descriptors))
    monkeypatch.setattr(
        module,
        "_posix_fstat",
        lambda descriptor: SimpleNamespace(
            st_dev=identities[descriptor][0],
            st_ino=identities[descriptor][1],
            st_mode=0o100600,
        ),
    )
    calls = 0

    def quarantine(
        root_fd: int,
        quarantine_fd: int,
        name: str,
        expected_identity: tuple[int, int],
    ) -> object:
        nonlocal calls
        del root_fd, quarantine_fd, name, expected_identity
        calls += 1
        if calls == 2:
            raise BlobCleanupError("blob cleanup failed")
        return first_quarantine

    monkeypatch.setattr(module, "_posix_quarantine_expected", quarantine)
    monkeypatch.setattr(
        module,
        "_posix_restore_quarantined",
        lambda root_fd, quarantine_fd, quarantined: restored.append(quarantined),
    )
    monkeypatch.setattr(
        module,
        "_posix_close_fd",
        lambda descriptor, cleanup: closed.append((descriptor, cleanup)),
    )

    with pytest.raises(BlobCleanupError):
        anchor.delete_pair(content_name, sidecar_name)

    assert restored == [first_quarantine]
    assert closed == [(51, True), (52, True)]


def test_windows_explicit_handle_close_failure_is_typed_cleanup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    held = module._WindowsHeldFile(123, (1, 2))
    monkeypatch.setattr(module, "_win_close", lambda handle, cleanup: False)

    with pytest.raises(BlobCleanupError):
        held.close(cleanup=True)


def test_posix_private_quarantine_directory_is_owner_only_and_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    mkdir_calls: list[tuple[int, str, int]] = []
    closed: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        module,
        "_posix_mkdir_private",
        lambda root_fd, name, mode: mkdir_calls.append((root_fd, name, mode)),
    )
    monkeypatch.setattr(module, "_posix_open_directory_at", lambda root_fd, name: 72)
    monkeypatch.setattr(
        module,
        "_posix_fstat",
        lambda descriptor: SimpleNamespace(
            st_dev=1,
            st_ino=20,
            st_mode=0o40700,
            st_uid=1000,
        ),
    )
    monkeypatch.setattr(module, "_posix_effective_uid", lambda: 1000)
    monkeypatch.setattr(
        module,
        "_posix_close_fd",
        lambda descriptor, cleanup: closed.append((descriptor, cleanup)),
    )

    descriptor, identity = module._posix_open_private_quarantine(71)

    assert descriptor == 72
    assert identity == (1, 20)
    assert mkdir_calls == [(71, module._POSIX_QUARANTINE_DIR_NAME, 0o700)]
    assert closed == []


@pytest.mark.parametrize(
    ("mode", "owner"),
    [(0o40770, 1000), (0o40707, 1000), (0o40700, 1001)],
)
def test_posix_private_quarantine_rejects_unsafe_mode_or_owner(
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
    owner: int,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    closed: list[tuple[int, bool]] = []
    monkeypatch.setattr(module, "_posix_mkdir_private", lambda root_fd, name, mode: None)
    monkeypatch.setattr(module, "_posix_open_directory_at", lambda root_fd, name: 73)
    monkeypatch.setattr(
        module,
        "_posix_fstat",
        lambda descriptor: SimpleNamespace(
            st_dev=1,
            st_ino=21,
            st_mode=mode,
            st_uid=owner,
        ),
    )
    monkeypatch.setattr(module, "_posix_effective_uid", lambda: 1000)
    monkeypatch.setattr(
        module,
        "_posix_close_fd",
        lambda descriptor, cleanup: closed.append((descriptor, cleanup)),
    )

    with pytest.raises(BlobStorageError) as captured:
        module._posix_open_private_quarantine(71)

    assert str(captured.value) == "private blob quarantine is unsafe"
    assert closed == [(73, True)]


def test_posix_private_boundary_rejects_swap_before_quarantine_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    private_fd = 80
    expected_identity = (1, 30)
    attacker_identity = (1, 99)
    quarantine_name = "." + ("9" * 32) + ".quarantine"
    entries = {quarantine_name: expected_identity}
    rejected_swap = False
    deleted_wrong_identity = False

    def unlink(directory_fd: int, name: str) -> None:
        nonlocal rejected_swap, deleted_wrong_identity
        if directory_fd == private_fd:
            rejected_swap = True
        else:
            entries[name] = attacker_identity
        deleted_wrong_identity = entries.pop(name) != expected_identity

    monkeypatch.setattr(module, "_posix_unlink_name", unlink)
    monkeypatch.setattr(module, "_posix_close_fd", lambda descriptor, cleanup: None)
    quarantined = module._PosixQuarantined(
        original_name="a" * 32,
        quarantine_name=quarantine_name,
        descriptor=81,
        identity=expected_identity,
    )

    module._posix_commit_quarantined(private_fd, quarantined)

    assert rejected_swap is True
    assert deleted_wrong_identity is False
    assert entries == {}


def test_posix_rename_probe_unsupported_fails_cleanly_without_root_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root_fd = 90
    private_fd = 91
    entries: dict[int, dict[str, int]] = {root_fd: {}, private_fd: {}}
    descriptors: dict[int, tuple[int, str]] = {}
    next_descriptor = 100

    def open_new(directory_fd: int, name: str) -> int:
        nonlocal next_descriptor
        entries[directory_fd][name] = next_descriptor
        descriptors[next_descriptor] = (directory_fd, name)
        next_descriptor += 1
        return next_descriptor - 1

    def unsupported_rename(
        source_fd: int,
        source_name: str,
        destination_fd: int,
        destination_name: str,
    ) -> None:
        del source_fd, source_name, destination_fd, destination_name
        raise BlobStorageError("required POSIX rename capability is unavailable")

    def unlink(directory_fd: int, name: str) -> None:
        entries[directory_fd].pop(name)

    monkeypatch.setattr(module, "_posix_open_new_fd", open_new)
    monkeypatch.setattr(module, "_posix_rename_noreplace", unsupported_rename)
    monkeypatch.setattr(module, "_posix_unlink_name", unlink)
    monkeypatch.setattr(module, "_posix_close_fd", lambda descriptor, cleanup: None)

    with pytest.raises(BlobStorageError) as captured:
        module._probe_posix_rename_semantics(root_fd, private_fd)

    assert str(captured.value) == "required POSIX rename capability is unavailable"
    assert entries[root_fd] == {}
    assert entries[private_fd] == {}


def test_posix_rename_probe_name_collision_is_safe_and_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root_fd = 96
    private_fd = 97
    entries: dict[int, set[str]] = {root_fd: set(), private_fd: set()}

    def open_new(directory_fd: int, name: str) -> int:
        entries[directory_fd].add(name)
        return 110

    def collide(
        source_fd: int,
        source_name: str,
        destination_fd: int,
        destination_name: str,
    ) -> None:
        del source_fd, source_name, destination_fd, destination_name
        raise module._EntryCollision

    monkeypatch.setattr(module, "_posix_open_new_fd", open_new)
    monkeypatch.setattr(module, "_posix_rename_noreplace", collide)
    monkeypatch.setattr(
        module,
        "_posix_unlink_name",
        lambda directory_fd, name: entries[directory_fd].remove(name),
    )
    monkeypatch.setattr(module, "_posix_close_fd", lambda descriptor, cleanup: None)

    with pytest.raises(BlobStorageError) as captured:
        module._probe_posix_rename_semantics(root_fd, private_fd)

    assert str(captured.value) == "required POSIX rename capability is unavailable"
    assert entries[root_fd] == set()
    assert entries[private_fd] == set()


def test_posix_rename_probe_verifies_move_and_noreplace_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    root_fd = 92
    private_fd = 93
    entries: dict[int, dict[str, int]] = {root_fd: {}, private_fd: {}}
    next_identity = 1
    collision_observed = False

    def open_new(directory_fd: int, name: str) -> int:
        nonlocal next_identity
        entries[directory_fd][name] = next_identity
        next_identity += 1
        return next_identity + 100

    def rename(
        source_fd: int,
        source_name: str,
        destination_fd: int,
        destination_name: str,
    ) -> None:
        nonlocal collision_observed
        if destination_name in entries[destination_fd]:
            collision_observed = True
            raise module._EntryCollision
        entries[destination_fd][destination_name] = entries[source_fd].pop(source_name)

    monkeypatch.setattr(module, "_posix_open_new_fd", open_new)
    monkeypatch.setattr(module, "_posix_rename_noreplace", rename)
    monkeypatch.setattr(
        module,
        "_posix_unlink_name",
        lambda directory_fd, name: entries[directory_fd].pop(name),
    )
    monkeypatch.setattr(module, "_posix_close_fd", lambda descriptor, cleanup: None)

    module._probe_posix_rename_semantics(root_fd, private_fd)

    assert collision_observed is True
    assert entries[root_fd] == {}
    assert entries[private_fd] == {}


def test_posix_anchor_constructor_probes_before_becoming_usable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    probed: list[tuple[int, int]] = []
    closed: list[tuple[int, bool]] = []
    monkeypatch.setattr(module, "_require_posix_capabilities", lambda: None)
    monkeypatch.setattr(module, "_posix_open_root_fd", lambda path: 94)
    monkeypatch.setattr(
        module,
        "_posix_fstat",
        lambda descriptor: SimpleNamespace(
            st_dev=1,
            st_ino=descriptor,
            st_mode=0o40700,
            st_uid=1000,
        ),
    )
    monkeypatch.setattr(
        module,
        "_posix_open_private_quarantine",
        lambda root_fd: (95, (1, 95)),
    )
    monkeypatch.setattr(
        module,
        "_probe_posix_rename_semantics",
        lambda root_fd, private_fd: probed.append((root_fd, private_fd)),
    )
    monkeypatch.setattr(
        module,
        "_posix_close_fd",
        lambda descriptor, cleanup: closed.append((descriptor, cleanup)),
    )
    monkeypatch.setattr(module, "_posix_close_best_effort", lambda descriptor: None)

    anchor = module._PosixRootAnchor(tmp_path / "blobs")

    assert probed == [(94, 95)]
    assert anchor._root_fd == 94
    assert anchor._quarantine_fd == 95
    anchor.close()
    assert closed == [(95, True), (94, True)]


def test_windows_last_error_binding_fails_closed_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("stock_research_agent.infrastructure.blob_storage")
    monkeypatch.setattr(module, "_CTYPES_GET_LAST_ERROR", None, raising=False)

    with pytest.raises(BlobStorageError, match="blob storage operation failed"):
        module._win_last_error()
