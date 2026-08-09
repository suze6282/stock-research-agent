"""Explicit document-version and parser commands; never download content."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

import typer
from sqlalchemy import select

from stock_research_agent.config import Settings
from stock_research_agent.db.models.knowledge import (
    DocumentChunk,
    DocumentParseRun,
    DocumentSection,
    DocumentVersion,
)
from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.db.session import (
    create_engine_from_settings,
    create_session_factory,
    session_scope,
)
from stock_research_agent.domain.documents.chunking import DocumentChunker
from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.identity import DocumentVersionService
from stock_research_agent.domain.documents.parsers.base import ParserRegistry
from stock_research_agent.domain.documents.parsers.html import SafeHtmlParser
from stock_research_agent.domain.documents.parsers.json import JsonDocumentParser
from stock_research_agent.domain.documents.parsers.pdf import PdfTextParser
from stock_research_agent.domain.documents.parsers.text import PlainTextParser
from stock_research_agent.domain.documents.parsing import DocumentParseService
from stock_research_agent.domain.documents.schemas import (
    AccessMode,
    ChunkConfig,
    EvidenceOrigin,
    LiveStatus,
    ParserConfig,
    RegisterDocumentVersionRequest,
)
from stock_research_agent.domain.securities.enums import ResolutionStatus
from stock_research_agent.domain.securities.resolution import SecurityResolutionService
from stock_research_agent.infrastructure.blob_storage import LocalBlobStorage

documents_app = typer.Typer(
    help="Explicit offline document-version and parser operations.",
    no_args_is_help=True,
)


def _registry() -> ParserRegistry:
    return ParserRegistry(
        {
            "application/pdf": PdfTextParser(),
            "text/html": SafeHtmlParser(),
            "text/plain": PlainTextParser(),
            "application/json": JsonDocumentParser(()),
        }
    )


@documents_app.command("parse")
def parse_document(
    security: Annotated[str, typer.Argument(help="Resolved security symbol, ID, or version ID.")],
) -> None:
    """Explicitly parse an already persisted body; never fetch from the network."""
    engine = None
    storage = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            try:
                requested_id = UUID(security)
            except ValueError:
                resolution = SecurityResolutionService(
                    SqlAlchemySecurityMasterRepository(session)
                ).resolve(security)
                if resolution.status != ResolutionStatus.RESOLVED:
                    raise LookupError from None
                requested_id = resolution.candidates[0].security_id
            version = session.get(DocumentVersion, requested_id)
            if version is None:
                version = session.scalar(
                    select(DocumentVersion)
                    .where(DocumentVersion.security_id == requested_id)
                    .order_by(DocumentVersion.version_number.desc(), DocumentVersion.id)
                    .limit(1)
                )
            if version is None:
                raise LookupError
            storage = LocalBlobStorage(
                settings.blob_storage_root,
                max_blob_bytes=settings.document_max_bytes,
            )
            result = DocumentParseService(repository, storage, _registry()).parse(
                version.id,
                ParserConfig(
                    max_document_bytes=settings.document_max_bytes,
                    max_pdf_pages=settings.document_max_pdf_pages,
                    max_document_characters=settings.document_max_characters,
                ),
            )
            if result.run is not None and result.document is not None:
                repository.add_chunks_and_citations(
                    parse_run_id=result.run.id,
                    document_version_id=version.id,
                    chunks=DocumentChunker().chunk(result.document, ChunkConfig()),
                )
            session.commit()
    except LookupError:
        typer.echo("BLOCKED: COMPANY_DOCUMENT_BODY_NOT_AVAILABLE")
        raise typer.Exit(code=3) from None
    except Exception:
        typer.echo("BLOCKED: DOCUMENT_PARSE_FAILED")
        raise typer.Exit(code=3) from None
    finally:
        if storage is not None:
            storage.close()
        if engine is not None:
            engine.dispose()
    typer.echo(result.model_dump_json(indent=2))


@documents_app.command("register-version")
def register_version(
    source_document_id: Annotated[UUID, typer.Argument(help="Persisted SourceDocument UUID.")],
    document_language: Annotated[DocumentLanguage, typer.Option("--document-language")],
    trust_level: Annotated[TrustLevel, typer.Option("--trust-level")],
    evidence_origin: Annotated[str, typer.Option("--evidence-origin")],
    access_mode: Annotated[str, typer.Option("--access-mode")],
    live_status: Annotated[str, typer.Option("--live-status")],
    source_version_status: Annotated[
        SourceVersionStatus, typer.Option("--source-version-status")
    ] = SourceVersionStatus.ACTIVE,
) -> None:
    """Register exact persisted verified bytes using explicitly supplied provenance markers."""
    engine = None
    storage = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            repository = SqlAlchemyKnowledgeRepository(session)
            body = repository.get_source_body(source_document_id)
            logical_document_id = repository.get_or_create_logical_document(source_document_id)
            if body is None or logical_document_id is None:
                raise LookupError
            storage = LocalBlobStorage(
                settings.blob_storage_root,
                max_blob_bytes=settings.document_max_bytes,
            )
            result = DocumentVersionService(repository, storage).register(
                RegisterDocumentVersionRequest(
                    logical_document_id=logical_document_id,
                    source_body=body,
                    document_language=document_language,
                    trust_level=trust_level,
                    evidence_origin=cast(EvidenceOrigin, evidence_origin),
                    access_mode=cast(AccessMode, access_mode),
                    live_status=cast(LiveStatus, live_status),
                    source_version_status=source_version_status,
                )
            )
            session.commit()
    except LookupError:
        typer.echo("BLOCKED: VERIFIED_SOURCE_DOCUMENT_BODY_REQUIRED")
        raise typer.Exit(code=3) from None
    except Exception:
        typer.echo("BLOCKED: DOCUMENT_VERSION_REGISTRATION_FAILED")
        raise typer.Exit(code=3) from None
    finally:
        if storage is not None:
            storage.close()
        if engine is not None:
            engine.dispose()
    typer.echo(result.model_dump_json(indent=2))


@documents_app.command("parse-status")
def parse_status(parse_run_id: UUID) -> None:
    """Read one persisted parse run without parsing or downloading."""
    engine = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        with session_scope(create_session_factory(engine)) as session:
            row = session.get(DocumentParseRun, parse_run_id)
            if row is None:
                raise LookupError
            typer.echo(
                f"status={row.status} parser={row.parser_name}@{row.parser_version} "
                f"completed={row.completed_at is not None}"
            )
    except Exception:
        typer.echo("BLOCKED: PARSE_RUN_NOT_FOUND")
        raise typer.Exit(code=3) from None
    finally:
        if engine is not None:
            engine.dispose()


@documents_app.command("sections")
def sections(document_version_id: UUID) -> None:
    """List bounded persisted section metadata without full document output."""
    engine = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        with session_scope(create_session_factory(engine)) as session:
            rows = session.scalars(
                select(DocumentSection)
                .join(DocumentParseRun, DocumentParseRun.id == DocumentSection.parse_run_id)
                .where(DocumentParseRun.document_version_id == document_version_id)
                .order_by(DocumentSection.section_path)
                .limit(100)
            ).all()
            if not rows:
                raise LookupError
            for row in rows:
                typer.echo(f"{row.section_path} | {row.title} | {row.locator_type}")
    except Exception:
        typer.echo("BLOCKED: DOCUMENT_SECTIONS_NOT_AVAILABLE")
        raise typer.Exit(code=3) from None
    finally:
        if engine is not None:
            engine.dispose()


@documents_app.command("chunks")
def chunks(document_version_id: UUID) -> None:
    """List bounded chunk metadata; never print the full source document."""
    engine = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        with session_scope(create_session_factory(engine)) as session:
            rows = session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_version_id == document_version_id)
                .order_by(DocumentChunk.chunk_index)
                .limit(100)
            ).all()
            if not rows:
                raise LookupError
            for row in rows:
                typer.echo(
                    f"{row.id} | index={row.chunk_index} | characters={len(row.text)} "
                    f"| checksum={row.checksum}"
                )
    except Exception:
        typer.echo("BLOCKED: DOCUMENT_CHUNKS_NOT_AVAILABLE")
        raise typer.Exit(code=3) from None
    finally:
        if engine is not None:
            engine.dispose()


@documents_app.command("verify")
def verify_document(document_version_id: UUID) -> None:
    """Verify immutable blob metadata for one persisted document version."""
    engine = None
    storage = None
    try:
        settings = Settings()
        if settings.database_url is None:
            raise LookupError
        engine = create_engine_from_settings(settings)
        with session_scope(create_session_factory(engine)) as session:
            version = session.get(DocumentVersion, document_version_id)
            if version is None:
                raise LookupError
            storage = LocalBlobStorage(
                settings.blob_storage_root,
                max_blob_bytes=settings.document_max_bytes,
            )
            metadata = storage.metadata(version.storage_uri)
            if (
                metadata.checksum_sha256 != version.checksum
                or metadata.size_bytes != version.byte_size
                or metadata.content_type != version.mime_type
            ):
                raise LookupError
        typer.echo(f"PASS: document_version={document_version_id} checksum={version.checksum}")
    except Exception:
        typer.echo("BLOCKED: DOCUMENT_VERSION_VERIFICATION_FAILED")
        raise typer.Exit(code=3) from None
    finally:
        if storage is not None:
            storage.close()
        if engine is not None:
            engine.dispose()
