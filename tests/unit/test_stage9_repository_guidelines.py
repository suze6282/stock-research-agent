from pathlib import Path

ROOT = Path(__file__).parents[2]
GUIDELINES = ROOT / "AGENTS.md"


def test_repository_guidelines_preserve_stage9_scope_without_claiming_stage10_unstarted() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")
    historical = text.partition("### Stage 9")[2]

    for required in (
        "stage-9/production-data-providers",
        "stage-9-production-data-provider-design.md",
        "stage-9-production-data-providers.md",
        "Definition → Capability → License → Provider Policy",
        "Credential Reference → Configuration Validation",
        "Live Authorization → Network",
        "批准执行该Provider的有限Live验证",
        "不得进入第10阶段",
    ):
        assert required in historical

    assert "Stage 10: Started / Work in Progress / Development Paused" in text
    assert "These are historical design constraints" in historical


def test_repository_guidelines_preserve_offline_and_read_only_boundaries() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")

    for required in (
        "OFFLINE",
        "NOT_LIVE",
        "NOT_ATTEMPTED",
        "READ_ONLY",
        "writes=false",
        "requires_network=false",
        "不得读取真实Provider凭证",
        "不得创建Snapshot",
        "不得运行Agent",
        "不得生成Report",
        "PostgreSQL",
    ):
        assert required in text
