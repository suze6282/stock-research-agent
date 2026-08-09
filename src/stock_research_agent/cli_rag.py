"""Explicit offline index/retrieval writes and cache reads."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from stock_research_agent.config import Settings
from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.retrieval.enums import RetrievalMode
from stock_research_agent.domain.retrieval.lexical import (
    LexicalIndexService,
    LexicalSearchService,
)
from stock_research_agent.domain.retrieval.schemas import (
    LexicalBuildRequest,
    RetrievalFilters,
    RetrievalRequest,
)
from stock_research_agent.domain.retrieval.service import (
    DeterministicRetrievalEngine,
    PrecomputedRetrievalQueryService,
    RetrievalExecutionService,
)
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage

rag_app = typer.Typer(
    help="Explicit offline RAG index, retrieval-run, and cache operations.",
    no_args_is_help=True,
)
vector_index_app = typer.Typer(help="Explicit vector-index operations.", no_args_is_help=True)
citation_app = typer.Typer(help="Read and verify persisted citations.", no_args_is_help=True)
retrieval_run_app = typer.Typer(help="Read immutable Retrieval Runs.", no_args_is_help=True)
rag_app.add_typer(vector_index_app, name="vector-index")
rag_app.add_typer(citation_app, name="citation")
rag_app.add_typer(retrieval_run_app, name="retrieval-run")


def _security_id(session: object, value: str) -> UUID | None:
    from sqlalchemy.orm import Session

    if not isinstance(session, Session):
        return None
    try:
        return UUID(value)
    except ValueError:
        result = SecurityResolutionService(SqlAlchemySecurityMasterRepository(session)).resolve(
            value
        )
        if result.status != ResolutionStatus.RESOLVED:
            return None
        return result.candidates[0].security_id


def _require_scope(snapshot_id: UUID | None, as_of: datetime | None) -> None:
    if (snapshot_id is None) == (as_of is None):
        typer.echo("BLOCKED: EXACTLY_ONE_RETRIEVAL_SCOPE_REQUIRED")
        raise typer.Exit(code=4)


@rag_app.command("vector-status")
def vector_status() -> None:
    """Report the production vector channel without loading or downloading a model."""
    typer.echo("BLOCKED: EMBEDDING_PROVIDER_NOT_CONFIGURED")


@vector_index_app.command("build")
def vector_index_build() -> None:
    """Refuse vector builds until a formally configured provider is approved."""
    typer.echo("BLOCKED: EMBEDDING_PROVIDER_NOT_CONFIGURED")
    raise typer.Exit(code=3)


@rag_app.command("build-lexical-index")
def build_lexical_index(
    security: Annotated[str, typer.Argument(help="Resolved security symbol or ID.")],
    snapshot_id: Annotated[UUID | None, typer.Option("--snapshot-id")] = None,
    as_of: Annotated[datetime | None, typer.Option("--as-of")] = None,
) -> None:
    """Explicitly build and persist an offline lexical index from eligible document chunks."""
    _require_scope(snapshot_id, as_of)
    engine = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            security_id = _security_id(session, security)
            if security_id is None:
                raise LookupError
            repository = SqlAlchemyKnowledgeRepository(session)
            chunks = repository.list_indexable_chunks(security_id)
            if not chunks:
                raise LookupError
            request = LexicalBuildRequest(
                index_name=f"security-{security_id}",
                security_id=security_id,
                snapshot_id=snapshot_id,
                index_as_of_time=as_of,
            )
            result = LexicalIndexService(chunks).build(request)
            repository.persist_lexical_index(request, result)
            session.commit()
    except LookupError:
        typer.echo("BLOCKED: COMPANY_DOCUMENT_BODY_NOT_AVAILABLE")
        raise typer.Exit(code=3) from None
    except Exception:
        typer.echo("BLOCKED: LEXICAL_INDEX_BUILD_FAILED")
        raise typer.Exit(code=3) from None
    finally:
        if engine is not None:
            engine.dispose()
    typer.echo(result.model_dump_json(indent=2))


@rag_app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Bounded query to persist explicitly.")],
    security: Annotated[str, typer.Option("--security", help="Security symbol or ID.")],
    snapshot_id: Annotated[UUID | None, typer.Option("--snapshot-id")] = None,
    as_of: Annotated[datetime | None, typer.Option("--as-of")] = None,
    mode: Annotated[RetrievalMode, typer.Option("--mode")] = RetrievalMode.LEXICAL,
    max_results: Annotated[int, typer.Option("--max-results", min=1, max=20)] = 10,
) -> None:
    """Explicit offline Retrieval Run write; never refreshes data or accesses the network."""
    _require_scope(snapshot_id, as_of)
    engine = storage = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        storage = LocalBlobStorage(
            settings.blob_storage_root,
            max_blob_bytes=settings.document_max_bytes,
        )
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            security_id = _security_id(session, security)
            if security_id is None:
                raise LookupError
            repository = SqlAlchemyKnowledgeRepository(session, blob_storage=storage)
            index = repository.find_lexical_index(
                security_id=security_id,
                snapshot_id=snapshot_id,
                index_as_of_time=as_of,
            )
            if index is None or index.index_version_id is None:
                raise LookupError
            chunks = repository.list_indexable_chunks(security_id)
            citations = repository.citation_ids_for_chunks(
                tuple(chunk.chunk_id for chunk in chunks)
            )
            retrieval = RetrievalExecutionService(
                repository,
                DeterministicRetrievalEngine(
                    index.index_version_id,
                    LexicalSearchService(chunks, index, citation_ids=citations),
                ),
            ).execute(
                RetrievalRequest(
                    query=query,
                    mode=mode,
                    filters=RetrievalFilters(
                        security_id=security_id,
                        snapshot_id=snapshot_id,
                        research_as_of_time=as_of,
                    ),
                    max_results=max_results,
                )
            )
            session.commit()
    except LookupError:
        typer.echo("BLOCKED: RETRIEVAL_INDEX_NOT_AVAILABLE")
        raise typer.Exit(code=3) from None
    except Exception:
        typer.echo("BLOCKED: RETRIEVAL_RUN_FAILED")
        raise typer.Exit(code=3) from None
    finally:
        if storage is not None:
            storage.close()
        if engine is not None:
            engine.dispose()
    typer.echo(retrieval.model_dump_json(indent=2))


def _read_service() -> tuple[Engine, Session, PrecomputedRetrievalQueryService]:
    settings = Settings()
    if settings.database_url is None:
        raise LookupError
    engine = create_engine_from_settings(settings)
    session = create_session_factory(engine)()
    return engine, session, PrecomputedRetrievalQueryService(SqlAlchemyKnowledgeRepository(session))


@citation_app.command("show")
def citation_show(citation_id: UUID) -> None:
    """Read one immutable citation anchor."""
    engine = session = None
    try:
        engine, session, service = _read_service()
        result = service.get_citation(citation_id)
        if not result.records:
            raise LookupError
        typer.echo(result.model_dump_json(indent=2))
    except Exception:
        typer.echo("BLOCKED: CITATION_NOT_FOUND")
        raise typer.Exit(code=3) from None
    finally:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()


@citation_app.command("verify")
def citation_verify(
    citation_id: UUID,
    snapshot_id: Annotated[UUID | None, typer.Option("--snapshot-id")] = None,
    as_of: Annotated[datetime | None, typer.Option("--as-of")] = None,
) -> None:
    """Read deterministic citation verification; never regenerate the citation."""
    engine = session = storage = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        session = create_session_factory(engine)()
        storage = LocalBlobStorage(
            settings.blob_storage_root,
            max_blob_bytes=settings.document_max_bytes,
        )
        service = PrecomputedRetrievalQueryService(
            SqlAlchemyKnowledgeRepository(session, blob_storage=storage)
        )
        result = service.verify_citation(
            citation_id,
            snapshot_id=snapshot_id,
            research_as_of_time=as_of,
            strict_historical=True,
        )
        typer.echo(result.model_dump_json(indent=2))
        if result.status.value == "BLOCKED":
            raise typer.Exit(code=3)
    except typer.Exit:
        raise
    except Exception:
        typer.echo("BLOCKED: CITATION_VERIFICATION_NOT_AVAILABLE")
        raise typer.Exit(code=3) from None
    finally:
        if storage is not None:
            storage.close()
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()


@retrieval_run_app.command("show")
def retrieval_run_show(retrieval_run_id: UUID) -> None:
    """Read one immutable precomputed Retrieval Run."""
    engine = session = None
    try:
        engine, session, service = _read_service()
        result = service.get_retrieval_run(retrieval_run_id)
        if not result.records:
            raise LookupError
        typer.echo(result.model_dump_json(indent=2))
    except Exception:
        typer.echo("BLOCKED: RETRIEVAL_RUN_NOT_FOUND")
        raise typer.Exit(code=3) from None
    finally:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()
