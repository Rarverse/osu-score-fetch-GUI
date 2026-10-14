import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas.scores import Player, ScoresResponse
from app.services.cache import JsonCache, score_cache_key
from app.services.osu_client import OsuClient, ServiceError, structure_scores


def test_cache_key_normalizes_player_and_cannot_escape_path():
    assert score_cache_key(" Player ") == score_cache_key("player")
    assert score_cache_key("000123") == score_cache_key("123")
    assert len(score_cache_key("../../.env")) == 64


def test_cache_expiry_and_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.cache.time.time", lambda: 100)
    cache = JsonCache(tmp_path, ttl=10)
    key = score_cache_key("player")
    cache.set(key, {"pp": 123.4})
    assert cache.get(key) == {"pp": 123.4}
    monkeypatch.setattr("app.services.cache.time.time", lambda: 110)
    assert cache.get(key) is None
    assert (tmp_path / f"{key}.json").exists()  # Expired scores remain stored for retention.
    (tmp_path / f"{key}.json").write_text("broken")
    assert cache.get(key) is None


def test_cache_retention_cleans_old_files_on_activity(tmp_path, monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr("app.services.cache.time.time", lambda: clock["now"])
    cache = JsonCache(tmp_path, ttl=60, retention=7200)
    key = score_cache_key("Player")
    cache.set(key, {"pp": 100})
    path = tmp_path / f"{key}.json"
    os.utime(path, (100, 100))
    clock["now"] = 160
    assert cache.get(key) is None
    assert path.exists()
    clock["now"] = 7300
    assert cache.get(key) is None
    assert not path.exists()


def test_query_refreshes_after_60_seconds_and_cached_queries_bypass_busy_lock(
    tmp_path, monkeypatch
):
    clock = {"now": 100.0}
    monkeypatch.setattr("app.services.cache.time.time", lambda: clock["now"])
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    calls = []

    def fetch(name, mode):
        calls.append(name)
        return ScoresResponse(
            mode=mode,
            player=Player(
                user_id=123,
                username="Player",
                country="CN",
                avatar_url="",
                pp=len(calls),
                global_rank=None,
                hit_accuracy=99,
            ),
            scores=[],
            fetched_at=datetime.now(UTC),
        )

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    url = "/api/v1/players/Player/scores"
    assert client.get(url).json()["player"]["pp"] == 1
    app.state.fetch_lock.acquire()
    try:
        cached = client.get(url + "?limit=50")
        assert cached.status_code == 200
        assert cached.headers["X-Cache"] == "HIT"
        assert 0 <= int(cached.headers["X-Cache-TTL"]) <= 60
    finally:
        app.state.fetch_lock.release()
    clock["now"] = 160
    refreshed = client.get(url)
    assert refreshed.headers["X-Cache"] == "MISS"
    assert refreshed.json()["player"]["pp"] == 2
    assert len(calls) == 2


def test_score_mapping_keeps_unknown_pp_and_mania_fields():
    score = SimpleNamespace(
        id=10,
        beatmap=SimpleNamespace(id=20, version="4K", difficulty_rating=5.2),
        beatmapset=SimpleNamespace(
            title="Song",
            artist="Artist",
            covers=SimpleNamespace(list_2x="https://example.com/cover.jpg"),
        ),
        accuracy=0.9876,
        pp=None,
        rank=SimpleNamespace(value="XH"),
        mods=[SimpleNamespace(acronym="DT")],
        max_combo=1000,
        ended_at=datetime.now(UTC),
    )
    result = structure_scores([score])[0]
    assert result.pp is None
    assert result.rank == "SSH"
    assert result.mods == ["DT"]
    assert result.star_rating == 5.2
    assert result.accuracy == 0.9876


def test_api_cache_validation_and_rate_limit(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path, rate_limit_per_player=2))
    calls = []

    def fetch(name, mode):
        calls.append(name)
        return ScoresResponse(
            player=Player(
                user_id=123,
                username="Player",
                country="CN",
                avatar_url="",
                pp=100,
                global_rank=None,
                hit_accuracy=99,
            ),
            scores=[],
            fetched_at=datetime.now(UTC),
        )

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    url = "/api/v1/players/Player/scores"
    first = client.get(url)
    assert first.status_code == 200 and first.headers["X-Cache"] == "MISS"
    assert client.get(url).headers["X-Cache"] == "HIT"
    assert client.get("/api/v1/players/123/scores").headers["X-Cache"] == "HIT"
    assert len(calls) == 1
    limited = client.get(url)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert client.get(url + "?limit=51").status_code == 422
    assert client.get(url + "?type=recent").status_code == 422


def test_api_error_contract(tmp_path, monkeypatch):
    monkeypatch.delenv("OSU_CLIENT_ID", raising=False)
    monkeypatch.delenv("OSU_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OSU_CLIENT_ID", "1")
    monkeypatch.setenv("OSU_CLIENT_SECRET", "dummy")
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            osu_client_id=None,
            osu_client_secret=None,
        )
    )
    client = TestClient(app)
    assert client.get("/api/v1/players/test/scores").json()["error"]["code"] == "NOT_CONFIGURED"
    for status, code in [(404, "PLAYER_NOT_FOUND"), (502, "UPSTREAM_ERROR")]:

        def fetch(name, mode, status=status, code=code):
            raise ServiceError(status, code, "test error")

        app.state.osu.get_user_scores = fetch
        # A cached 404 is per player, so each contract check uses its own name.
        response = client.get(f"/api/v1/players/contract-{code}/scores")
        assert response.status_code == status
        assert response.json()["error"]["code"] == code


def test_custom_oauth_credentials_are_forwarded_only_with_complete_pair(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    received = []

    def fetch(name, mode, client_id, client_secret):
        received.append((client_id, client_secret))
        return ScoresResponse(
            player=Player(
                user_id=123,
                username="Player",
                country="CN",
                avatar_url="",
                pp=100,
                global_rank=None,
                hit_accuracy=99,
            ),
            scores=[],
            fetched_at=datetime.now(UTC),
        )

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    incomplete = client.get(
        "/api/v1/players/Player/scores",
        headers={"X-Osu-Client-Id": "123"},
    )
    assert incomplete.status_code == 422
    assert incomplete.json()["error"]["code"] == "INVALID_CREDENTIALS"
    response = client.get(
        "/api/v1/players/Player/scores",
        headers={
            "X-Osu-Client-Id": "123",
            "X-Osu-Client-Secret": "private-value",
        },
    )
    assert response.status_code == 200
    assert received == [(123, "private-value")]
    assert "private-value" not in response.text


@pytest.mark.parametrize(
    "upstream_status, expected_status", [(404, 404), (401, 502), (429, 502), (500, 502)]
)
def test_upstream_http_errors_are_mapped_without_leaking_details(
    monkeypatch, upstream_status, expected_status
):
    service = OsuClient(Settings(_env_file=None))
    response = requests.Response()
    response.status_code = upstream_status

    def user(*args, **kwargs):
        raise requests.HTTPError("sensitive upstream details", response=response)

    monkeypatch.setattr(service, "get_ossapi_client", lambda: SimpleNamespace(user=user))
    with pytest.raises(ServiceError) as failure:
        service.get_user_scores("test")
    assert failure.value.status == expected_status
    assert "sensitive" not in failure.value.message


def test_modes_use_separate_cache_entries(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path, rate_limit_per_player=20))
    calls = []

    def fetch(name, mode):
        calls.append(mode)
        return ScoresResponse(
            mode=mode,
            player=Player(
                user_id=123,
                username="Player",
                country="CN",
                avatar_url="",
                pp=100,
                global_rank=None,
                hit_accuracy=99,
            ),
            scores=[],
            fetched_at=datetime.now(UTC),
        )

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    for mode in ["osu", "taiko", "fruits", "mania"]:
        url = f"/api/v1/players/Player/scores?mode={mode}"
        first = client.get(url)
        assert first.status_code == 200
        assert first.json()["mode"] == mode
        assert first.headers["X-Cache"] == "MISS"
        assert client.get(url).headers["X-Cache"] == "HIT"
    assert calls == ["osu", "taiko", "fruits", "mania"]
    assert len({score_cache_key("Player", mode) for mode in calls}) == 4
    assert client.get("/api/v1/players/Player/scores?mode=catch").status_code == 422


@pytest.mark.parametrize("mode", ["osu", "taiko", "fruits", "mania"])
def test_osu_client_uses_selected_mode_for_stats_and_scores(monkeypatch, mode):
    service = OsuClient(Settings(_env_file=None))
    queried_modes = []

    def user(name, *, mode):
        queried_modes.append(mode.value)
        return SimpleNamespace(
            id=123,
            username="Player",
            country_code="CN",
            avatar_url="",
            statistics=SimpleNamespace(pp=100, global_rank=10, hit_accuracy=99),
        )

    def scores(user_id, score_type, **kwargs):
        queried_modes.append(kwargs["mode"].value)
        return []

    monkeypatch.setattr(
        service, "get_ossapi_client", lambda: SimpleNamespace(user=user, user_scores=scores)
    )
    response = service.get_user_scores("Player", mode)
    assert queried_modes == [mode, mode]
    assert response.mode == mode


def test_player_not_found_is_cached_for_every_mode(tmp_path, monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr("app.services.cache.time.time", lambda: clock["now"])
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            negative_cache_ttl=60,
            rate_limit_per_player=10,
            osu_client_id=None,
            osu_client_secret=None,
        )
    )
    calls = []

    def fetch(name, mode):
        calls.append((name, mode))
        raise ServiceError(404, "PLAYER_NOT_FOUND", "未找到该玩家，请检查用户名或 ID。")

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    url = "/api/v1/players/MissingPlayerZZ/scores"
    first = client.get(url)
    assert first.status_code == 404
    assert first.json()["error"]["code"] == "PLAYER_NOT_FOUND"
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["x-cache"] == "MISS"
    assert first.headers["x-cache-ttl"] == "60"
    second = client.get(url + "?mode=osu")
    assert second.status_code == 404
    assert second.json() == first.json()
    assert second.headers["x-cache"] == "HIT"
    assert second.headers["cache-control"] == "no-store"
    assert len(calls) == 1
    stored = "\n".join(path.read_text() for path in tmp_path.rglob("*.json"))
    assert "MissingPlayerZZ" not in stored
    clock["now"] = 1_060
    third = client.get(url)
    assert third.status_code == 404
    assert third.headers["x-cache"] == "MISS"
    assert len(calls) == 2


def test_other_upstream_errors_are_not_negatively_cached(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path, rate_limit_per_player=10))
    calls = []

    def fetch(name, mode):
        calls.append(mode)
        raise ServiceError(502, "UPSTREAM_ERROR", "osu! 服务暂时无法访问，请稍后重试。")

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    url = "/api/v1/players/Player/scores"
    assert client.get(url).status_code == 502
    assert client.get(url).status_code == 502
    assert calls == ["mania", "mania"]
