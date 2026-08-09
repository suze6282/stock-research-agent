from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from stock_research_agent.domain.documents.enums import DocumentLanguage, TrustLevel
from stock_research_agent.domain.retrieval.enums import IndexStatus
from stock_research_agent.domain.retrieval.lexical import LexicalIndexService, LexicalSearchService
from stock_research_agent.domain.retrieval.schemas import (
    IndexableChunk,
    LexicalBuildRequest,
    LexicalSearchRequest,
    RetrievalFilters,
)
from stock_research_agent.domain.retrieval.tokenizer import VersionedTokenizer

SECURITY_ID = UUID("00000000-0000-0000-0000-000000000051")
NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _chunk(
    number: int,
    text: str,
    published_at: datetime | None,
    *,
    superseded_at: datetime | None = None,
    supersession_time_unknown: bool = False,
) -> IndexableChunk:
    return IndexableChunk(
        chunk_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        document_version_id=UUID(f"10000000-0000-0000-0000-{number:012d}"),
        document_checksum=f"{number:064x}",
        security_id=SECURITY_ID,
        published_at=published_at,
        snapshot_ids=(),
        chunk_index=number,
        locator_checksum=f"{number + 10:064x}",
        text=text,
        section_title=None,
        document_type="SEC_10_K",
        language=DocumentLanguage.EN_US,
        trust_level=TrustLevel.OFFICIAL_REGULATORY,
        superseded_at=superseded_at,
        supersession_time_unknown=supersession_time_unknown,
    )


def test_as_of_index_excludes_future_and_unknown_publication_and_builds_postings() -> None:
    service = LexicalIndexService(
        (
            _chunk(1, "risk risk revenue", NOW - timedelta(days=1)),
            _chunk(2, "future evidence", NOW + timedelta(days=1)),
            _chunk(3, "unknown evidence", None),
        )
    )
    request = LexicalBuildRequest(
        index_name="mu-as-of",
        security_id=SECURITY_ID,
        index_as_of_time=NOW,
    )

    result = service.build(request)

    assert result.status == IndexStatus.COMPLETE
    assert result.document_count == 1
    assert result.chunk_count == 1
    risk = next(posting for posting in result.postings if posting.token == "risk")
    assert risk.term_frequency == 2
    assert risk.positions == (0, 1)


def test_lexical_build_is_stable_and_reuses_identical_fingerprint() -> None:
    service = LexicalIndexService((_chunk(1, "stable evidence", NOW),))
    request = LexicalBuildRequest(
        index_name="stable",
        security_id=SECURITY_ID,
        index_as_of_time=NOW,
    )

    first = service.build(request)
    second = service.build(request)

    assert first.index_version_id == second.index_version_id
    assert first.document_set_checksum == second.document_set_checksum
    assert second.reused is True


def test_as_of_index_excludes_versions_superseded_by_the_cutoff() -> None:
    service = LexicalIndexService(
        (
            _chunk(1, "old revision", NOW - timedelta(days=3), superseded_at=NOW),
            _chunk(
                2,
                "current revision",
                NOW - timedelta(days=2),
                superseded_at=NOW + timedelta(days=1),
            ),
            _chunk(
                3,
                "unknown supersession",
                NOW - timedelta(days=2),
                supersession_time_unknown=True,
            ),
        )
    )

    result = service.build(
        LexicalBuildRequest(
            index_name="supersession-as-of",
            security_id=SECURITY_ID,
            index_as_of_time=NOW,
        )
    )

    assert result.document_count == 1
    assert result.chunk_count == 1
    assert {posting.chunk_id for posting in result.postings} == {_chunk(2, "x", NOW).chunk_id}


def test_lexical_search_scores_exact_tokens_and_uses_stable_ties() -> None:
    chunks = (
        _chunk(1, "risk risk revenue", NOW),
        _chunk(2, "risk outlook", NOW),
        _chunk(3, "unrelated", NOW),
    )
    index = LexicalIndexService(chunks).build(
        LexicalBuildRequest(index_name="search", security_id=SECURITY_ID, index_as_of_time=NOW)
    )
    assert index.index_version_id is not None
    service = LexicalSearchService(
        chunks,
        index,
        citation_ids={
            chunk.chunk_id: UUID(f"20000000-0000-0000-0000-{index:012d}")
            for index, chunk in enumerate(chunks, start=1)
        },
    )

    hits = service.search(
        LexicalSearchRequest(
            index_version_id=index.index_version_id,
            tokenized_query=VersionedTokenizer().tokenize_query("risk revenue"),
            filters=RetrievalFilters(security_id=SECURITY_ID, research_as_of_time=NOW),
            max_results=10,
        )
    )

    assert [hit.chunk_id for hit in hits] == [chunks[0].chunk_id, chunks[1].chunk_id]
    assert hits[0].rank == 1
    assert hits[0].phrase_match is True
    assert hits[0].citation_id is not None
    assert all(hit.score > 0 for hit in hits)


def test_lexical_search_rejects_wrong_index_and_bounds_results() -> None:
    chunks = tuple(_chunk(number, "risk", NOW) for number in range(1, 15))
    index = LexicalIndexService(chunks).build(
        LexicalBuildRequest(index_name="bounded", security_id=SECURITY_ID, index_as_of_time=NOW)
    )
    service = LexicalSearchService(
        chunks,
        index,
        citation_ids={
            chunk.chunk_id: UUID(f"20000000-0000-0000-0000-{number:012d}")
            for number, chunk in enumerate(chunks, start=1)
        },
    )
    request = LexicalSearchRequest(
        index_version_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        tokenized_query=VersionedTokenizer().tokenize_query("risk"),
        filters=RetrievalFilters(security_id=SECURITY_ID, research_as_of_time=NOW),
        max_results=10,
    )

    assert service.search(request) == ()
    assert (
        len(service.search(request.model_copy(update={"index_version_id": index.index_version_id})))
        == 10
    )


def test_lexical_search_applies_filters_before_document_frequency() -> None:
    english = _chunk(1, "risk disclosure", NOW)
    chinese = _chunk(2, "risk disclosure", NOW).model_copy(
        update={"language": DocumentLanguage.ZH_CN}
    )
    chunks = (english, chinese)
    index = LexicalIndexService(chunks).build(
        LexicalBuildRequest(index_name="filtered", security_id=SECURITY_ID, index_as_of_time=NOW)
    )
    assert index.index_version_id is not None

    hits = LexicalSearchService(
        chunks,
        index,
        citation_ids={
            english.chunk_id: UUID("20000000-0000-0000-0000-000000000001"),
            chinese.chunk_id: UUID("20000000-0000-0000-0000-000000000002"),
        },
    ).search(
        LexicalSearchRequest(
            index_version_id=index.index_version_id,
            tokenized_query=VersionedTokenizer().tokenize_query("risk"),
            filters=RetrievalFilters(
                security_id=SECURITY_ID,
                research_as_of_time=NOW,
                languages=(DocumentLanguage.EN_US,),
            ),
        )
    )

    assert [hit.chunk_id for hit in hits] == [english.chunk_id]
