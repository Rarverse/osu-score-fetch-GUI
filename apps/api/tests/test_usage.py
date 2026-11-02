import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.schemas.scores import Player, ScoresResponse
from app.services.osu_client import ServiceError
from app.services.usage import UsageStats

SECRET = "test-only-statistics-secret-000001"


def _scores(mode="mania", user_id=123, username="SecretPlayerZZ"):
    return ScoresResponse(
        mode=mode or "mania",
        player=Player(
            user_id=user_id,
            username=username,
            country="CN",
            avatar_url="",
            pp=100,
            global_rank=None,
            hit_accuracy=99,
        ),
        scores=[],
        fetched_at=datetime.now(UTC),
    )


def test_returning_visitor_is_counted_on_a_later_day_only(tmp_path, monkeypatch):
    stats = UsageStats(tmp_path / "usage.json", salt="test-only-statistics-secret-000001")
    current = {"day": "2026-10-14"}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            year, month, day = (int(part) for part in current["day"].split("-"))
            return cls(year, month, day, tzinfo=tz)

    monkeypatch.setattr("app.services.usage.datetime", Clock)
    visitor = "visitor-aaa-0001"
    stats.record(mode="mania", success=True, player_id="998877", visitor_id=visitor)
    stats.record(mode="mania", success=True, player_id="998877", visitor_id=visitor)
    stats.record(mode="osu", success=False, player_id="998877", visitor_id="no")
    payload = json.loads((tmp_path / "usage.json").read_text())
    day = payload["days"]["2026-10-14"]
    assert day["queries"] == 3
    assert day["distinct_players"] == 1
    assert day["queries_by_mode"]["mania"] == 2
    assert day["queries_by_mode"]["osu"] == 1
    assert day["returning_visitors"] == 0
    raw = (tmp_path / "usage.json").read_text()
    assert visitor not in raw
    assert "998877" not in raw

    current["day"] = "2026-10-15"
    stats.record(mode="taiko", success=False, player_id=None, visitor_id=visitor)
    stats.record(mode="taiko", success=False, player_id=None, visitor_id=visitor)
    payload = json.loads((tmp_path / "usage.json").read_text())
    later = payload["days"]["2026-10-15"]
    assert later["returning_visitors"] == 1
    assert later["distinct_players"] == 0
    assert later["queries"] == 2
    assert later["queries_by_mode"]["taiko"] == 2
    assert visitor not in (tmp_path / "usage.json").read_text()


def test_usage_retention_and_visitor_cap_are_bounded(tmp_path, monkeypatch):
    stats = UsageStats(
        tmp_path / "usage.json",
        retention_days=2,
        max_visitors=3,
        salt="test-only-statistics-secret-000001",
    )
    current = {"day": "2026-10-14"}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            year, month, day = (int(part) for part in current["day"].split("-"))
            return cls(year, month, day, tzinfo=tz)

    monkeypatch.setattr("app.services.usage.datetime", Clock)
    for index in range(4):
        stats.record(
            mode="mania",
            success=True,
            player_id=str(index),
            visitor_id=f"visitor-{index:04d}",
        )

    payload = json.loads((tmp_path / "usage.json").read_text())
    assert len(payload["visitors"]) <= 3
    assert list(payload["days"]) == ["2026-10-14"]

    current["day"] = "2026-10-16"
    stats.record(mode="osu", success=False, player_id=None, visitor_id="visitor-new")
    payload = json.loads((tmp_path / "usage.json").read_text())
    assert list(payload["days"]) == ["2026-10-16"]
    assert all(first_seen >= "2026-10-15" for first_seen in payload["visitors"].values())


def test_rejected_requests_do_not_persist_visitor_ids(tmp_path):
    stats_path = tmp_path / "stats" / "usage.json"
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path / "cache",
            stats_path=stats_path,
            rate_limit_per_player=1,
        )
    )
    app.state.osu.get_user_scores = lambda *_args: _scores()
    client = TestClient(app)

    rejected = client.get(
        f"/api/v1/players/{'x' * 33}/scores",
        headers={"X-Visitor-Id": "rejected-visitor-0001"},
    )
    assert rejected.status_code == 422
    incomplete = client.get(
        "/api/v1/players/incomplete/scores",
        headers={
            "X-Visitor-Id": "rejected-visitor-0002",
            "X-Osu-Client-Id": "123",
        },
    )
    assert incomplete.status_code == 422
    assert not stats_path.exists()

    accepted = client.get(
        "/api/v1/players/accepted/scores",
        headers={"X-Visitor-Id": "accepted-visitor-0001"},
    )
    assert accepted.status_code == 200
    limited = client.get(
        "/api/v1/players/accepted/scores?mode=osu",
        headers={"X-Visitor-Id": "rejected-visitor-0003"},
    )
    assert limited.status_code == 429

    payload = json.loads(stats_path.read_text())
    assert len(payload["visitors"]) == 1
    assert next(iter(payload["days"].values()))["queries"] == 1


def test_api_counts_distinct_players_only_for_successful_queries(tmp_path):
    stats_path = tmp_path / "stats" / "usage.json"
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path / "cache",
            stats_path=stats_path,
            rate_limit_per_player=1,
            osu_client_id=None,
            osu_client_secret=None,
        )
    )

    def fetch(name, mode):
        if name == "missingplayerzz":
            raise ServiceError(404, "PLAYER_NOT_FOUND", "未找到该玩家，请检查用户名或 ID。")
        if name == "brokenplayerzz":
            raise ServiceError(502, "UPSTREAM_ERROR", "osu! 服务暂时无法访问，请稍后重试。")
        user_id = 123 if name == "secretplayerzz" else 456
        return _scores(mode, user_id, "SecretPlayerZZ" if user_id == 123 else "OtherPlayerZZ")

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    headers = {"X-Visitor-Id": "11111111-2222-4333-8444-555555555555"}
    ok = client.get("/api/v1/players/SecretPlayerZZ/scores", headers=headers)
    assert ok.status_code == 200
    limited = client.get("/api/v1/players/SecretPlayerZZ/scores?mode=osu", headers=headers)
    assert limited.status_code == 429
    missing = client.get("/api/v1/players/MissingPlayerZZ/scores?mode=fruits", headers=headers)
    assert missing.status_code == 404
    broken = client.get("/api/v1/players/BrokenPlayerZZ/scores?mode=taiko", headers=headers)
    assert broken.status_code == 502
    other = client.get("/api/v1/players/OtherPlayerZZ/scores", headers=headers)
    assert other.status_code == 200

    payload = json.loads(stats_path.read_text())
    day = next(iter(payload["days"].values()))
    assert day["queries"] == 4
    assert day["distinct_players"] == 2
    assert day["queries_by_mode"] == {"osu": 0, "taiko": 1, "fruits": 1, "mania": 2}
    assert day["returning_visitors"] == 0
    raw = stats_path.read_text()
    for secret in (
        "SecretPlayerZZ",
        "MissingPlayerZZ",
        "BrokenPlayerZZ",
        "OtherPlayerZZ",
        "11111111-2222-4333-8444-555555555555",
        "testclient",
        "127.0.0.1",
    ):
        assert secret not in raw

    allowed = client.options(
        "/api/v1/players/SecretPlayerZZ/scores",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Visitor-Id",
        },
    )
    assert allowed.status_code == 200
    assert "x-visitor-id" in allowed.headers["access-control-allow-headers"].lower()


def test_secret_is_external_and_deduplication_survives_restart(tmp_path):
    path = tmp_path / "usage.json"
    for _ in range(2):
        UsageStats(path, salt=SECRET).record(
            mode="osu", success=True, player_id="123", visitor_id="visitor-123"
        )
    raw = path.read_text()
    payload = json.loads(raw)
    day = next(iter(payload["days"].values()))
    assert SECRET not in raw
    assert "salt" not in payload
    assert day["queries"] == 2
    assert day["distinct_players"] == 1
    assert len(payload["visitors"]) == 1


@pytest.mark.parametrize("salt", [None, SECRET])
def test_startup_migrates_legacy_stats_without_waiting_for_query(tmp_path, salt):
    path = tmp_path / "usage.json"
    today = datetime.now(UTC).date().isoformat()
    legacy_day = {
        "queries": 9,
        "queries_by_mode": {"osu": 9},
        "distinct_players": 5,
        "returning_visitors": 2,
        "player_hashes": ["legacy-player-hash"],
        "returning_visitor_hashes": ["legacy-visitor-hash"],
    }
    path.write_text(
        json.dumps(
            {
                "salt": "legacy-salt-0123456789",
                "visitors": {"legacy-visitor-hash": "2020-01-01"},
                "days": {"2020-01-01": legacy_day, today: legacy_day},
            }
        )
    )
    app = create_app(
        Settings(
            _env_file=None, cache_path=tmp_path / "cache", stats_path=path, stats_hash_salt=salt
        )
    )
    with TestClient(app):
        payload = json.loads(path.read_text())
    assert "legacy" not in path.read_text()
    assert "salt" not in payload
    assert payload["visitors"] == {}
    assert payload["days"]["2020-01-01"]["distinct_players"] == 5
    assert payload["days"]["2020-01-01"]["returning_visitors"] == 2
    assert payload["days"][today]["queries"] == 9
    assert payload["days"][today]["queries_by_mode"] == {"osu": 9}
    assert payload["days"][today]["distinct_players"] == 0
    assert payload["days"][today]["returning_visitors"] == 0


@pytest.mark.parametrize("replacement", [None, "a-different-statistics-secret-0001"])
def test_secret_rotation_clears_old_hashes_and_keeps_query_counts(tmp_path, replacement):
    path = tmp_path / "usage.json"
    UsageStats(path, salt=SECRET).record(
        mode="osu", success=True, player_id="123", visitor_id="visitor-123"
    )
    old = json.loads(path.read_text())
    old_hash = next(iter(old["days"].values()))["player_hashes"][0]
    stats = UsageStats(path, salt=replacement)
    stats.migrate()
    stats.record(mode="osu", success=True, player_id="123", visitor_id="visitor-123")
    payload = json.loads(path.read_text())
    day = next(iter(payload["days"].values()))
    assert old_hash not in path.read_text()
    assert day["queries"] == 2
    assert day["distinct_players"] == (1 if replacement else 0)


def test_missing_secret_keeps_aggregates_without_identity_hashes(tmp_path):
    path = tmp_path / "usage.json"
    UsageStats(path).record(mode="mania", success=True, player_id="123", visitor_id="visitor-123")
    payload = json.loads(path.read_text())
    day = next(iter(payload["days"].values()))
    assert payload["key_id"] is None
    assert payload["visitors"] == {}
    assert day["queries"] == 1
    assert day["player_hashes"] == []
    assert day["returning_visitor_hashes"] == []


def test_short_stats_secret_is_rejected_and_valid_secret_is_redacted():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, stats_hash_salt="too-short")
    assert SECRET not in repr(Settings(_env_file=None, stats_hash_salt=SECRET))


def test_source_counts_include_cache_hits_but_not_rate_limited_requests(tmp_path):
    path = tmp_path / "usage.json"
    app = create_app(
        Settings(
            _env_file=None, cache_path=tmp_path / "cache", stats_path=path, rate_limit_per_player=1
        )
    )
    app.state.osu.get_user_scores = lambda *_args: _scores()
    client = TestClient(app)
    url = "/api/v1/players/Player/scores"
    for source in ("bili", " BILI ", "youtube", "", "bad/source"):
        assert client.get(url, params={"from": source}).status_code == 200
    assert client.get(url, params={"from": "blocked", "mode": "osu"}).status_code == 429
    day = next(iter(json.loads(path.read_text())["days"].values()))
    assert day["queries"] == 5
    assert day["queries_by_source"] == {"bili": 2, "youtube": 1, "direct": 2}


def test_source_labels_and_number_of_buckets_are_bounded(tmp_path):
    path = tmp_path / "usage.json"
    stats = UsageStats(path)
    sources = [*(f"source-{index}" for index in range(70)), "", "x" * 33, "bili\nextra"]
    for source in sources:
        stats.record(mode=None, success=False, player_id=None, visitor_id=None, source=source)
    counts = next(iter(json.loads(path.read_text())["days"].values()))["queries_by_source"]
    assert len(counts) == 66
    assert counts["other"] == 6
    assert counts["direct"] == 3
    assert sum(counts.values()) == len(sources)
