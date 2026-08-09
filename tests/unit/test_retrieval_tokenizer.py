from __future__ import annotations

import pytest

from stock_research_agent.domain.retrieval.tokenizer import VersionedTokenizer


def _values(text: str, *, query: bool = True) -> tuple[str, ...]:
    return tuple(token.value for token in VersionedTokenizer().tokenize(text, query=query))


def test_tokenizer_nfkc_casefold_and_preserves_financial_mixed_tokens() -> None:
    assert _values("ＭＵ NASDAQ:MU ６０１１３８.SH 10-K 12.5% RMB USD") == (
        "mu",
        "nasdaq:mu",
        "601138.sh",
        "10-k",
        "12.5%",
        "rmb",
        "usd",
    )


def test_tokenizer_emits_bounded_cjk_whole_run_and_overlapping_bigrams() -> None:
    assert _values("工业富联 风险") == ("工业富联", "工业", "业富", "富联", "风险", "风险")
    assert _values("不") == ("不",)


def test_tokenizer_uses_minimal_stopwords_but_preserves_negations() -> None:
    assert _values("The company is not without risk and no assurance") == (
        "company",
        "is",
        "not",
        "without",
        "risk",
        "no",
        "assurance",
    )


def test_tokenizer_rejects_controls_empty_query_and_query_limits() -> None:
    tokenizer = VersionedTokenizer()
    with pytest.raises(ValueError, match="control"):
        tokenizer.tokenize("safe\x00unsafe", query=True)
    with pytest.raises(ValueError, match="empty"):
        tokenizer.tokenize("...", query=True)
    with pytest.raises(ValueError, match="256"):
        tokenizer.tokenize("x" * 257, query=True)
    with pytest.raises(ValueError, match="64"):
        tokenizer.tokenize(" ".join(f"x{i}" for i in range(65)), query=True)


def test_document_tokenization_is_stable_and_not_query_length_limited() -> None:
    tokenizer = VersionedTokenizer()
    text = " ".join(["evidence"] * 70)
    first = tokenizer.tokenize(text, query=False)
    second = tokenizer.tokenize(text, query=False)
    assert first == second
    assert len(first) == 70
