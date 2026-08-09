from __future__ import annotations

from collections.abc import Callable

import pytest

from stock_research_agent.domain.securities.exceptions import InvalidSecurityQuery
from stock_research_agent.domain.securities.normalization import (
    normalize_company_name,
    normalize_exchange_alias,
    normalize_external_identifier,
    normalize_free_text,
    normalize_symbol,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Micron   Technology  ", "MICRON TECHNOLOGY"),
        ("Ｍｉｃｒｏｎ　Ｔｅｃｈｎｏｌｏｇｙ", "MICRON TECHNOLOGY"),
        ("工业富联", "工业富联"),
        ("６０１１３８", "601138"),
    ],
)
def test_normalize_free_text_is_stable(value: str, expected: str) -> None:
    assert normalize_free_text(value) == expected
    assert normalize_free_text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" ６０１１３８．ｓｈ ", "601138.SH"),
        ("NASDAQ：ｍｕ", "NASDAQ:MU"),
        ("  M U  ", "MU"),
        ("brk.b", "BRK.B"),
    ],
)
def test_normalize_symbol_handles_supported_separators(value: str, expected: str) -> None:
    assert normalize_symbol(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (".SH", "SH"),
        (" sh ", "SH"),
        ("ＮＡＳＤＡＱ", "NASDAQ"),
        ("X N A S", "XNAS"),
    ],
)
def test_normalize_exchange_alias_accepts_only_authorized_forms(value: str, expected: str) -> None:
    assert normalize_exchange_alias(value) == expected


@pytest.mark.parametrize("value", ["$NASDAQ", "NAS%DAQ", "..SH", "SH:", "."])
def test_normalize_exchange_alias_rejects_disallowed_punctuation(value: str) -> None:
    with pytest.raises(InvalidSecurityQuery):
        normalize_exchange_alias(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" Micron Technology, Inc. ", "MICRON TECHNOLOGY INC"),
        ("富士康工业互联网股份有限公司", "富士康工业互联网股份有限公司"),
        ("工业富联，股份有限公司", "工业富联 股份有限公司"),
    ],
)
def test_normalize_company_name_preserves_meaningful_characters(value: str, expected: str) -> None:
    assert normalize_company_name(value) == expected


def test_normalize_external_identifier_supports_confirmed_cik_only() -> None:
    assert normalize_external_identifier("sec_cik", "723125") == "0000723125"
    assert normalize_external_identifier("SEC_CIK", "００００７２３１２５") == "0000723125"

    with pytest.raises(InvalidSecurityQuery):
        normalize_external_identifier("CUSIP", "595112103")


@pytest.mark.parametrize(
    "normalizer",
    [
        normalize_free_text,
        normalize_symbol,
        normalize_exchange_alias,
        normalize_company_name,
    ],
)
@pytest.mark.parametrize("value", ["", "   ", "...", "，。", "abc\nvalue", "abc\u200bvalue"])
def test_normalizers_reject_empty_punctuation_and_control_input(
    normalizer: Callable[[str], str], value: str
) -> None:
    with pytest.raises(InvalidSecurityQuery):
        normalizer(value)


@pytest.mark.parametrize(
    "normalizer",
    [
        normalize_free_text,
        normalize_symbol,
        normalize_exchange_alias,
        normalize_company_name,
    ],
)
def test_normalizers_reject_raw_or_nfkc_expanded_overlength(
    normalizer: Callable[[str], str],
) -> None:
    with pytest.raises(InvalidSecurityQuery):
        normalizer("A" * 257)

    # U+FDFA expands to an 18-character Arabic phrase under NFKC.
    with pytest.raises(InvalidSecurityQuery):
        normalizer("A" * 250 + "\ufdfa")


def test_normalization_does_not_modify_the_original_string() -> None:
    original = "  Micron Technology, Inc.  "
    snapshot = original[:]

    assert normalize_company_name(original) == "MICRON TECHNOLOGY INC"
    assert original == snapshot
