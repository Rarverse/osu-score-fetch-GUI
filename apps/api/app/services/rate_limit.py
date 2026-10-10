import math
import time
from collections import deque
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
