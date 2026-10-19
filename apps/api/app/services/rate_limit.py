import logging
import math
import time
from collections import deque
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock

logger = logging.getLogger(__name__)


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
                    retry_after = max(1, math.ceil(self.window - (now - bucket[0])))
                    logger.warning(
                        "local_rate_limited",
                        extra={
                            "fields": {
                                "scope": key.split(":", 1)[0],
                                "retry_after": retry_after,
                            }
                        },
                    )
                    return retry_after
            for key, _ in limits:
                self.buckets.setdefault(key, deque()).append(now)
        return None


class UpstreamBusy(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class UpstreamLimiter:
    """One budget for OAuth and API HTTP requests, paced without bursts."""

    def __init__(self, per_minute: int, budget: str = "api"):
        self.budget = budget
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
                retry_after = max(1, math.ceil(delay))
                logger.warning(
                    "upstream_wait",
                    extra={
                        "fields": {
                            "budget": self.budget,
                            "retry_after": retry_after,
                            "reason": "upstream_cooldown"
                            if self.cooldown_until > time.monotonic()
                            else "budget_exhausted",
                        }
                    },
                )
                raise UpstreamBusy(retry_after)

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self._delay(now, 1)
            if delay > 0:
                retry_after = max(1, math.ceil(delay))
                logger.warning(
                    "upstream_wait",
                    extra={
                        "fields": {
                            "budget": self.budget,
                            "retry_after": retry_after,
                            "reason": "upstream_cooldown"
                            if self.cooldown_until > time.monotonic()
                            else "budget_exhausted",
                        }
                    },
                )
                raise UpstreamBusy(retry_after)
            if self.requests:
                time.sleep(max(0, self.requests[-1] + self.interval - now))
            self.requests.append(time.monotonic())

    def defer(self, retry_after: str | None) -> int:
        seconds = 60.0
        fallback = True
        if retry_after:
            try:
                seconds = float(retry_after)
                fallback = False
            except ValueError:
                try:
                    seconds = (
                        parsedate_to_datetime(retry_after) - datetime.now(UTC)
                    ).total_seconds()
                    fallback = False
                except (ValueError, TypeError, OverflowError):
                    pass
        if not math.isfinite(seconds) or seconds <= 0:
            seconds = 60.0
            fallback = True
        seconds = math.ceil(seconds)
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, time.monotonic() + seconds)
            remaining = max(1, math.ceil(self.cooldown_until - time.monotonic()))
            logger.warning(
                "upstream_rate_limited",
                extra={
                    "fields": {
                        "budget": self.budget,
                        "retry_after": remaining,
                        "fallback": fallback,
                    }
                },
            )
            return remaining
