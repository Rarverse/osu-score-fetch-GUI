import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from threading import Lock

from app.schemas.scores import Ruleset


def normalize_player(value: str) -> str:
    value = value.strip().casefold()
    return str(int(value)) if value.isascii() and value.isdecimal() else value


def score_cache_key(player: str, mode: Ruleset = "mania") -> str:
    # Cache the full best 50 once; limit is a response slice, not a new upstream query.
    raw = f"v1:{mode}:best:50:{normalize_player(player)}"
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
        with self.lock:
            self._cleanup()
            path = self.directory / f"{key}.json"
            try:
                entry = json.loads(path.read_text())
                if time.time() - entry["created_at"] >= self.ttl:
                    return None
                return entry["data"]
            except (OSError, ValueError, KeyError, TypeError):
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
