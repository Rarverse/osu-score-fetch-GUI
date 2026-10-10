import math
import time
from collections import deque
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock


class RateLimiter:
    """Sliding window for a single API process; check all buckets atomically."""

    def __init__(self, window: int):
        self.window = window
        self.buckets: dict[str, deque[float]] = {}
        self.lock = Lock()

    def check(self, limits: list[tuple[str, int]]) -> int | None:
        now = time.monotonic()
        with self.lock:
            # Prune inactive buckets so arbitrary usernames cannot accumulate forever.
            for key in list(self.buckets):
                bucket = self.buckets[key]
                while bucket and bucket[0] <= now - self.window:
                    bucket.popleft()
                if not bucket:
                    del self.buckets[key]
            for key, limit in limits:
                bucket = self.buckets.get(key)
                if bucket and len(bucket) >= limit:
                    return max(1, math.ceil(self.window - (now - bucket[0])))
            for key, _ in limits:
                self.buckets.setdefault(key, deque()).append(now)
        return None


class UpstreamBusy(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class UpstreamLimiter:
    """One budget for OAuth and API HTTP requests, paced without bursts."""

    def __init__(self, per_minute: int):
        self.limit = per_minute
        self.interval = 60 / per_minute
        self.requests: deque[float] = deque()
        self.cooldown_until = 0.0
        self.lock = Lock()

    def _delay(self, now: float, needed: int) -> float:
        while self.requests and self.requests[0] <= now - 60:
            self.requests.popleft()
        delay = max(0.0, self.cooldown_until - now)
        if len(self.requests) + needed > self.limit:
            delay = max(
                delay, self.requests[len(self.requests) + needed - self.limit - 1] + 60 - now
            )
        return delay

    def ensure_capacity(self, needed: int) -> None:
        with self.lock:
            delay = self._delay(time.monotonic(), needed)
            if delay > 0:
                raise UpstreamBusy(max(1, math.ceil(delay)))

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self._delay(now, 1)
            if delay > 0:
                raise UpstreamBusy(max(1, math.ceil(delay)))
            if self.requests:
                time.sleep(max(0, self.requests[-1] + self.interval - now))
            self.requests.append(time.monotonic())

    def defer(self, retry_after: str | None) -> int:
        seconds = 60.0
        if retry_after:
            try:
                seconds = float(retry_after)
            except ValueError:
                try:
                    seconds = (
                        parsedate_to_datetime(retry_after) - datetime.now(UTC)
                    ).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    pass
        if not math.isfinite(seconds) or seconds <= 0:
            seconds = 60.0
        seconds = math.ceil(seconds)
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, time.monotonic() + seconds)
            return max(1, math.ceil(self.cooldown_until - time.monotonic()))
