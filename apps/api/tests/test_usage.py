import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas.scores import Player, ScoresResponse
from app.services.osu_client import ServiceError
from app.services.usage import UsageStats


def _scores(mode="mania", user_id=123, username="SecretPlayerZZ"):
    return ScoresResponse(
        mode=mode,
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
    stats = UsageStats(tmp_path / "usage.json")
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
    assert day["queries"] == 5
    assert day["distinct_players"] == 2
    assert day["queries_by_mode"] == {"osu": 1, "taiko": 1, "fruits": 1, "mania": 2}
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
