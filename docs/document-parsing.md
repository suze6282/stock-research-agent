# Offline document parsing

Parsers receive existing immutable bytes and a bounded configuration. They never follow links,
load images, execute scripts, read attachments, open caller paths, access Provider HTTP, or create
database sessions. PDF uses pypdf only for an existing text layer; OCR is absent. Encryption,
scans and missing text return BLOCKED or PARTIAL. Physical pages are one-based and reading order
is explicitly best-effort.

HTML uses the standard-library parser and suppresses script, style, iframe, object, embed and form.
Malformed structure degrades. Text is UTF-8 only and preserves canonical half-open offsets. JSON
promotes only configured RFC 6901 string paths. Tables keep safe text but do not claim precise
row/column structure and never populate Stage 5 financial facts. 不调用大模型，也不执行正文指令。
