# Deterministic chunking

`chunk-v1` consumes canonical parser output, preserving PDF page boundaries and HTML/JSON sections
before bounded character windows. Each chunk retains exact offsets plus its PDF page, HTML anchor
or JSON pointer when present. The target is 1,000 characters, maximum 1,600, minimum 120 and overlap
at most 200 and 20 percent of target. Splits prefer whitespace so stock codes, percentages,
decimal-unit tokens and ASCII words remain intact; a forced hard-limit split emits a warning.

The checksum uses canonical JSON containing canonical-text checksum, parser/config metadata,
chunk version, index, exact offsets and exact text. Rebuilding identical inputs gives identical
ordered descriptors and checksums independent of random database IDs. Old chunks are immutable;
parser, sanitizer or chunk configuration changes create another generation. Synthetic inputs are
SYNTHETIC_TEST_ONLY and NOT_COMPANY_EVIDENCE, never company research.
