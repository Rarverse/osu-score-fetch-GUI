import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas.scores import Player, ScoresResponse
from app.services.cache import JsonCache, normalize_player, not_found_cache_key, score_cache_key


@pytest.mark.parametrize("digit", ["0", "9"])
def test_long_numeric_player_does_not_crash_normalization(tmp_path, digit):
    assert normalize_player("0" * 5000 + "123") == "123"
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    response = TestClient(app, raise_server_exceptions=False).get(
        f"/api/v1/players/{digit * 5000}/scores"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PLAYER"


@pytest.mark.parametrize(
    "entry",
    [
        {"created_at": 100, "data": []},
        {"created_at": 100, "data": "corrupt"},
        {"created_at": float("inf"), "data": {}},
        {"created_at": 10**400, "data": {}},
        {"created_at": 200, "data": {}},
    ],
)
def test_invalid_cache_envelope_is_a_miss(tmp_path, monkeypatch, entry):
    monkeypatch.setattr("app.services.cache.time.time", lambda: 100)
    key = score_cache_key("player")
    (tmp_path / f"{key}.json").write_text(json.dumps(entry))
    assert JsonCache(tmp_path, ttl=60).get(key) is None


@pytest.mark.parametrize("bad_data", [{}, {"player": {}}, {"fetched_at": "invalid"}, "naive"])
@pytest.mark.parametrize("negative_cache", [False, True])
def test_invalid_cache_is_refetched_and_repaired(tmp_path, bad_data, negative_cache):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    key = score_cache_key("player")
    calls = []

    def fetch(name, mode):
        calls.append((name, mode))
        return ScoresResponse(
            mode=mode or "mania",
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
    if bad_data == "naive":
        bad_data = fetch("player", "mania").model_dump(mode="json")
        bad_data["fetched_at"] = datetime.now().isoformat()
        calls.clear()
    if negative_cache:
        app.state.not_found.set(not_found_cache_key("player"), bad_data)
    else:
        app.state.cache.set(key, bad_data)
    client = TestClient(app, raise_server_exceptions=False)
    url = "/api/v1/players/Player/scores"
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    assert response.json()["player"]["user_id"] == 123
    assert client.get(url).headers["X-Cache"] == "HIT"
    assert calls == [("player", None)]
