import hmac
import json
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from app.schemas.scores import Ruleset

# Anonymous browser ids are UUIDs. Reject anything else so the file cannot grow from junk.
VISITOR_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
SOURCE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
MAX_SOURCES = 64
MODES: tuple[Ruleset, ...] = ("osu", "taiko", "fruits", "mania")


def _empty_day() -> dict:
    return {
        "queries": 0,
        "distinct_players": 0,
        "queries_by_mode": {mode: 0 for mode in MODES},
        "queries_by_source": {},
        "returning_visitors": 0,
        "player_hashes": [],
        "returning_visitor_hashes": [],
    }


class UsageStats:
    """Daily counts for one worker. Identity hashes require an external secret."""

    def __init__(
        self,
        path: Path,
        retention_days: int = 180,
        max_visitors: int = 10_000,
        *,
        salt: str | None = None,
    ):
        self.path = path
        self.retention_days = retention_days
        self.max_visitors = max_visitors
        self.salt = salt
        self.key_id = self._digest("usage-key-id") if salt else None
        self.lock = Lock()

    def migrate(self) -> None:
        # Remove legacy secrets even when there are no queries after deployment.
        with self.lock:
            if self.path.exists():
                self._save(self._load())

    def record(
        self,
        *,
        mode: Ruleset | None,
        success: bool,
        player_id: str | None,
        visitor_id: str | None,
        source: str | None = None,
    ) -> None:
        with self.lock:
            payload = self._load()
            day_key = datetime.now(UTC).date().isoformat()
            cutoff = (
                datetime.now(UTC).date() - timedelta(days=self.retention_days - 1)
            ).isoformat()
            payload["days"] = {
                key: value for key, value in payload["days"].items() if key >= cutoff
            }
            payload["visitors"] = {
                digest: first_seen
                for digest, first_seen in payload["visitors"].items()
                if isinstance(first_seen, str) and first_seen >= cutoff
            }
            day = payload["days"].setdefault(day_key, _empty_day())
            day["queries"] = int(day.get("queries", 0)) + 1
            by_mode = day.setdefault("queries_by_mode", {name: 0 for name in MODES})
            for name in MODES:
                by_mode.setdefault(name, 0)
            if mode in by_mode:
                by_mode[mode] = int(by_mode[mode]) + 1

            label = source.strip().lower() if isinstance(source, str) else ""
            if not SOURCE.fullmatch(label):
                label = "direct"
            by_source = day.setdefault("queries_by_source", {})
            named_sources = by_source.keys() - {"direct", "other"}
            if label not in by_source and label != "direct" and len(named_sources) >= MAX_SOURCES:
                label = "other"
            by_source[label] = int(by_source.get(label, 0)) + 1

            hashes: list[str] = day.setdefault("player_hashes", [])
            if self.salt and success and player_id:
                digest = self._digest(f"player:{player_id}")
                if digest not in hashes:
                    hashes.append(digest)
            day["distinct_players"] = len(hashes)

            visitor = visitor_id.strip() if isinstance(visitor_id, str) else ""
            returning: list[str] = day.setdefault("returning_visitor_hashes", [])
            if self.salt and VISITOR_ID.fullmatch(visitor):
                digest = self._digest(f"visitor:{visitor}")
                first_seen = payload["visitors"].get(digest)
                if first_seen is None:
                    if len(payload["visitors"]) >= self.max_visitors:
                        remove_count = max(1, self.max_visitors // 10)
                        oldest = sorted(
                            payload["visitors"],
                            key=lambda key: (payload["visitors"][key], key),
                        )[:remove_count]
                        for key in oldest:
                            del payload["visitors"][key]
                    payload["visitors"][digest] = day_key
                elif first_seen < day_key and digest not in returning:
                    returning.append(digest)
            day["returning_visitors"] = len(returning)
            self._save(payload)

    def _digest(self, value: str) -> str:
        assert self.salt is not None
        return hmac.new(self.salt.encode(), value.encode(), "sha256").hexdigest()

    def _load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"key_id": self.key_id, "visitors": {}, "days": {}}
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("visitors"), dict)
            or not isinstance(payload.get("days"), dict)
            or (
                "salt" in payload
                and (not isinstance(payload["salt"], str) or len(payload["salt"]) < 16)
            )
            or ("salt" not in payload and "key_id" not in payload)
        ):
            raise ValueError("Invalid usage statistics file")
        if "salt" in payload or payload["key_id"] != self.key_id:
            payload.pop("salt", None)
            payload["key_id"] = self.key_id
            payload["visitors"] = {}
            today = datetime.now(UTC).date().isoformat()
            for date, day in payload["days"].items():
                day["player_hashes"] = []
                day["returning_visitor_hashes"] = []
                if date == today:
                    day["distinct_players"] = 0
                    day["returning_visitors"] = 0
        return payload

    def _save(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(payload, file, separators=(",", ":"), sort_keys=True)
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
