"""Token-bucket rate limiter for download speed control.

Provides a thread-safe global speed limiter that can be shared across
multiple concurrent download threads. Each thread calls acquire() after
writing a chunk; the call blocks if the rate limit would be exceeded.

Usage:
    limiter = TokenBucketRateLimiter(max_bytes_per_sec=5_000_000)  # 5 MB/s
    # In download loop:
    limiter.acquire(len(chunk))  # blocks until tokens available
    limiter.set_limit(0)  # 0 = unlimited
"""

from __future__ import annotations

import threading
import time


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter.

    Tokens accumulate at ``max_bytes_per_sec`` per second. Each
    ``acquire(n)`` call consumes *n* tokens and blocks if insufficient
    tokens are available.  Burst capacity is capped at one second of
    tokens to prevent long idle periods from building excessive credit.
    """

    def __init__(self, max_bytes_per_sec: int = 0) -> None:
        self._lock = threading.Lock()
        self._max_rate = max(0, max_bytes_per_sec)
        self._tokens = 0.0
        self._last_refill = time.monotonic()

    @property
    def limit(self) -> int:
        """Current limit in bytes/sec.  0 means unlimited."""
        return self._max_rate

    def set_limit(self, max_bytes_per_sec: int) -> None:
        """Change the rate limit at runtime.  0 = unlimited."""
        with self._lock:
            self._max_rate = max(0, max_bytes_per_sec)
            self._tokens = 0.0
            self._last_refill = time.monotonic()

    def acquire(self, byte_count: int) -> None:
        """Block until *byte_count* tokens are available."""
        if self._max_rate <= 0:
            return  # unlimited

        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._last_refill = now
                self._tokens += elapsed * self._max_rate
                # Cap burst to 1 second worth of tokens
                if self._tokens > self._max_rate:
                    self._tokens = float(self._max_rate)

                if self._tokens >= byte_count:
                    self._tokens -= byte_count
                    return

                # Calculate sleep time for the deficit
                deficit = byte_count - self._tokens
                wait_time = deficit / self._max_rate

            time.sleep(min(wait_time, 0.5))  # cap individual sleeps at 500ms
