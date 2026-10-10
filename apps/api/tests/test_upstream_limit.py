from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest
import requests
from fastapi.testclient import TestClient
from pydantic import ValidationError
from requests.adapters import HTTPAdapter

from app.config import Settings
from app.main import create_app
from app.services.osu_client import ServiceError, TimeoutAdapter
from app.services.rate_limit import UpstreamBusy, UpstreamLimiter


@pytest.fixture
def clock(monkeypatch):
    state = {"now": 0.0}
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", lambda: state["now"])

    def sleep(seconds):
        state["now"] += seconds

    monkeypatch.setattr("app.services.rate_limit.time.sleep", sleep)
    return state


def test_global_http_budget_is_paced_and_never_exceeds_60(clock):
    limiter = UpstreamLimiter(60)
    for _ in range(60):
        limiter.acquire()
    assert list(limiter.requests) == list(range(60))
    with pytest.raises(UpstreamBusy) as failure:
        limiter.acquire()
    assert failure.value.retry_after == 1
    assert len(limiter.requests) == 60
    clock["now"] = 60
    limiter.acquire()
    assert len(limiter.requests) == 60
    assert limiter.requests[-1] == 60


def test_whole_query_headroom_and_lower_configured_limit(clock):
    limiter = UpstreamLimiter(6)
    for _ in range(4):
        limiter.acquire()
    assert clock["now"] == 30
    with pytest.raises(UpstreamBusy) as failure:
        limiter.ensure_capacity(3)
    assert failure.value.retry_after == 30
    limiter.ensure_capacity(2)


@pytest.mark.parametrize("value", [2, 61, 1200])
def test_settings_reject_unsafe_upstream_limits(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, osu_requests_per_minute=value)


def test_oauth_and_score_http_requests_share_budget_and_429_cooldown(clock, monkeypatch):
    limiter = UpstreamLimiter(60)
    oauth, api = TimeoutAdapter(limiter), TimeoutAdapter(limiter)
    responses = []

    def send(self, request, **kwargs):
        assert kwargs["timeout"] == (5, 20)
        responses.append(request.url)
        response = requests.Response()
        response.status_code = 429 if len(responses) == 3 else 200
        response.headers["Retry-After"] = "120"
        response._content = b"{}"
        response._content_consumed = True
        return response

    monkeypatch.setattr(HTTPAdapter, "send", send)
    oauth.send(requests.Request("POST", "https://osu.ppy.sh/oauth/token").prepare())
    api.send(requests.Request("GET", "https://osu.ppy.sh/api/v2/users/123/mania").prepare())
    with pytest.raises(UpstreamBusy) as failure:
        api.send(
            requests.Request("GET", "https://osu.ppy.sh/api/v2/users/123/scores/best").prepare()
        )
    assert failure.value.retry_after == 120
    with pytest.raises(UpstreamBusy):
        oauth.send(requests.Request("POST", "https://osu.ppy.sh/oauth/token").prepare())
    assert len(responses) == 3  # No network request during the cooldown.


def test_retry_after_date_and_invalid_values(clock):
    limiter = UpstreamLimiter(60)
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=120), usegmt=True)
    assert 119 <= limiter.defer(future) <= 120
    assert limiter.defer("invalid") >= 119  # A shorter cooldown cannot clear the existing one.
    assert UpstreamLimiter(60).defer(None) == 60
    assert UpstreamLimiter(60).defer("nan") == 60


def test_busy_contract_has_retry_after_and_does_not_call_upstream(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    app.state.fetch_lock.acquire()
    try:
        response = TestClient(app).get("/api/v1/players/Player/scores")
    finally:
        app.state.fetch_lock.release()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVER_BUSY"
    assert response.headers["Retry-After"] == "3"


def test_upstream_busy_contract(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))

    def fetch(name, mode):
        raise ServiceError(503, "UPSTREAM_BUSY", "busy", retry_after=60)

    app.state.osu.get_user_scores = fetch
    response = TestClient(app).get("/api/v1/players/Player/scores")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPSTREAM_BUSY"
    assert response.headers["Retry-After"] == "60"
