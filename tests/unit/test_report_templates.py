from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.reports.enums import ReportLocale, ReportType

NOW = datetime(2026, 7, 26, 13, tzinfo=UTC)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.templates")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 data-only report templates are missing")


class _Repository:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, object], object] = {}
        self.add_calls = 0

    def get_template(self, name: str, version: str, locale: object) -> object | None:
        return self.values.get((name, version, locale))

    def add_template(self, value: object) -> object:
        self.add_calls += 1
        record = _module().ReportTemplateVersionRecord.model_validate(
            {
                **value.model_dump(mode="python"),
                "id": uuid5(
                    NAMESPACE_URL,
                    f"{value.name}:{value.version}:{value.locale.value}",
                ),
                "created_at": NOW,
            }
        )
        self.values[(record.name, record.version, record.locale)] = record
        return record


def test_seed_creates_exact_eight_active_bilingual_templates_idempotently() -> None:
    module = _module()
    repository = _Repository()
    seeds = module.ReportTemplateSeedService(repository)

    first = seeds.seed_v1()
    second = seeds.seed_v1()

    assert len(first.templates) == len(ReportType) * len(ReportLocale) == 8
    assert first.created_count == 8
    assert second.created_count == 0
    assert repository.add_calls == 8
    assert {item.report_type for item in first.templates} == set(ReportType)
    assert {item.locale for item in first.templates} == set(ReportLocale)
    assert all(item.version == "1.0.0" for item in first.templates)
    assert all(item.template_schema_version == "report-template-v1" for item in first.templates)
    assert all(item.status.value == "ACTIVE" for item in first.templates)
    assert all(len(item.checksum) == 64 for item in first.templates)


def test_templates_use_only_literal_or_closed_placeholder_tokens() -> None:
    module = _module()
    templates = module.build_default_template_writes()

    assert templates
    for template in templates:
        assert template.section_keys
        assert tuple(rule.section for rule in template.section_rules) == template.section_keys
        assert template.statement_patterns
        for pattern in template.statement_patterns:
            assert pattern.tokens
            for token in pattern.tokens:
                assert (token.literal is None) != (token.placeholder is None)


def test_resolver_requires_exact_active_version_and_rejects_test_only() -> None:
    module = _module()
    repository = _Repository()
    module.ReportTemplateSeedService(repository).seed_v1()
    resolver = module.ReportTemplateResolver(repository)
    expected = next(iter(repository.values.values()))

    assert resolver.require(expected.name, expected.version, expected.locale) == expected
    with pytest.raises(module.ReportTemplateError) as raised:
        resolver.require(expected.name, "latest", expected.locale)
    assert raised.value.code == "REPORT_TEMPLATE_NOT_FOUND"

    test_only = expected.model_copy(update={"status": module.TemplateStatus.TEST_ONLY})
    repository.values[(expected.name, expected.version, expected.locale)] = test_only
    with pytest.raises(module.ReportTemplateError) as raised:
        resolver.require(expected.name, expected.version, expected.locale)
    assert raised.value.code == "REPORT_TEMPLATE_NOT_PRODUCTION"


@pytest.mark.parametrize(
    "literal",
    [
        "{{ claim.value }}",
        "{claim.value}",
        "{% include 'x' %}",
        "${ENV_SECRET}",
        "__class__",
        "../template",
        "C:\\template",
        "https://example.com/template",
        "os.environ",
        "eval(value)",
    ],
)
def test_literal_token_rejects_executable_path_environment_and_network_syntax(
    literal: str,
) -> None:
    module = _module()

    with pytest.raises(ValidationError):
        module.TemplateToken.model_validate({"literal": literal})


def test_unknown_placeholder_and_mixed_token_shape_are_rejected() -> None:
    module = _module()

    with pytest.raises(ValidationError):
        module.TemplateToken.model_validate({"placeholder": "CLAIM.__dict__"})
    with pytest.raises(ValidationError):
        module.TemplateToken.model_validate(
            {
                "literal": "value",
                "placeholder": module.TemplatePlaceholder.CLAIM_VALUE,
            }
        )


def test_template_checksum_is_recomputed_and_conflicts_are_not_overwritten() -> None:
    module = _module()
    repository = _Repository()
    seeds = module.ReportTemplateSeedService(repository)
    first = seeds.seed_v1()
    template = first.templates[0]
    repository.values[(template.name, template.version, template.locale)] = template.model_copy(
        update={"checksum": "f" * 64}
    )

    with pytest.raises(module.ReportTemplateError) as raised:
        seeds.seed_v1()

    assert raised.value.code == "REPORT_TEMPLATE_VERSION_CONFLICT"


def test_template_records_are_frozen() -> None:
    module = _module()
    repository = _Repository()
    record = module.ReportTemplateSeedService(repository).seed_v1().templates[0]

    with pytest.raises(ValidationError, match="Instance is frozen"):
        record.name = "replaced"


def test_template_persistence_has_named_uniqueness_status_and_checksum_guards() -> None:
    models = import_module("stock_research_agent.db.models.reports")
    try:
        table = models.ReportTemplateVersion.__table__
    except AttributeError:
        pytest.fail("Stage 8 report template persistence model is missing")

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "version",
        "report_type",
        "locale",
        "template_schema_version",
        "status",
        "checksum",
        "definition",
        "created_at",
    }
    assert {
        "uq_report_template_versions_identity",
        "ck_report_template_versions_status",
        "ck_report_template_versions_checksum",
    }.issubset({item.name for item in table.constraints})
