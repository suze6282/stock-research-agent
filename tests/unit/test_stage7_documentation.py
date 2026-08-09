from pathlib import Path

ROOT = Path(__file__).parents[2]
DOCUMENTS = (
    "docs/research-agent-architecture.md",
    "docs/research-agent-policy.md",
    "docs/research-agent-state-machine.md",
    "docs/research-planning.md",
    "docs/research-tool-execution.md",
    "docs/research-evidence-ledger.md",
    "docs/research-claims.md",
    "docs/research-packages.md",
    "docs/research-agent-security.md",
    "docs/tool-contracts.md",
    "docs/api.md",
    "docs/database.md",
    "docs/testing.md",
    "docs/security-boundaries.md",
    "docs/risk-register.md",
    "docs/open-questions.md",
    "README.md",
)


def test_stage7_documentation_set_exists_and_records_controlled_boundaries() -> None:
    missing = [path for path in DOCUMENTS if not (ROOT / path).is_file()]
    assert missing == []

    corpus = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in DOCUMENTS)
    for required in (
        "DeterministicTemplatePlanner",
        "DeterministicClaimBuilder",
        "controlled-offline-v1",
        "tool_catalog_version",
        "model_token_budget=0",
        "READ_ONLY",
        "requires_network=false",
        "research_as_of_time",
        "SYNTHETIC_TEST_ONLY",
        "PARTIAL",
        "BLOCKED",
        "601138.SH",
        "MU",
        "Evidence",
        "Claim",
        "CONFLICTING",
        "GET",
        "CLI",
        "0006_controlled_research_agent",
    ):
        assert required in corpus


def test_stage7_docs_state_prohibited_capabilities_and_honest_sample_limits() -> None:
    corpus = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in DOCUMENTS)
    for prohibited in (
        "no investment recommendation",
        "no target price",
        "no automatic trading",
        "no MCP Server",
        "no production model provider",
        "no implicit network refresh",
    ):
        assert prohibited in corpus
    assert "Industrial FII verified company body: BLOCKED" in corpus
    assert "Micron verified company body: BLOCKED" in corpus
    assert "CONDITIONAL GO" in corpus
