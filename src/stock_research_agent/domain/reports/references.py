"""Stable first-appearance allocation for visible report references."""

from __future__ import annotations

import re
from collections import defaultdict
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from stock_research_agent.domain.reports.reporting import (
    StructuredReportBlock,
    StructuredReportContent,
    StructuredReportSection,
)
from stock_research_agent.domain.reports.schemas import FrozenReportContract

_REFERENCE_PATTERN = re.compile(r"\[(CIT|EV|MET|LIM|CON)-[0-9]{3}\]")


class ReportReferenceError(ValueError):
    """Stable rejection for a non-bijective visible reference graph."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReferenceKind(StrEnum):
    CITATION = "CITATION"
    EVIDENCE = "EVIDENCE"
    METRIC = "METRIC"
    LIMITATION = "LIMITATION"
    CONFLICT = "CONFLICT"


class ReferenceTarget(FrozenReportContract):
    kind: ReferenceKind
    record_id: UUID
    label: str = Field(pattern=r"^(CIT|EV|MET|LIM|CON)-[0-9]{3}$")

    @model_validator(mode="after")
    def require_kind_prefix(self) -> Self:
        if not self.label.startswith(f"{_PREFIX[self.kind]}-"):
            raise ValueError("reference label prefix must match its kind")
        return self


class ReferenceEntry(FrozenReportContract):
    kind: ReferenceKind
    record_id: UUID
    label: str = Field(pattern=r"^(CIT|EV|MET|LIM|CON)-[0-9]{3}$")


class ReferenceAllocation(FrozenReportContract):
    content: StructuredReportContent
    references: tuple[ReferenceEntry, ...] = Field(max_length=5000)


class ReportReferenceAllocator:
    """Recalculate labels solely from canonical content traversal order."""

    def allocate(
        self,
        content: StructuredReportContent,
    ) -> ReferenceAllocation:
        targets = _collect_targets(content)
        _validate_existing_graph(content, targets)
        replacements, entries = _allocate(targets)
        return ReferenceAllocation(
            content=_rewrite_content(content, replacements),
            references=entries,
        )


def _collect_targets(
    content: StructuredReportContent,
) -> tuple[ReferenceTarget, ...]:
    targets: list[ReferenceTarget] = []
    for section in content.sections:
        for block in section.blocks:
            raw = block.payload.get("reference_targets", [])
            if not isinstance(raw, list):
                raise ReportReferenceError("REFERENCE_TARGETS_INVALID")
            for item in raw:
                try:
                    if not isinstance(item, dict):
                        raise TypeError
                    targets.append(
                        ReferenceTarget(
                            kind=ReferenceKind(str(item["kind"])),
                            record_id=UUID(str(item["record_id"])),
                            label=str(item["label"]),
                        )
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ReportReferenceError("REFERENCE_TARGET_INVALID") from error
    return tuple(targets)


def _validate_existing_graph(
    content: StructuredReportContent,
    targets: tuple[ReferenceTarget, ...],
) -> None:
    label_to_record: dict[str, tuple[ReferenceKind, UUID]] = {}
    record_to_label: dict[tuple[ReferenceKind, UUID], str] = {}
    for target in targets:
        key = (target.kind, target.record_id)
        prior_record = label_to_record.setdefault(target.label, key)
        if prior_record != key:
            raise ReportReferenceError("REFERENCE_LABEL_NOT_BIJECTIVE")
        prior_label = record_to_label.setdefault(key, target.label)
        if prior_label != target.label:
            raise ReportReferenceError("REFERENCE_RECORD_NOT_BIJECTIVE")
    body_labels = _body_labels(content)
    if body_labels - set(label_to_record):
        raise ReportReferenceError("BODY_REFERENCE_UNBOUND")
    if set(label_to_record) - body_labels:
        raise ReportReferenceError("REFERENCE_TARGET_UNUSED")


def _body_labels(content: StructuredReportContent) -> set[str]:
    labels: set[str] = set()
    for section in content.sections:
        for block in section.blocks:
            labels.update(_labels_in_text(block.text or ""))
            reference = block.payload.get("reference")
            if isinstance(reference, str):
                labels.update(_labels_in_text(reference))
    return labels


def _labels_in_text(value: str) -> set[str]:
    return {match.group(0)[1:-1] for match in _REFERENCE_PATTERN.finditer(value)}


def _allocate(
    targets: tuple[ReferenceTarget, ...],
) -> tuple[dict[str, str], tuple[ReferenceEntry, ...]]:
    counters: dict[ReferenceKind, int] = defaultdict(int)
    by_record: dict[tuple[ReferenceKind, UUID], ReferenceEntry] = {}
    replacements: dict[str, str] = {}
    ordered: list[ReferenceEntry] = []
    for target in targets:
        key = (target.kind, target.record_id)
        entry = by_record.get(key)
        if entry is None:
            counters[target.kind] += 1
            entry = ReferenceEntry(
                kind=target.kind,
                record_id=target.record_id,
                label=f"{_PREFIX[target.kind]}-{counters[target.kind]:03d}",
            )
            by_record[key] = entry
            ordered.append(entry)
        replacements[target.label] = entry.label
    return replacements, tuple(ordered)


def _rewrite_content(
    content: StructuredReportContent,
    replacements: dict[str, str],
) -> StructuredReportContent:
    sections = tuple(
        StructuredReportSection(
            section=section.section,
            section_index=section.section_index,
            title=section.title,
            status=section.status,
            blocks=tuple(_rewrite_block(block, replacements) for block in section.blocks),
        )
        for section in content.sections
    )
    return StructuredReportContent(
        schema_version=content.schema_version,
        locale=content.locale,
        sections=sections,
    )


def _rewrite_block(
    block: StructuredReportBlock,
    replacements: dict[str, str],
) -> StructuredReportBlock:
    return StructuredReportBlock(
        block_key=block.block_key,
        block_index=block.block_index,
        block_type=block.block_type,
        status=block.status,
        text=(None if block.text is None else _replace_reference_text(block.text, replacements)),
        payload={key: _rewrite_json(value, replacements) for key, value in block.payload.items()},
    )


def _rewrite_json(
    value: JsonValue,
    replacements: dict[str, str],
) -> JsonValue:
    if isinstance(value, str):
        return _replace_reference_text(value, replacements)
    if isinstance(value, list):
        return [_rewrite_json(item, replacements) for item in value]
    if isinstance(value, dict):
        rewritten = {key: _rewrite_json(item, replacements) for key, item in value.items()}
        label = rewritten.get("label")
        if isinstance(label, str) and label in replacements:
            rewritten["label"] = replacements[label]
        return rewritten
    return value


def _replace_reference_text(
    value: str,
    replacements: dict[str, str],
) -> str:
    def replace(match: re.Match[str]) -> str:
        old = match.group(0)[1:-1]
        return f"[{replacements.get(old, old)}]"

    return _REFERENCE_PATTERN.sub(replace, value)


_PREFIX = {
    ReferenceKind.CITATION: "CIT",
    ReferenceKind.EVIDENCE: "EV",
    ReferenceKind.METRIC: "MET",
    ReferenceKind.LIMITATION: "LIM",
    ReferenceKind.CONFLICT: "CON",
}
