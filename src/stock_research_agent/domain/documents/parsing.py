"""Offline parse-run orchestration over immutable bytes."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from stock_research_agent.domain.documents.enums import ParseStatus
from stock_research_agent.domain.documents.parsers.base import ParserRegistry
from stock_research_agent.domain.documents.repositories import DocumentArtifactRepository
from stock_research_agent.domain.documents.schemas import (
    DocumentParseResult,
    DocumentParseRunRecord,
    DocumentParseRunWrite,
    ParseCompletion,
    ParserConfig,
)
from stock_research_agent.infrastructure.blob_storage import BlobStorage, BlobStorageError

_SANITIZER_VERSION = "sanitizer-v1"


class DocumentParseService:
    def __init__(
        self,
        repository: DocumentArtifactRepository,
        blob_storage: BlobStorage,
        parsers: ParserRegistry,
    ) -> None:
        self._repository = repository
        self._blob_storage = blob_storage
        self._parsers = parsers

    def parse(self, document_version_id: UUID, config: ParserConfig) -> DocumentParseResult:
        version = self._repository.get_document_version(document_version_id)
        if version is None:
            return _blocked("DOCUMENT_VERSION_NOT_FOUND")
        parser = self._parsers.select(version.mime_type)
        if parser is None:
            return _blocked("PARSER_NOT_CONFIGURED")
        config_checksum = hashlib.sha256(
            json.dumps(
                config.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        existing = self._repository.find_parse_run(
            document_version_id,
            parser.parser_name,
            parser.parser_version,
            _SANITIZER_VERSION,
            config_checksum,
        )
        if existing is not None and existing.status != ParseStatus.RUNNING:
            return DocumentParseResult(
                status=existing.status,
                run=existing,
                document=self._repository.get_parsed_document(existing.id),
                reused=True,
                warnings=existing.warnings,
            )
        if existing is not None:
            return _in_progress(existing)
        try:
            content = self._blob_storage.get(version.storage_uri)
        except BlobStorageError:
            return _blocked("DOCUMENT_BLOB_NOT_AVAILABLE")
        running, acquired = self._repository.acquire_parse_run(
            DocumentParseRunWrite(
                document_version_id=document_version_id,
                parser_name=parser.parser_name,
                parser_version=parser.parser_version,
                sanitizer_version=_SANITIZER_VERSION,
                config_checksum=config_checksum,
            )
        )
        if not acquired:
            if running.status != ParseStatus.RUNNING:
                return DocumentParseResult(
                    status=running.status,
                    run=running,
                    document=self._repository.get_parsed_document(running.id),
                    reused=True,
                    warnings=running.warnings,
                )
            return _in_progress(running)
        parsed = parser.parse(content, config)
        self._repository.replace_running_artifacts(running.id, parsed)
        terminal = self._repository.finish_parse_run(
            running.id,
            ParseCompletion(
                status=parsed.status,
                canonical_text_checksum=parsed.canonical_text_checksum,
                warnings=parsed.warnings,
            ),
        )
        return DocumentParseResult(
            status=terminal.status,
            run=terminal,
            document=parsed,
            reused=False,
            warnings=terminal.warnings,
        )


def _blocked(warning: str) -> DocumentParseResult:
    return DocumentParseResult(
        status=ParseStatus.BLOCKED,
        run=None,
        document=None,
        reused=False,
        warnings=(warning,),
    )


def _in_progress(run: DocumentParseRunRecord) -> DocumentParseResult:
    return DocumentParseResult(
        status=ParseStatus.BLOCKED,
        run=run,
        document=None,
        reused=True,
        warnings=("PARSE_RUN_IN_PROGRESS",),
    )
