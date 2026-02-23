"""Tests for token bucket rate limiter."""

from __future__ import annotations

import time

from sims4_updater.core.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    def test_unlimited_returns_immediately(self):
        limiter = TokenBucketRateLimiter(0)
        start = time.monotonic()
        limiter.acquire(1_000_000)
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # should be near-instant

    def test_negative_rate_clamped_to_zero(self):
        limiter = TokenBucketRateLimiter(-5)
        assert limiter.limit == 0
        # Should not block since 0 = unlimited
        limiter.acquire(1000)

    def test_set_limit_changes_rate(self):
        limiter = TokenBucketRateLimiter(1000)
        assert limiter.limit == 1000
        limiter.set_limit(5000)
        assert limiter.limit == 5000

    def test_set_limit_to_zero_makes_unlimited(self):
        limiter = TokenBucketRateLimiter(100)
        limiter.set_limit(0)
        assert limiter.limit == 0
        # Should be unlimited now
        start = time.monotonic()
        limiter.acquire(1_000_000)
        assert time.monotonic() - start < 0.05

    def test_rate_limiting_blocks(self):
        # 1000 bytes/sec, acquiring 1500 should take ~0.5 seconds
        # (1000 tokens initially available, deficit of 500)
        limiter = TokenBucketRateLimiter(1000)
        # Prime the bucket with some tokens
        time.sleep(0.1)
        start = time.monotonic()
        limiter.acquire(1000)
        limiter.acquire(500)
        elapsed = time.monotonic() - start
        # Should have some blocking time (at least 0.3s)
        assert elapsed > 0.2

    def test_burst_cap(self):
        # Even after sleeping longer than 1 second, tokens cap at 1 second worth
        limiter = TokenBucketRateLimiter(10000)
        time.sleep(0.2)  # accumulate 2000 tokens but cap is 10000
        start = time.monotonic()
        limiter.acquire(100)  # well within the accumulated tokens
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # should succeed without blocking
