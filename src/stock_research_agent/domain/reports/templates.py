"""Strict data-only bilingual report template versions."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    Code,
    FrozenReportContract,
)


class TemplateStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    TEST_ONLY = "TEST_ONLY"


class TemplatePlaceholder(StrEnum):
    OFFICIAL_SECURITY_NAME = "OFFICIAL_SECURITY_NAME"
    SYMBOL = "SYMBOL"
    EXCHANGE = "EXCHANGE"
    CLAIM_VALUE = "CLAIM_VALUE"
    CLAIM_UNIT = "CLAIM_UNIT"
    CLAIM_PERIOD = "CLAIM_PERIOD"
    CLAIM_AS_OF = "CLAIM_AS_OF"
    VISIBLE_REFERENCE = "VISIBLE_REFERENCE"


class CitationStyle(StrEnum):
    BRACKETED_NUMERIC = "BRACKETED_NUMERIC"


class TemplateToken(FrozenReportContract):
    literal: str | None = Field(default=None, min_length=1, max_length=200)
    placeholder: TemplatePlaceholder | None = None

    @model_validator(mode="after")
    def require_safe_exclusive_token(self) -> Self:
        if (self.literal is None) == (self.placeholder is None):
            raise ValueError("template token requires exactly one data source")
        if self.literal is not None:
            _validate_literal(self.literal)
        return self


class TemplateSectionRule(FrozenReportContract):
    section: ReportSection
    required: bool
    allow_empty_state: bool


class StatementPattern(FrozenReportContract):
    statement_code: Code
    tokens: tuple[TemplateToken, ...] = Field(min_length=1, max_length=20)


class TableColumnDescriptor(FrozenReportContract):
    column_code: Code
    label: str = Field(min_length=1, max_length=80)
    value_placeholder: TemplatePlaceholder


class ReportTemplateVersionWrite(FrozenReportContract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    report_type: ReportType
    locale: ReportLocale
    section_keys: tuple[ReportSection, ...] = Field(min_length=1, max_length=16)
    section_rules: tuple[TemplateSectionRule, ...] = Field(
        min_length=1,
        max_length=16,
    )
    statement_patterns: tuple[StatementPattern, ...] = Field(
        min_length=1,
        max_length=100,
    )
    table_columns: tuple[TableColumnDescriptor, ...] = Field(max_length=20)
    citation_style: CitationStyle
    template_schema_version: str = Field(pattern=r"^report-template-v[1-9][0-9]*$")
    checksum: Checksum
    status: TemplateStatus

    @model_validator(mode="after")
    def require_exact_section_rules(self) -> Self:
        if tuple(item.section for item in self.section_rules) != self.section_keys:
            raise ValueError("section rules must match exact section order")
        if len(self.section_keys) != len(set(self.section_keys)):
            raise ValueError("section keys must be unique")
        return self


class ReportTemplateVersionRecord(ReportTemplateVersionWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ReportTemplateSeedResult(FrozenReportContract):
    templates: tuple[ReportTemplateVersionRecord, ...]
    created_count: int = Field(ge=0, le=8)


class _TemplateRepository(Protocol):
    def get_template(
        self,
        name: str,
        version: str,
        locale: ReportLocale,
    ) -> ReportTemplateVersionRecord | None: ...

    def add_template(
        self,
        value: ReportTemplateVersionWrite,
    ) -> ReportTemplateVersionRecord: ...


class ReportTemplateError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReportTemplateResolver:
    def __init__(self, repository: _TemplateRepository) -> None:
        self._repository = repository

    def require(
        self,
        name: str,
        version: str,
        locale: ReportLocale,
    ) -> ReportTemplateVersionRecord:
        template = self._repository.get_template(name, version, locale)
        if template is None:
            raise ReportTemplateError("REPORT_TEMPLATE_NOT_FOUND")
        if template.status is not TemplateStatus.ACTIVE:
            raise ReportTemplateError("REPORT_TEMPLATE_NOT_PRODUCTION")
        if template.checksum != _template_checksum(template):
            raise ReportTemplateError("REPORT_TEMPLATE_CHECKSUM_MISMATCH")
        return template


class ReportTemplateSeedService:
    def __init__(self, repository: _TemplateRepository) -> None:
        self._repository = repository

    def seed_v1(self) -> ReportTemplateSeedResult:
        records: list[ReportTemplateVersionRecord] = []
        created_count = 0
        for expected in build_default_template_writes():
            existing = self._repository.get_template(
                expected.name,
                expected.version,
                expected.locale,
            )
            if existing is not None:
                if _semantic_template(existing) != _semantic_template(expected):
                    raise ReportTemplateError("REPORT_TEMPLATE_VERSION_CONFLICT")
                records.append(existing)
                continue
            records.append(self._repository.add_template(expected))
            created_count += 1
        return ReportTemplateSeedResult(
            templates=tuple(records),
            created_count=created_count,
        )


def build_default_template_writes() -> tuple[ReportTemplateVersionWrite, ...]:
    return tuple(
        _build_template(report_type, locale)
        for report_type in ReportType
        for locale in ReportLocale
    )


def _build_template(
    report_type: ReportType,
    locale: ReportLocale,
) -> ReportTemplateVersionWrite:
    name = report_type.value.casefold()
    sections = tuple(ReportSection)
    rules = tuple(
        TemplateSectionRule(
            section=section,
            required=section
            in {
                ReportSection.DATA_QUALITY,
                ReportSection.LIMITATIONS,
            },
            allow_empty_state=True,
        )
        for section in sections
    )
    patterns = (
        StatementPattern(
            statement_code="SECURITY_IDENTITY",
            tokens=(
                TemplateToken(literal="证券：" if locale is ReportLocale.ZH_CN else "Security: "),
                TemplateToken(placeholder=TemplatePlaceholder.OFFICIAL_SECURITY_NAME),
                TemplateToken(literal="（" if locale is ReportLocale.ZH_CN else " ("),
                TemplateToken(placeholder=TemplatePlaceholder.SYMBOL),
                TemplateToken(literal=" / "),
                TemplateToken(placeholder=TemplatePlaceholder.EXCHANGE),
                TemplateToken(literal="）" if locale is ReportLocale.ZH_CN else ")"),
            ),
        ),
        StatementPattern(
            statement_code="NUMERIC_CLAIM",
            tokens=(
                TemplateToken(placeholder=TemplatePlaceholder.CLAIM_VALUE),
                TemplateToken(literal=" "),
                TemplateToken(placeholder=TemplatePlaceholder.CLAIM_UNIT),
                TemplateToken(literal="，期间：" if locale is ReportLocale.ZH_CN else ", period: "),
                TemplateToken(placeholder=TemplatePlaceholder.CLAIM_PERIOD),
                TemplateToken(literal=" "),
                TemplateToken(placeholder=TemplatePlaceholder.VISIBLE_REFERENCE),
            ),
        ),
    ) + _fixed_disclosure_patterns(locale)
    table_columns = (
        TableColumnDescriptor(
            column_code="VALUE",
            label="数值" if locale is ReportLocale.ZH_CN else "Value",
            value_placeholder=TemplatePlaceholder.CLAIM_VALUE,
        ),
        TableColumnDescriptor(
            column_code="PERIOD",
            label="期间" if locale is ReportLocale.ZH_CN else "Period",
            value_placeholder=TemplatePlaceholder.CLAIM_PERIOD,
        ),
    )
    basis = {
        "name": name,
        "version": "1.0.0",
        "report_type": report_type,
        "locale": locale,
        "section_keys": sections,
        "section_rules": rules,
        "statement_patterns": patterns,
        "table_columns": table_columns,
        "citation_style": CitationStyle.BRACKETED_NUMERIC,
        "template_schema_version": "report-template-v1",
        "status": TemplateStatus.ACTIVE,
    }
    return ReportTemplateVersionWrite.model_validate({**basis, "checksum": report_checksum(basis)})


def _template_checksum(template: ReportTemplateVersionWrite) -> str:
    return report_checksum(
        template.model_dump(mode="python", exclude={"id", "created_at", "checksum"})
    )


def _fixed_disclosure_patterns(
    locale: ReportLocale,
) -> tuple[StatementPattern, ...]:
    localized = {
        ReportLocale.ZH_CN: (
            ("PARTIAL_QUALIFIER", "以下结果受数据可用性限制，仅反映已验证证据。"),
            ("BLOCKED_DISCLOSURE", "相关能力受阻，未使用缺失信息推断事实。"),
            ("NO_EVIDENCE_DISCLOSURE", "未发现可验证证据，未填补缺失内容。"),
            ("CONFLICT_DISCLOSURE", "证据存在冲突，未自动选择或合并数值。"),
        ),
        ReportLocale.EN_US: (
            (
                "PARTIAL_QUALIFIER",
                "The following results are limited by data availability "
                "and reflect verified evidence only.",
            ),
            (
                "BLOCKED_DISCLOSURE",
                "The capability is blocked; missing information was not used to infer facts.",
            ),
            (
                "NO_EVIDENCE_DISCLOSURE",
                "No verifiable evidence is available; missing content was not filled.",
            ),
            (
                "CONFLICT_DISCLOSURE",
                "Evidence conflicts are preserved; values were not selected "
                "or combined automatically.",
            ),
        ),
    }
    literals = localized[locale]
    return tuple(
        StatementPattern(
            statement_code=code,
            tokens=(TemplateToken(literal=literal),),
        )
        for code, literal in literals
    )


def _semantic_template(template: ReportTemplateVersionWrite) -> dict[str, object]:
    return template.model_dump(
        mode="python",
        exclude={"id", "created_at"},
    )


def _validate_literal(value: str) -> None:
    folded = value.casefold()
    forbidden = (
        "{",
        "}",
        "${",
        "__",
        "../",
        "\\",
        "://",
        "os.",
        "environ",
        "eval(",
        "exec(",
        "<script",
        "</",
        "select ",
        "insert ",
        "update ",
        "delete ",
        "drop ",
        "powershell",
        "cmd.exe",
        " env:",
    )
    if any(marker in folded for marker in forbidden):
        raise ValueError("template literal contains executable or external syntax")
