from __future__ import annotations

from pathlib import Path

import pytest

from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.file_security import resolve_inbox_file


def test_resolve_inbox_file_returns_safe_relative_identity(tmp_path: Path) -> None:
    root = tmp_path / "inbox"
    nested = root / "batch"
    nested.mkdir(parents=True)
    source = nested / "filing.html"
    source.write_bytes(b"synthetic\n")

    resolved = resolve_inbox_file(root, "batch/filing.html")

    assert resolved.relative_name == "batch/filing.html"
    assert resolved.safe_filename == "filing.html"
    assert resolved.read_bytes() == b"synthetic\n"
    assert "absolute_path" not in resolved.safe_summary()
    assert str(root.resolve()) not in str(resolved.safe_summary())


@pytest.mark.parametrize(
    "value",
    ["../outside.pdf", "batch/../../outside.pdf", "batch/../filing.html"],
)
def test_parent_traversal_is_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        resolve_inbox_file(tmp_path, value)

    assert exc_info.value.code == "PATH_TRAVERSAL"


@pytest.mark.parametrize(
    "value",
    ["C:/evidence/file.pdf", "C:\\evidence\\file.pdf", "/evidence/file.pdf"],
)
def test_absolute_paths_are_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        resolve_inbox_file(tmp_path, value)

    assert exc_info.value.code == "ABSOLUTE_PATH"


@pytest.mark.parametrize(
    "value",
    [r"\\server\share\file.pdf", "//server/share/file.pdf"],
)
def test_unc_paths_are_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        resolve_inbox_file(tmp_path, value)

    assert exc_info.value.code == "UNC_PATH"


def test_resolved_target_outside_root_is_rejected_as_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "inbox"
    root.mkdir()
    link = root / "link.pdf"
    link.write_bytes(b"placeholder")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    original_resolve = Path.resolve

    def controlled_resolve(path: Path, *, strict: bool = False) -> Path:
        if path == link:
            return original_resolve(outside, strict=strict)
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", controlled_resolve)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        resolve_inbox_file(root, "link.pdf")

    assert exc_info.value.code == "SYMLINK_ESCAPE"
