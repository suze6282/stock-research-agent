from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    ParseStatus,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.parsers.base import ParserRegistry
from stock_research_agent.domain.documents.parsing import DocumentParseService
from stock_research_agent.domain.documents.schemas import (
    DocumentParseRunRecord,
    DocumentParseRunWrite,
    DocumentVersionRecord,
    ParseCompletion,
    ParsedDocument,
    ParserConfig,
)
from stock_research_agent.infrastructure.blob_storage import InMemoryBlobStorage

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


class StubParser:
    parser_name = "stub-text"
    parser_version = "stub-v1"

    def __init__(self, status: ParseStatus = ParseStatus.PASS) -> None:
        self.status = status
        self.calls = 0

    def parse(self, content: bytes, config: ParserConfig) -> ParsedDocument:
        self.calls += 1
        text = content.decode()
        return ParsedDocument(
            canonical_text=text,
            canonical_text_checksum=hashlib.sha256(text.encode()).hexdigest(),
            status=self.status,
            warnings=("PARSER_PARTIAL",) if self.status == ParseStatus.PARTIAL else (),
        )


class FakeArtifactRepository:
    def __init__(self, version: DocumentVersionRecord) -> None:
        self.version = version
        self.runs: list[DocumentParseRunRecord] = []
        self.documents: dict[UUID, ParsedDocument] = {}

    def get_document_version(self, document_version_id: UUID) -> DocumentVersionRecord | None:
        return self.version if document_version_id == self.version.id else None

    def find_parse_run(
        self,
        document_version_id: UUID,
        parser_name: str,
        parser_version: str,
        sanitizer_version: str,
        config_checksum: str,
    ) -> DocumentParseRunRecord | None:
        return next(
            (
                row
                for row in self.runs
                if (
                    row.document_version_id,
                    row.parser_name,
                    row.parser_version,
                    row.sanitizer_version,
                    row.config_checksum,
                )
                == (
                    document_version_id,
                    parser_name,
                    parser_version,
                    sanitizer_version,
                    config_checksum,
                )
            ),
            None,
        )

    def create_parse_run(self, value: DocumentParseRunWrite) -> DocumentParseRunRecord:
        row = DocumentParseRunRecord(
            id=uuid4(),
            status=ParseStatus.RUNNING,
            started_at=NOW,
            **value.model_dump(exclude={"status"}),
        )
        self.runs.append(row)
        return row

    def acquire_parse_run(
        self, value: DocumentParseRunWrite
    ) -> tuple[DocumentParseRunRecord, bool]:
        existing = self.find_parse_run(
            value.document_version_id,
            value.parser_name,
            value.parser_version,
            value.sanitizer_version,
            value.config_checksum,
        )
        if existing is not None:
            return existing, False
        return self.create_parse_run(value), True

    def replace_running_artifacts(self, parse_run_id: UUID, value: ParsedDocument) -> None:
        self.documents[parse_run_id] = value

    def finish_parse_run(
        self, parse_run_id: UUID, completion: ParseCompletion
    ) -> DocumentParseRunRecord:
        current = next(row for row in self.runs if row.id == parse_run_id)
        terminal = current.model_copy(
            update={
                "status": completion.status,
                "canonical_text_checksum": completion.canonical_text_checksum,
                "warnings": completion.warnings,
                "completed_at": NOW,
            }
        )
        self.runs[self.runs.index(current)] = terminal
        return terminal

    def get_parsed_document(self, parse_run_id: UUID) -> ParsedDocument | None:
        return self.documents.get(parse_run_id)


def _arrange(
    parser: StubParser | None = None,
) -> tuple[DocumentParseService, FakeArtifactRepository, StubParser, UUID]:
    content = b"synthetic body"
    storage = InMemoryBlobStorage(
        max_blob_bytes=10_000_000,
        key_factory=lambda: "0123456789abcdef0123456789abcdef",
    )
    blob = storage.put(content, content_type="text/plain")
    version_id = uuid4()
    version = DocumentVersionRecord(
        id=version_id,
        logical_document_id=uuid4(),
        source_document_id=uuid4(),
        security_id=uuid4(),
        provider_id=uuid4(),
        source_payload_id=uuid4(),
        version_number=1,
        supersedes_document_version_id=None,
        storage_uri=blob.uri,
        mime_type=blob.content_type,
        checksum_algorithm="sha256",
        checksum=blob.checksum_sha256,
        byte_size=blob.size_bytes,
        published_at=NOW,
        filed_at=None,
        period_end=None,
        retrieved_at=NOW,
        document_language=DocumentLanguage.EN_US,
        trust_level=TrustLevel.TEST_FIXTURE,
        evidence_origin="SYNTHETIC_TEST_ONLY",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        source_version_status=SourceVersionStatus.ACTIVE,
        created_at=NOW,
    )
    repository = FakeArtifactRepository(version)
    selected = parser or StubParser()
    registry = ParserRegistry({"text/plain": selected})
    return DocumentParseService(repository, storage, registry), repository, selected, version_id


def test_parse_service_persists_terminal_result_and_artifacts() -> None:
    service, repository, parser, version_id = _arrange()

    result = service.parse(version_id, ParserConfig())

    assert result.status == ParseStatus.PASS
    assert result.reused is False
    assert parser.calls == 1
    assert result.run.id in repository.documents


def test_parse_service_reuses_same_terminal_generation() -> None:
    service, repository, parser, version_id = _arrange()

    first = service.parse(version_id, ParserConfig())
    second = service.parse(version_id, ParserConfig())

    assert second.reused is True
    assert second.run == first.run
    assert parser.calls == 1
    assert len(repository.runs) == 1


def test_parse_service_does_not_duplicate_work_owned_by_another_caller() -> None:
    service, repository, parser, version_id = _arrange()
    config = ParserConfig()
    config_checksum = hashlib.sha256(
        json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    repository.create_parse_run(
        DocumentParseRunWrite(
            document_version_id=version_id,
            parser_name=parser.parser_name,
            parser_version=parser.parser_version,
            sanitizer_version="sanitizer-v1",
            config_checksum=config_checksum,
        )
    )

    result = service.parse(version_id, config)

    assert result.status == ParseStatus.BLOCKED
    assert result.warnings == ("PARSE_RUN_IN_PROGRESS",)
    assert result.reused is True
    assert parser.calls == 0
    assert repository.documents == {}


def test_parse_service_propagates_partial_without_promoting_to_pass() -> None:
    service, _, _, version_id = _arrange(StubParser(ParseStatus.PARTIAL))

    result = service.parse(version_id, ParserConfig())

    assert result.status == ParseStatus.PARTIAL
    assert result.warnings == ("PARSER_PARTIAL",)


def test_parse_service_blocks_unknown_version_or_unregistered_mime() -> None:
    service, repository, _, version_id = _arrange()
    missing = service.parse(uuid4(), ParserConfig())
    assert missing.status == ParseStatus.BLOCKED
    assert missing.warnings == ("DOCUMENT_VERSION_NOT_FOUND",)

    repository.version = repository.version.model_copy(update={"mime_type": "text/html"})
    blocked = service.parse(version_id, ParserConfig())
    assert blocked.status == ParseStatus.BLOCKED
    assert blocked.warnings == ("PARSER_NOT_CONFIGURED",)


def test_parser_registry_does_not_accept_request_selected_classes_or_paths() -> None:
    with pytest.raises(ValueError, match="MIME"):
        ParserRegistry({"C:/parser.exe": StubParser()})
