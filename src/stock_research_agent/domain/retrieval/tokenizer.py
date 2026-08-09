"""Versioned deterministic Chinese/English lexical tokenizer."""

from __future__ import annotations

import re
import unicodedata

from stock_research_agent.domain.retrieval.schemas import LexicalToken, TokenizedQuery

TOKENIZER_VERSION = "tokenizer-v1"
_STOPWORDS = frozenset({"a", "an", "and", "for", "in", "of", "the", "to"})
_SEGMENT = re.compile(r"[\u3400-\u9fff]+|(?:[A-Za-z]+:)?[A-Za-z0-9]+(?:[.%-][A-Za-z0-9]+)*%?")


class VersionedTokenizer:
    version = TOKENIZER_VERSION

    def tokenize_query(self, value: str) -> TokenizedQuery:
        normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        return TokenizedQuery(
            original_query=value,
            normalized_query=normalized,
            tokens=self.tokenize(value, query=True),
        )

    def tokenize(self, value: str, *, query: bool) -> tuple[LexicalToken, ...]:
        if not isinstance(value, str):
            raise ValueError("tokenizer input must be text")
        if any(
            unicodedata.category(character) == "Cc" and character not in "\n\t"
            for character in value
        ):
            raise ValueError("unsafe control character in tokenizer input")
        normalized = unicodedata.normalize("NFKC", value).casefold().strip()
        if query and len(normalized) > 256:
            raise ValueError("query exceeds 256 characters")
        values: list[str] = []
        for match in _SEGMENT.finditer(normalized):
            segment = match.group(0)
            if _is_cjk(segment):
                if len(segment) == 1:
                    values.append(segment)
                else:
                    if len(segment) <= 32:
                        values.append(segment)
                    values.extend(segment[index : index + 2] for index in range(len(segment) - 1))
            elif segment not in _STOPWORDS:
                values.append(segment)
        if query and not values:
            raise ValueError("tokenized query is empty")
        if query and len(values) > 64:
            raise ValueError("tokenized query exceeds 64 tokens")
        return tuple(
            LexicalToken(value=token, position=index) for index, token in enumerate(values)
        )


def _is_cjk(value: str) -> bool:
    return bool(value) and all("\u3400" <= character <= "\u9fff" for character in value)
