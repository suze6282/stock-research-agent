# Document versions

`SourceDocument` remains provider metadata and lineage. `LogicalDocument` is the stable confirmed
identity within one security; title similarity never creates identity. `DocumentVersion` binds
one exact byte sequence, SHA-256, opaque Blob URI, MIME, source timestamps and provenance. It is
immutable after creation. A revision, withdrawal or replacement creates another version and an
explicit supersedes relation; old snapshots, citations and retrieval runs remain readable.

`SnapshotDocumentVersion` may link only a `SOURCE_DOCUMENTS/source_documents` SnapshotItem whose
source record, provider and security match the version. Filing metadata cannot stand in for body
evidence and a terminal old snapshot never receives a later body retroactively. Published time is
never inferred from retrieval time. 工业富联真实正文验收：BLOCKED。美光科技真实正文验收：BLOCKED。
