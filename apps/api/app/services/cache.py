import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path
from threading import Lock

from app.schemas.scores import Ruleset


def normalize_player(value: str) -> str:
    value = value.strip().casefold()
    return (value.lstrip("0") or "0") if value.isascii() and value.isdecimal() else value


def score_cache_key(player: str, mode: Ruleset | None = None) -> str:
    # Cache the full best 50 once; limit is a response slice, not a new upstream query.
    raw = f"v1:{mode or 'auto'}:best:50:{normalize_player(player)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def not_found_cache_key(player: str) -> str:
    # A missing player 404s in every mode, so one short-lived entry covers all of them.
    raw = f"v1:not-found:{normalize_player(player)}"
    return hashlib.sha256(raw.encode()).hexdigest()


class JsonCache:
    def __init__(self, directory: Path, ttl: int, retention: int = 15552000):
        self.directory = directory
        self.ttl = ttl
        self.retention = retention
        self.lock = Lock()
        self.next_cleanup = 0.0

    def _cleanup(self) -> None:
        now = time.time()
        if now < self.next_cleanup:
            return
        self.next_cleanup = now + 3600
        for path in self.directory.glob("*.json"):
            try:
                if now - path.stat().st_mtime >= self.retention:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    def get(self, key: str) -> dict | None:
        fresh = self.get_fresh(key)
        if fresh is None:
            return None
        data, _remaining = fresh
        return data

    def get_fresh(self, key: str) -> tuple[dict, int] | None:
        with self.lock:
            self._cleanup()
            path = self.directory / f"{key}.json"
            try:
                entry = json.loads(path.read_text())
                if not isinstance(entry, dict) or not isinstance(entry.get("data"), dict):
                    return None
                age = time.time() - float(entry["created_at"])
                if not math.isfinite(age) or age < 0 or age >= self.ttl:
                    return None
                return entry["data"], max(0, int(self.ttl - age))
            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                return None

    def set(self, key: str, data: dict) -> None:
        with self.lock:
            self._cleanup()
            self.directory.mkdir(parents=True, exist_ok=True)
            # Atomic replacement prevents partial JSON after interruption.
            fd, name = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as file:
                    json.dump({"created_at": time.time(), "data": data}, file)
                os.replace(name, self.directory / f"{key}.json")
            finally:
                Path(name).unlink(missing_ok=True)
