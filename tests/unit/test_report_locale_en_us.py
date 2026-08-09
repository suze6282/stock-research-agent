from __future__ import annotations

import json
from pathlib import Path

from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.schemas import ReportInputManifest
from stock_research_agent.domain.reports.sections import build_sections
from stock_research_agent.domain.reports.templates import (
    build_default_template_writes,
)

GOLDEN_PATH = Path(__file__).parents[1] / "golden" / "report_templates_en_us.json"


def _golden() -> dict[str, object]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _templates(locale: ReportLocale) -> tuple[object, ...]:
    return tuple(
        template for template in build_default_template_writes() if template.locale is locale
    )


def _literal_pattern(template: object, code: str) -> str:
    pattern = next(item for item in template.statement_patterns if item.statement_code == code)
    assert all(token.placeholder is None for token in pattern.tokens)
    return "".join(token.literal or "" for token in pattern.tokens)


def _semantic_pattern_shape(template: object) -> dict[str, tuple[str, ...]]:
    return {
        pattern.statement_code: tuple(
            (
                f"PLACEHOLDER:{token.placeholder.value}"
                if token.placeholder is not None
                else "LITERAL"
            )
            for token in pattern.tokens
        )
        for pattern in template.statement_patterns
    }


def test_en_us_golden_covers_all_types_sections_and_fixed_titles() -> None:
    golden = _golden()
    templates = _templates(ReportLocale.EN_US)

    assert len(templates) == len(ReportType) == 4
    assert golden["locale"] == ReportLocale.EN_US.value
    assert golden["section_order"] == [section.value for section in ReportSection]
    for template in templates:
        assert [section.value for section in template.section_keys] == golden["section_order"]
        sections = build_sections(
            template,
            ReportInputManifest.model_construct(
                section_states=(),
                blocked_capabilities=(),
                warnings=(),
            ),
        )
        assert [section.title for section in sections] == golden["section_titles"]


def test_en_us_disclosures_match_independent_golden_literals() -> None:
    disclosures = _golden()["fixed_disclosures"]

    for template in _templates(ReportLocale.EN_US):
        for code, expected in disclosures.items():
            assert _literal_pattern(template, code) == expected


def test_en_us_and_zh_cn_templates_have_semantic_parity() -> None:
    zh_by_type = {template.report_type: template for template in _templates(ReportLocale.ZH_CN)}
    for template in _templates(ReportLocale.EN_US):
        zh = zh_by_type[template.report_type]
        assert template.section_keys == zh.section_keys
        assert tuple(
            (rule.section, rule.required, rule.allow_empty_state) for rule in template.section_rules
        ) == tuple(
            (rule.section, rule.required, rule.allow_empty_state) for rule in zh.section_rules
        )
        assert _semantic_pattern_shape(template) == _semantic_pattern_shape(zh)
        assert tuple(column.column_code for column in template.table_columns) == tuple(
            column.column_code for column in zh.table_columns
        )


def test_en_us_templates_preserve_exact_source_fields_without_translation_claim() -> None:
    forbidden = (
        "translated by",
        "machine translation",
        "buy",
        "sell",
        "target price",
        "position size",
        "guaranteed return",
    )
    for template in _templates(ReportLocale.EN_US):
        literals = "".join(
            token.literal or ""
            for pattern in template.statement_patterns
            for token in pattern.tokens
        )
        assert not any(term in literals.casefold() for term in forbidden)
        identity = next(
            pattern
            for pattern in template.statement_patterns
            if pattern.statement_code == "SECURITY_IDENTITY"
        )
        placeholders = {
            token.placeholder.value for token in identity.tokens if token.placeholder is not None
        }
        assert placeholders == {
            "OFFICIAL_SECURITY_NAME",
            "SYMBOL",
            "EXCHANGE",
        }
