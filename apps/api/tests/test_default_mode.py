from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas.scores import Player, ScoresResponse
from app.services.cache import score_cache_key
from app.services.osu_client import OsuClient


@pytest.mark.parametrize("preferred", ["osu", "taiko", "fruits", "mania"])
def test_default_mode_uses_profile_statistics_and_scores(monkeypatch, preferred):
    service = OsuClient(Settings(_env_file=None))
    calls = []

    def user(name, *, mode):
        assert mode is None
        return SimpleNamespace(
            id=123,
            username="Player",
            country_code="CN",
            avatar_url="",
            playmode=preferred,
            statistics=SimpleNamespace(pp=1234, global_rank=10, hit_accuracy=98.5),
        )

    def scores(user_id, score_type, **kwargs):
        calls.append((user_id, kwargs["mode"].value, kwargs["limit"]))
        return []

    monkeypatch.setattr(
        service, "get_ossapi_client", lambda: SimpleNamespace(user=user, user_scores=scores)
    )
    result = service.get_user_scores("Player")
    assert result.mode == preferred
    assert result.player.pp == 1234
    assert calls == [(123, preferred, 50)]


def test_manual_mode_does_not_poison_default_and_default_populates_resolved_cache(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path, rate_limit_per_player=20))
    calls = []

    def fetch(name, mode):
        calls.append(mode)
        return ScoresResponse(
            mode=mode or "taiko",
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
    url = "/api/v1/players/Player/scores"
    assert client.get(url + "?mode=mania").json()["mode"] == "mania"
    default = client.get(url)
    assert default.json()["mode"] == "taiko"
    assert default.headers["X-Cache"] == "MISS"
    assert client.get("/api/v1/players/123/scores?limit=50").headers["X-Cache"] == "HIT"
    assert client.get(url + "?mode=taiko&limit=50").headers["X-Cache"] == "HIT"
    assert calls == ["mania", None]
    assert score_cache_key("Player") != score_cache_key("Player", "mania")
