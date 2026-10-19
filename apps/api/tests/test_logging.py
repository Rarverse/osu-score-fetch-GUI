import io
import json
import logging

import pytest
import requests
from fastapi.testclient import TestClient
from requests.adapters import HTTPAdapter
from test_images import AVATAR, PNG, upstream
from test_usage import _scores

from app.config import Settings
from app.logging_setup import JsonFormatter, TextFormatter, configure_logging, request_id
from app.main import create_app
from app.services.cache import JsonCache
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
    assert sum(handler.name == "app_console" for handler in logging.getLogger("app").handlers) == 1


def test_readable_formatter_explains_errors_without_losing_searchable_fields():
    record = logging.LogRecord(
        "app.main", logging.WARNING, __file__, 1, "request_completed", (), None
    )
    record.fields = {
        "status": 503,
        "error_code": "UPSTREAM_BUSY",
        "retry_after": "60",
        "duration_ms": 42.5,
    }
    token = request_id.set("test-request")
    try:
        text = TextFormatter().format(record)
        data = json.loads(JsonFormatter().format(record))
    finally:
        request_id.reset(token)
    assert "Request completed with an error" in text
    assert "request_id=test-request" in text
    assert "retry_after=60" in text
    assert "duration_ms=42.5" in text
    assert "event=request_completed" in text
    assert "Wait" in text
    assert data["message"] == "Request completed with an error"
    assert data["error_reason"]
    assert data["next_step"]
    assert not any("\u4e00" <= char <= "\u9fff" for char in text)


def test_query_logs_explain_cache_misses_hits_and_returned_scores(tmp_path, logs):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    app.state.osu.get_user_scores = lambda *_args: _scores("mania", 123, "private-player")
    client = TestClient(app)
    for expected_cache in ("MISS", "HIT"):
        response = client.get("/api/v1/players/private-player/scores?limit=20")
        records = [
            item
            for item in entries(logs)
            if item.get("request_id") == response.headers["X-Request-ID"]
        ]
        assert records[0]["event"] == "request_started"
        assert (
            next(item for item in records if item["event"] == "scores_query_started")["mode"]
            == "auto"
        )
        assert (
            next(item for item in records if item["event"] == "scores_cache_lookup")["cache"]
            == expected_cache
        )
        ready = next(item for item in records if item["event"] == "scores_ready")
        assert ready["mode"] == "mania"
        assert ready["limit"] == 20
        assert ready["score_count"] == len(response.json()["scores"])
        assert records[-1]["event"] == "request_completed"
        assert records[-1]["cache_ttl"]
    assert "private-player" not in logs.getvalue()


def test_unexpected_errors_include_safe_code_locations(tmp_path, logs):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))

    def fail(*_args):
        raise RuntimeError("secret-should-never-appear")

    app.state.osu.get_user_scores = fail
    response = TestClient(app).get("/api/v1/players/Player/scores")
    assert response.status_code == 500
    record = next(item for item in entries(logs) if item["event"] == "request_failed")
    assert record["error_type"] == "RuntimeError"
    assert any("routers/players.py:" in frame for frame in record["error_trace"])
    assert "secret-should-never-appear" not in logs.getvalue()


def test_log_configuration_can_switch_format_and_level_without_duplicate_output():
    try:
        configure_logging("json", "DEBUG")
        logger = logging.getLogger("app")
        handlers = [handler for handler in logger.handlers if handler.name == "app_console"]
        assert len(handlers) == 1
        assert type(handlers[0].formatter) is JsonFormatter
        assert logger.level == logging.DEBUG
        configure_logging("text", "INFO")
        assert len([handler for handler in logger.handlers if handler.name == "app_console"]) == 1
        assert isinstance(handlers[0].formatter, TextFormatter)
        assert logger.level == logging.INFO
    finally:
        configure_logging()


@pytest.mark.parametrize(
    ("path", "phase"),
    [
        ("/oauth/token", "oauth"),
        ("/api/v2/users/123/mania", "player"),
        ("/api/v2/users/123/scores/best", "scores"),
    ],
)
def test_upstream_stages_are_distinguishable_without_logging_urls(logs, monkeypatch, path, phase):
    def send(*_args, **_kwargs):
        response = requests.Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(HTTPAdapter, "send", send)
    prepared = requests.Request("GET", f"https://osu.ppy.sh{path}?secret=private-query").prepare()
    TimeoutAdapter(UpstreamLimiter(60)).send(prepared)
    record = entries(logs)[-1]
    assert record["phase"] == phase
    assert record["duration_ms"] >= 0
    assert record["wait_ms"] >= 0
    assert "private-query" not in logs.getvalue()
    assert "https://" not in logs.getvalue()


def test_corrupt_and_unreadable_cache_logs_keep_data_and_paths_private(tmp_path, logs, monkeypatch):
    key = "private-cache-key"
    (tmp_path / f"{key}.json").write_text("private-corrupt-data")
    cache = JsonCache(tmp_path, 60)
    assert cache.get(key) is None
    assert entries(logs)[-1]["event"] == "cache_entry_invalid"

    def denied(*_args, **_kwargs):
        raise PermissionError(13, "private-permission-message", "private-cache-path")

    monkeypatch.setattr("pathlib.Path.read_text", denied)
    assert cache.get(key) is None
    record = entries(logs)[-1]
    assert record["event"] == "cache_read_failed"
    assert record["error_errno"] == 13
    assert record["error_type"] == "PermissionError"
    assert "private-" not in logs.getvalue()


def test_artwork_logs_report_size_and_failure_reason_without_the_url(tmp_path, logs, monkeypatch):
    upstream(monkeypatch)
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    client = TestClient(app)
    assert client.get("/api/v1/images", params={"url": AVATAR}).status_code == 200
    record = next(item for item in entries(logs) if item["event"] == "image_http_completed")
    assert record["bytes"] == len(PNG)
    assert record["media_type"] == "image/png"
    assert record["duration_ms"] >= 0
    upstream(monkeypatch, media_type="text/html; private-content-type")
    response = client.get("/api/v1/images", params={"url": "https://a.ppy.sh/3"})
    assert response.status_code == 502
    record = next(item for item in entries(logs) if item["event"] == "image_http_failed")
    assert record["reason"] == "unsupported_type"
    assert record["reason_detail"]
    assert "a.ppy.sh" not in logs.getvalue()
    assert "private-content-type" not in logs.getvalue()
