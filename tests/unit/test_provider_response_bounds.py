from collections.abc import Iterator
from decimal import Decimal

import pytest

from stock_research_agent.providers.http_response import (
    BoundedResponseReader,
    ProviderResponseLimits,
)


class FakeStream:
    def __init__(
        self,
        chunks: tuple[bytes, ...],
        *,
        declared_length: int | None = None,
        compressed_length: int | None = None,
    ) -> None:
        self.chunks = chunks
        self.declared_length = declared_length
        self.compressed_length = compressed_length
        self.closed = False

    def iter_chunks(self) -> Iterator[bytes]:
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


def _limits(**updates: object) -> ProviderResponseLimits:
    values: dict[str, object] = {
        "max_bytes": 16,
        "max_chunks": 4,
        "max_decompression_ratio": Decimal("4"),
        "max_duration_seconds": Decimal("5"),
    }
    values.update(updates)
    return ProviderResponseLimits(**values)


def test_bounded_reader_accepts_small_stream_and_closes_it() -> None:
    stream = FakeStream((b"hello", b" world"), declared_length=11)
    payload = BoundedResponseReader().read(stream, _limits())

    assert payload.body == b"hello world"
    assert payload.byte_count == 11
    assert len(payload.checksum) == 64
    assert stream.closed is True


@pytest.mark.parametrize(
    ("stream", "limits", "reason"),
    [
        (FakeStream((b"x" * 17,)), _limits(), "PROVIDER_RESPONSE_TOO_LARGE"),
        (
            FakeStream((b"a", b"b", b"c", b"d", b"e")),
            _limits(),
            "PROVIDER_RESPONSE_CHUNK_LIMIT",
        ),
        (
            FakeStream((b"hello",), declared_length=4),
            _limits(),
            "PROVIDER_RESPONSE_LENGTH_MISMATCH",
        ),
        (
            FakeStream((b"x" * 16,), compressed_length=1),
            _limits(),
            "PROVIDER_RESPONSE_COMPRESSION_RATIO",
        ),
    ],
)
def test_bounded_reader_rejects_overflow_false_length_and_compression_bomb(
    stream: FakeStream,
    limits: ProviderResponseLimits,
    reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        BoundedResponseReader().read(stream, limits)
    assert stream.closed is True


def test_bounded_reader_stops_endless_stream_by_chunk_limit() -> None:
    class EndlessStream(FakeStream):
        def iter_chunks(self) -> Iterator[bytes]:
            while True:
                yield b"x"

    stream = EndlessStream(())
    with pytest.raises(ValueError, match="PROVIDER_RESPONSE_CHUNK_LIMIT"):
        BoundedResponseReader().read(stream, _limits(max_chunks=2))
    assert stream.closed is True


def test_bounded_reader_enforces_deterministic_duration_and_closes() -> None:
    ticks = iter((Decimal("0"), Decimal("6")))
    stream = FakeStream((b"x",))
    reader = BoundedResponseReader(clock=lambda: next(ticks))
    with pytest.raises(ValueError, match="PROVIDER_RESPONSE_DURATION"):
        reader.read(stream, _limits(max_duration_seconds=Decimal("5")))
    assert stream.closed is True
