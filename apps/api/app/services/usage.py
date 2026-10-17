import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from app.schemas.scores import Ruleset

# Anonymous browser ids are UUIDs. Reject anything else so the file cannot grow from junk.
VISITOR_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
MODES: tuple[Ruleset, ...] = ("osu", "taiko", "fruits", "mania")


def _empty_day() -> dict:
    return {
        "queries": 0,
        "distinct_players": 0,
        "queries_by_mode": {mode: 0 for mode in MODES},
        "returning_visitors": 0,
        "player_hashes": [],
        "returning_visitor_hashes": [],
    }


class UsageStats:
    """Daily counts for one worker. The file stores salted hashes, never raw ids."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = Lock()

    def record(
        self,
        *,
        mode: Ruleset | None,
        success: bool,
        player_id: str | None,
        visitor_id: str | None,
    ) -> None:
        with self.lock:
            payload = self._load()
            day_key = datetime.now(UTC).date().isoformat()
            day = payload["days"].setdefault(day_key, _empty_day())
            day["queries"] = int(day.get("queries", 0)) + 1
            by_mode = day.setdefault("queries_by_mode", {name: 0 for name in MODES})
            for name in MODES:
                by_mode.setdefault(name, 0)
            if mode in by_mode:
                by_mode[mode] = int(by_mode[mode]) + 1

            hashes: list[str] = day.setdefault("player_hashes", [])
            if success and player_id:
                digest = self._digest(payload["salt"], f"player:{player_id}")
                if digest not in hashes:
                    hashes.append(digest)
            day["distinct_players"] = len(hashes)

            visitor = visitor_id.strip() if isinstance(visitor_id, str) else ""
            returning: list[str] = day.setdefault("returning_visitor_hashes", [])
            if VISITOR_ID.fullmatch(visitor):
                digest = self._digest(payload["salt"], f"visitor:{visitor}")
                first_seen = payload["visitors"].get(digest)
                if first_seen is None:
                    payload["visitors"][digest] = day_key
                elif first_seen < day_key and digest not in returning:
                    returning.append(digest)
            day["returning_visitors"] = len(returning)
            self._save(payload)

    def _digest(self, salt: str, value: str) -> str:
        return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()

    def _load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"salt": os.urandom(16).hex(), "visitors": {}, "days": {}}
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("salt"), str)
            or len(payload["salt"]) < 16
            or not isinstance(payload.get("visitors"), dict)
            or not isinstance(payload.get("days"), dict)
        ):
            raise ValueError("Invalid usage statistics file")
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
