import io
import json
import logging

import pytest
import requests
from fastapi.testclient import TestClient
from requests.adapters import HTTPAdapter
from test_usage import _scores

from app.config import Settings
from app.logging_setup import JsonFormatter, configure_logging, request_id
from app.main import create_app
from app.services.osu_client import ServiceError, TimeoutAdapter
from app.services.rate_limit import UpstreamBusy, UpstreamLimiter


@pytest.fixture
def logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("app")
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        handler.close()


def entries(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_request_logs_link_to_response_without_credentials_or_player_data(tmp_path, logs):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    app.state.osu.get_user_scores = lambda *_args: _scores("mania", 123, "private-player")
    client = TestClient(app)
    response = client.get(
        "/api/v1/players/private-player/scores?private=test-query",
        headers={
            "X-Osu-Client-Id": "987654321",
            "X-Osu-Client-Secret": "test-secret-do-not-log",
            "X-Visitor-Id": "test-visitor-do-not-log",
            "X-Forwarded-For": "203.0.113.42",
        },
    )
    assert response.status_code == 200
    result = next(item for item in entries(logs) if item["event"] == "request_completed")
    assert result["request_id"] == response.headers["X-Request-ID"]
    assert result["route"] == "/api/v1/players/{username}/scores"
    assert result["status"] == 200
    assert result["cache"] == "MISS"
    assert result["credentials"] == "custom"
    assert result["duration_ms"] >= 0
    raw = logs.getvalue()
    for private in (
        "private-player",
        "test-query",
        "987654321",
        "test-secret-do-not-log",
        "test-visitor-do-not-log",
        "203.0.113.42",
    ):
        assert private not in raw
    assert request_id.get() is None
    second = client.get("/api/v1/players/private-player/scores")
    assert second.headers["X-Request-ID"] != response.headers["X-Request-ID"]


def test_error_and_validation_logs_are_safe_and_include_wait_time(tmp_path, logs):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))

    def busy(*_args):
        raise ServiceError(503, "UPSTREAM_BUSY", "private upstream body", retry_after=60)

    app.state.osu.get_user_scores = busy
    client = TestClient(app)
    response = client.get("/api/v1/players/Player/scores")
    record = entries(logs)[-1]
    assert record["request_id"] == response.headers["X-Request-ID"]
    assert record["error_code"] == "UPSTREAM_BUSY"
    assert record["retry_after"] == "60"
    assert record["status"] == 503
    invalid = client.get(
        "/api/v1/players/Player/scores", headers={"X-Osu-Client-Id": "private-invalid-id"}
    )
    assert invalid.status_code == 422
    assert entries(logs)[-1]["error_code"] == "INVALID_REQUEST"
    client.get("/private-path?secret=private-query")
    assert entries(logs)[-1]["route"] == "unmatched"
    for value in ("private upstream body", "private-invalid-id", "private-path", "private-query"):
        assert value not in logs.getvalue()


def test_health_is_quiet_and_unexpected_failures_are_safe(tmp_path, logs):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert entries(logs) == []

    def fail(*_args):
        raise RuntimeError("private-secret-in-exception")

    app.state.osu.get_user_scores = fail
    response = client.get("/api/v1/players/Player/scores")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private-secret-in-exception" not in logs.getvalue()
    assert entries(logs)[-2]["error_type"] == "RuntimeError"
    assert entries(logs)[-1]["error_code"] == "INTERNAL_ERROR"


def test_wait_logs_distinguish_budget_and_upstream_fallback(logs, monkeypatch):
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", lambda: 100)
    limiter = UpstreamLimiter(3)
    limiter.requests.extend([98, 99, 100])
    with pytest.raises(UpstreamBusy):
        limiter.ensure_capacity(1)
    assert entries(logs)[-1]["reason"] == "budget_exhausted"
    images = UpstreamLimiter(60, budget="images")
    assert images.defer(None) == 60
    record = entries(logs)[-1]
    assert record["event"] == "upstream_rate_limited"
    assert record["budget"] == "images"
    assert record["fallback"] is True
    with pytest.raises(UpstreamBusy):
        images.acquire()
    assert entries(logs)[-1]["reason"] == "upstream_cooldown"


def test_upstream_http_logs_status_without_request_body_or_url(logs, monkeypatch):
    def send(*_args, **_kwargs):
        response = requests.Response()
        response.status_code = 401
        response._content = b"private-token-in-body"
        response.url = "https://osu.ppy.sh/oauth/token?secret=private-query"
        return response

    monkeypatch.setattr(HTTPAdapter, "send", send)
    request = requests.Request(
        "POST", "https://osu.ppy.sh/oauth/token", data={"client_secret": "private-secret"}
    ).prepare()
    with pytest.raises(requests.HTTPError):
        TimeoutAdapter(UpstreamLimiter(60)).send(request)
    record = entries(logs)[-1]
    assert record["event"] == "osu_http_completed"
    assert record["phase"] == "oauth"
    assert record["status"] == 401
    assert "private-" not in logs.getvalue()


def test_logging_configuration_does_not_duplicate_handlers():
    configure_logging()
    configure_logging()
    assert (
        sum(
            isinstance(handler.formatter, JsonFormatter)
            for handler in logging.getLogger("app").handlers
        )
        == 1
    )
