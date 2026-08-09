from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "document-versions.md",
    "document-parsing.md",
    "document-chunking.md",
    "rag-lexical-retrieval.md",
    "rag-vector-interface.md",
    "rag-hybrid-retrieval.md",
    "citations.md",
    "evidence-bundles.md",
    "prompt-injection-defense.md",
)


def test_stage6_topic_documents_exist_without_placeholder_text() -> None:
    for name in FILES:
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert len(text) >= 300
        assert not any(marker in text for marker in ("TBD", "TODO", "FIXME"))


def test_stage6_docs_state_honest_company_vector_and_cache_boundaries() -> None:
    corpus = "\n".join((ROOT / "docs" / name).read_text(encoding="utf-8") for name in FILES)
    for phrase in (
        "RETRIEVAL_RUN_NOT_PRECOMPUTED",
        "VECTOR: BLOCKED",
        "HYBRID: PARTIAL",
        "工业富联真实正文验收：BLOCKED",
        "美光科技真实正文验收：BLOCKED",
        "SYNTHETIC_TEST_ONLY",
        "NOT_COMPANY_EVIDENCE",
        "不调用大模型",
        "不得隐式刷新",
    ):
        assert phrase in corpus
