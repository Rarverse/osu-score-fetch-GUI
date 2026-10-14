from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.client_ip import client_ip
from app.config import Settings
from app.main import create_app
from app.schemas.scores import Player, ScoresResponse


def test_forwarded_for_is_taken_from_the_right_when_the_peer_is_trusted():
    trusted = "172.31.210.10, 127.0.0.1, 172.31.210.1"
    assert client_ip("172.31.210.10", "203.0.113.10", trusted) == "203.0.113.10"
    assert client_ip("172.31.210.10", "9.9.9.9, 203.0.113.10", trusted) == "203.0.113.10"
    assert (
        client_ip("172.31.210.1", "9.9.9.9, 203.0.113.50, 172.31.210.1", trusted) == "203.0.113.50"
    )
    assert client_ip("172.31.210.10", "203.0.113.8:54432", trusted) == "203.0.113.8"
    assert client_ip("10.1.2.3", "203.0.113.10", "10.1.2.0/24") == "203.0.113.10"


def test_spoofed_forwarded_for_is_ignored_from_an_untrusted_peer():
    trusted = "172.31.210.10"
    assert client_ip("203.0.113.77", "198.51.100.9", trusted) == "203.0.113.77"
    assert client_ip("testclient", "203.0.113.10", trusted) == "testclient"
    assert client_ip("172.31.210.10", None, trusted) == "172.31.210.10"
    assert client_ip("172.31.210.10", "   ", trusted) == "172.31.210.10"
    assert client_ip(None, "203.0.113.10", trusted) == "unknown"


def _scores() -> ScoresResponse:
    return ScoresResponse(
        player=Player(
            user_id=1,
            username="Player",
            country="CN",
            avatar_url="",
            pp=1,
            global_rank=None,
            hit_accuracy=100,
        ),
        scores=[],
        fetched_at=datetime.now(UTC),
    )


def test_api_rate_limit_buckets_follow_forwarded_ip_only_for_a_trusted_peer(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            rate_limit_per_ip=2,
            rate_limit_per_player=100,
            forwarded_allow_ips="testclient",
        )
    )
    app.state.osu.get_user_scores = lambda name, mode: _scores()
    client = TestClient(app)
    first = {"X-Forwarded-For": "9.9.9.9, 203.0.113.10"}
    assert client.get("/api/v1/players/alpha/scores", headers=first).status_code == 200
    assert client.get("/api/v1/players/alpha-2/scores", headers=first).status_code == 200
    limited = client.get("/api/v1/players/alpha-3/scores", headers=first)
    assert limited.status_code == 429
    other = client.get(
        "/api/v1/players/beta/scores",
        headers={"X-Forwarded-For": "203.0.113.20"},
    )
    assert other.status_code == 200


def test_api_ignores_spoofed_forwarded_for_from_an_untrusted_peer(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            rate_limit_per_ip=2,
            rate_limit_per_player=100,
            forwarded_allow_ips="172.31.210.10",
        )
    )
    app.state.osu.get_user_scores = lambda name, mode: _scores()
    client = TestClient(app)
    assert (
        client.get(
            "/api/v1/players/one/scores",
            headers={"X-Forwarded-For": "203.0.113.10"},
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/players/two/scores",
            headers={"X-Forwarded-For": "203.0.113.20"},
        ).status_code
        == 200
    )
    limited = client.get(
        "/api/v1/players/three/scores",
        headers={"X-Forwarded-For": "203.0.113.30"},
    )
    assert limited.status_code == 429
