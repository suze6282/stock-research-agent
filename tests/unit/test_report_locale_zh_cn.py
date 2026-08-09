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
    TemplatePlaceholder,
    build_default_template_writes,
)

GOLDEN_PATH = Path(__file__).parents[1] / "golden" / "report_templates_zh_cn.json"


def _golden() -> dict[str, object]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _zh_templates() -> tuple[object, ...]:
    return tuple(
        template
        for template in build_default_template_writes()
        if template.locale is ReportLocale.ZH_CN
    )


def _literal_pattern(template: object, code: str) -> str:
    pattern = next(item for item in template.statement_patterns if item.statement_code == code)
    assert all(token.placeholder is None for token in pattern.tokens)
    return "".join(token.literal or "" for token in pattern.tokens)


def test_zh_cn_golden_covers_all_types_sections_and_fixed_titles() -> None:
    golden = _golden()
    templates = _zh_templates()

    assert len(templates) == len(ReportType) == 4
    assert golden["locale"] == ReportLocale.ZH_CN.value
    assert golden["section_order"] == [section.value for section in ReportSection]
    for template in templates:
        assert list(item.value for item in template.section_keys) == golden["section_order"]
        sections = build_sections(
            template,
            ReportInputManifest.model_construct(
                section_states=(),
                blocked_capabilities=(),
                warnings=(),
            ),
        )
        assert [section.title for section in sections] == golden["section_titles"]


def test_zh_cn_disclosures_match_independent_golden_literals() -> None:
    golden = _golden()
    disclosures = golden["fixed_disclosures"]

    for template in _zh_templates():
        for code, expected in disclosures.items():
            assert _literal_pattern(template, code) == expected


def test_zh_cn_templates_keep_data_quality_and_limitations_mandatory() -> None:
    for template in _zh_templates():
        rules = {rule.section: rule for rule in template.section_rules}
        assert rules[ReportSection.DATA_QUALITY].required is True
        assert rules[ReportSection.LIMITATIONS].required is True
        assert all(rule.allow_empty_state for rule in rules.values())
        numeric = next(
            item for item in template.statement_patterns if item.statement_code == "NUMERIC_CLAIM"
        )
        placeholders = tuple(
            token.placeholder for token in numeric.tokens if token.placeholder is not None
        )
        assert placeholders == (
            TemplatePlaceholder.CLAIM_VALUE,
            TemplatePlaceholder.CLAIM_UNIT,
            TemplatePlaceholder.CLAIM_PERIOD,
            TemplatePlaceholder.VISIBLE_REFERENCE,
        )


def test_zh_cn_templates_contain_no_advice_or_promotional_language() -> None:
    forbidden = (
        "买入",
        "卖出",
        "目标价",
        "仓位",
        "强烈推荐",
        "必然上涨",
        "确定收益",
    )
    for template in _zh_templates():
        literals = "".join(
            token.literal or ""
            for pattern in template.statement_patterns
            for token in pattern.tokens
        )
        assert not any(term in literals for term in forbidden)
