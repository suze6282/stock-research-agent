from __future__ import annotations

import importlib
import math
import threading

import pytest

from stock_research_agent.providers.rate_limit import MonotonicRateLimiter


class _Clock:
    def __init__(self) -> None:
        self.now = 10.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.parametrize("rate", [0.0, -1.0, math.inf, -math.inf, math.nan])
def test_rate_limiter_rejects_non_positive_or_non_finite_rates(rate: float) -> None:
    module = importlib.import_module("stock_research_agent.providers.rate_limit")

    with pytest.raises(ValueError, match="positive and finite"):
        module.MonotonicRateLimiter(rate, monotonic=lambda: 0.0, sleeper=lambda _: None)


def test_rate_limiter_sleeps_only_until_same_bucket_deadline() -> None:
    clock = _Clock()
    limiter = MonotonicRateLimiter(
        2.0,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    limiter.acquire("data.example")
    clock.now += 0.2
    limiter.acquire("data.example")

    assert clock.sleeps == [pytest.approx(0.3)]


def test_rate_limiter_keeps_independent_bucket_deadlines() -> None:
    clock = _Clock()
    limiter = MonotonicRateLimiter(
        1.0,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    limiter.acquire("one.example")
    limiter.acquire("two.example")

    assert clock.sleeps == []


def test_waiting_bucket_does_not_hold_lock_needed_by_independent_bucket() -> None:
    sleep_started = threading.Event()
    release_sleep = threading.Event()
    second_bucket_finished = threading.Event()

    def blocking_sleep(_: float) -> None:
        sleep_started.set()
        release_sleep.wait(timeout=1.0)

    limiter = MonotonicRateLimiter(
        1.0,
        monotonic=lambda: 10.0,
        sleeper=blocking_sleep,
    )
    limiter.acquire("one.example")

    waiting = threading.Thread(target=lambda: limiter.acquire("one.example"))
    independent = threading.Thread(
        target=lambda: (limiter.acquire("two.example"), second_bucket_finished.set())
    )
    try:
        waiting.start()
        assert sleep_started.wait(timeout=0.3)
        independent.start()
        assert second_bucket_finished.wait(timeout=0.2)
    finally:
        release_sleep.set()
        waiting.join(timeout=1.0)
        independent.join(timeout=1.0)
