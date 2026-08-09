"""Deterministic lexical postings and Decimal BM25."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from uuid import NAMESPACE_URL, UUID, uuid5

from stock_research_agent.domain.retrieval.enums import IndexStatus
from stock_research_agent.domain.retrieval.schemas import (
    Bm25Stats,
    IndexableChunk,
    LexicalBuildRequest,
    LexicalHit,
    LexicalIndexResult,
    LexicalPostingDraft,
    LexicalSearchRequest,
)
from stock_research_agent.domain.retrieval.tokenizer import VersionedTokenizer

_QUANTUM = Decimal("0.000000000001")
_K1 = Decimal("1.2")
_B = Decimal("0.75")


class LexicalIndexService:
    def __init__(self, chunks: Iterable[IndexableChunk]) -> None:
        self._chunks = tuple(chunks)
        self._cache: dict[str, LexicalIndexResult] = {}
        self._tokenizer = VersionedTokenizer()

    def build(self, request: LexicalBuildRequest) -> LexicalIndexResult:
        eligible = tuple(
            sorted(
                (chunk for chunk in self._chunks if _eligible(chunk, request)),
                key=lambda chunk: (
                    str(chunk.document_version_id),
                    chunk.chunk_index,
                    str(chunk.chunk_id),
                ),
            )
        )
        document_set = tuple(
            sorted(
                {(str(chunk.document_version_id), chunk.document_checksum) for chunk in eligible}
            )
        )
        document_set_checksum = hashlib.sha256(
            json.dumps(document_set, separators=(",", ":")).encode()
        ).hexdigest()
        fingerprint_payload = {
            "request": request.model_dump(mode="json"),
            "document_set_checksum": document_set_checksum,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        cached = self._cache.get(fingerprint)
        if cached is not None:
            return cached.model_copy(update={"reused": True})

        postings: list[LexicalPostingDraft] = []
        lengths: list[int] = []
        for chunk in eligible:
            tokens = self._tokenizer.tokenize(chunk.text, query=False)
            lengths.append(len(tokens))
            positions: dict[str, list[int]] = defaultdict(list)
            for token in tokens:
                positions[token.value].append(token.position)
            counts = Counter(token.value for token in tokens)
            postings.extend(
                LexicalPostingDraft(
                    token=token,
                    chunk_id=chunk.chunk_id,
                    term_frequency=count,
                    field_kind="BODY",
                    positions=tuple(positions[token]),
                )
                for token, count in sorted(counts.items())
            )
        average = (
            (Decimal(sum(lengths)) / Decimal(len(lengths))).quantize(_QUANTUM)
            if lengths
            else Decimal("0")
        )
        result = LexicalIndexResult(
            status=IndexStatus.COMPLETE,
            index_version_id=uuid5(NAMESPACE_URL, fingerprint),
            document_set_checksum=document_set_checksum,
            document_count=len(document_set),
            chunk_count=len(eligible),
            average_chunk_length=average,
            postings=tuple(postings),
        )
        self._cache[fingerprint] = result
        return result


class LexicalSearchService:
    """Search one immutable in-memory index generation without fuzzy matching."""

    def __init__(
        self,
        chunks: Iterable[IndexableChunk],
        index: LexicalIndexResult,
        *,
        citation_ids: Mapping[UUID, UUID] | None = None,
    ) -> None:
        self._chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self._index = index
        self._citation_ids: dict[UUID, UUID] = {
            chunk_id: citation_id for chunk_id, citation_id in (citation_ids or {}).items()
        }
        self._tokenizer = VersionedTokenizer()

    def search(self, request: LexicalSearchRequest) -> tuple[LexicalHit, ...]:
        if request.index_version_id != self._index.index_version_id:
            return ()
        query_values = tuple(token.value for token in request.tokenized_query.tokens)
        postings_by_chunk: dict[object, list[LexicalPostingDraft]] = defaultdict(list)
        for posting in self._index.postings:
            if posting.token not in query_values:
                continue
            postings_by_chunk[posting.chunk_id].append(posting)
        if not postings_by_chunk:
            return ()

        eligible_chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk_id in postings_by_chunk
            and chunk_id in self._citation_ids
            and _matches_filters(chunk, request)
        }
        if not eligible_chunks:
            return ()
        document_frequency: Counter[str] = Counter()
        for chunk_id in eligible_chunks:
            document_frequency.update({posting.token for posting in postings_by_chunk[chunk_id]})
        lengths = {
            chunk_id: len(self._tokenizer.tokenize(chunk.text, query=False))
            for chunk_id, chunk in eligible_chunks.items()
        }
        average = Decimal(sum(lengths.values())) / Decimal(len(lengths))
        drafts: list[tuple[IndexableChunk, Decimal, bool, int]] = []
        for chunk_id, chunk in eligible_chunks.items():
            body_tokens = tuple(
                token.value for token in self._tokenizer.tokenize(chunk.text, query=False)
            )
            score = sum(
                (
                    bm25_score(
                        Bm25Stats(
                            term_frequency=posting.term_frequency,
                            document_frequency=document_frequency[posting.token],
                            document_count=len(eligible_chunks),
                            document_length=lengths[chunk_id],
                            average_document_length=average,
                        )
                    )
                    for posting in postings_by_chunk[chunk_id]
                ),
                Decimal("0"),
            ).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
            heading_tokens = (
                set(
                    token.value
                    for token in self._tokenizer.tokenize(chunk.section_title, query=False)
                )
                if chunk.section_title
                else set()
            )
            drafts.append(
                (
                    chunk,
                    score,
                    _contains_sequence(body_tokens, query_values),
                    sum(1 for value in query_values if value in heading_tokens),
                )
            )
        drafts.sort(key=lambda item: (-item[1], item[0].locator_checksum, item[0].chunk_index))
        return tuple(
            LexicalHit(
                chunk_id=chunk.chunk_id,
                document_version_id=chunk.document_version_id,
                citation_id=self._citation_ids[chunk.chunk_id],
                chunk_index=chunk.chunk_index,
                locator_checksum=chunk.locator_checksum,
                text=chunk.text,
                section_title=chunk.section_title,
                score=score,
                rank=rank,
                phrase_match=phrase_match,
                heading_token_matches=heading_matches,
            )
            for rank, (chunk, score, phrase_match, heading_matches) in enumerate(
                drafts[: request.max_results], start=1
            )
        )


def bm25_score(stats: Bm25Stats) -> Decimal:
    if stats.term_frequency == 0:
        return Decimal("0").quantize(_QUANTUM)
    with localcontext() as context:
        context.prec = 50
        tf = Decimal(stats.term_frequency)
        df = Decimal(stats.document_frequency)
        count = Decimal(stats.document_count)
        length = Decimal(stats.document_length)
        average = stats.average_document_length
        inverse_document_frequency = (
            Decimal(1) + (count - df + Decimal("0.5")) / (df + Decimal("0.5"))
        ).ln()
        denominator = tf + _K1 * (Decimal(1) - _B + _B * length / average)
        score = inverse_document_frequency * (tf * (_K1 + Decimal(1))) / denominator
        return score.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _eligible(chunk: IndexableChunk, request: LexicalBuildRequest) -> bool:
    if chunk.security_id != request.security_id:
        return False
    if request.snapshot_id is not None:
        return request.snapshot_id in chunk.snapshot_ids
    if request.index_as_of_time is None or chunk.published_at is None:
        return False
    if chunk.published_at > request.index_as_of_time or chunk.supersession_time_unknown:
        return False
    return chunk.superseded_at is None or chunk.superseded_at > request.index_as_of_time


def _matches_filters(chunk: IndexableChunk, request: LexicalSearchRequest) -> bool:
    filters = request.filters
    if chunk.security_id != filters.security_id:
        return False
    if filters.snapshot_id is not None and filters.snapshot_id not in chunk.snapshot_ids:
        return False
    if filters.research_as_of_time is not None:
        if chunk.published_at is None and filters.strict_unknown_publication:
            return False
        if chunk.published_at is not None and chunk.published_at > filters.research_as_of_time:
            return False
        if chunk.supersession_time_unknown:
            return False
        if chunk.superseded_at is not None and chunk.superseded_at <= filters.research_as_of_time:
            return False
    if filters.document_types and chunk.document_type not in filters.document_types:
        return False
    if filters.languages and chunk.language not in filters.languages:
        return False
    return not filters.trust_levels or chunk.trust_level in filters.trust_levels


def _contains_sequence(values: tuple[str, ...], query: tuple[str, ...]) -> bool:
    if not query or len(query) > len(values):
        return False
    return any(values[index : index + len(query)] == query for index in range(len(values)))
