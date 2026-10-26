import io
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient
from requests.adapters import HTTPAdapter
from test_images import AVATAR, PNG, upstream
from test_usage import _scores

from app.config import Settings
from app.logging_setup import (
    JsonFormatter,
    TextFormatter,
    configure_logging,
    request_id,
    score_query_log,
)
from app.main import create_app
from app.services.cache import JsonCache
from app.services.osu_client import OsuClient, ServiceError, TimeoutAdapter
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


def test_request_logs_link_to_response_without_credentials(tmp_path, logs):
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
    failed = next(item for item in entries(logs) if item["event"] == "request_failed")
    assert failed["error_type"] == "RuntimeError"
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
    for query, expected_cache in (("Private-Player", "MISS"), ("123", "HIT")):
        response = client.get(f"/api/v1/players/{query}/scores?limit=20")
        records = [
            item
            for item in entries(logs)
            if item.get("request_id") == response.headers["X-Request-ID"]
        ]
        assert records[0]["event"] == "request_started"
        started = next(item for item in records if item["event"] == "scores_query_started")
        assert "query" not in started
        assert (
            next(item for item in records if item["event"] == "scores_query_started")["mode"]
            == "auto"
        )
        assert (
            next(item for item in records if item["event"] == "scores_cache_lookup")["cache"]
            == expected_cache
        )
        ready = next(item for item in records if item["event"] == "scores_ready")
        assert "username" not in ready
        assert "user_id" not in ready
        assert "api_slot" not in ready
        assert ready["mode"] == "mania"
        assert ready["limit"] == 20
        assert ready["score_count"] == len(response.json()["scores"])
        assert records[-1]["event"] == "request_completed"
        assert records[-1]["cache_ttl"]
        summaries = [item for item in records if item["event"] == "scores_query_completed"]
        assert len(summaries) == 1
        summary = summaries[0]
        assert "query" not in summary
        assert "username" not in summary
        assert "user_id" not in summary
        assert summary["cache"] == expected_cache
        assert summary["status"] == 200
        assert score_query_log.get() is None
        assert summary["api_slot"] is None
        assert summary["upstream_requests"] == 0  # This test stubs the entire upstream service.
        assert summary["token_refreshed"] is False
        assert summary["duration_ms"] >= 0


@pytest.fixture
def score_transport(monkeypatch):
    from ossapi import Ossapi

    sent = []
    behavior = {"phase": None, "status": 200, "timeout": False}

    def send(_adapter, request, **_kwargs):
        phase = (
            "oauth"
            if request.url.endswith("/oauth/token")
            else "scores"
            if "/scores/" in request.url
            else "player"
        )
        sent.append(phase)
        if phase == behavior["phase"] and behavior["timeout"]:
            raise requests.Timeout("private-network-error")
        response = requests.Response()
        response.status_code = behavior["status"] if phase == behavior["phase"] else 200
        response.request, response.url = request, request.url
        body = (
            {"access_token": "private-access-token", "expires_in": 3600}
            if phase == "oauth"
            else []
            if phase == "scores"
            else {"id": 123}
        )
        response._content = json.dumps(body).encode()
        response._content_consumed = True
        return response

    monkeypatch.setattr(HTTPAdapter, "send", send)
    monkeypatch.setattr(
        Ossapi,
        "_instantiate_type",
        lambda _self, _type, data: (
            []
            if isinstance(data, list)
            else SimpleNamespace(
                id=123,
                username="Player",
                country_code="CN",
                avatar_url="",
                playmode="mania",
                statistics=None,
            )
        ),
    )
    return sent, behavior


@pytest.mark.parametrize("custom", [False, True])
def test_query_summary_counts_real_transport_calls_and_resets_between_requests(
    tmp_path, logs, score_transport, custom
):
    sent, _behavior = score_transport
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            osu_client_id_3=987653,
            osu_client_secret_3="private-site-secret",
        )
    )
    app.state.osu.limiter = Mock()
    headers = {"X-Osu-Client-Id": "987654321", "X-Osu-Client-Secret": "private-custom-secret"}
    client = TestClient(app)
    for path, expected_count in (
        ("Player/scores", 3),
        ("123/scores", 0),
        ("Player/scores?mode=osu", 3 if custom else 2),
    ):
        before = len(sent)
        response = client.get(f"/api/v1/players/{path}", headers=headers if custom else {})
        assert response.status_code == 200
        (summary,) = [
            item
            for item in entries(logs)
            if item["event"] == "scores_query_completed"
            and item["request_id"] == response.headers["X-Request-ID"]
        ]
        assert summary["upstream_requests"] == len(sent) - before == expected_count
        assert summary["token_refreshed"] is (expected_count == 3)
        assert summary["api_slot"] == (3 if expected_count and not custom else None)
        assert summary["credentials"] == ("custom" if custom else "site")
        assert summary["cache"] == ("HIT" if expected_count == 0 else "MISS")
        assert "username" not in summary
        assert "user_id" not in summary
        assert summary["status"] == 200
    for private in ("private-", "98765"):
        assert private not in logs.getvalue()


@pytest.mark.parametrize(
    ("phase", "upstream_status", "timeout", "status", "count", "refreshed", "code"),
    [
        ("oauth", 401, False, 502, 1, False, "UPSTREAM_ERROR"),
        ("player", 404, False, 404, 2, True, "PLAYER_NOT_FOUND"),
        ("scores", 429, False, 503, 3, True, "UPSTREAM_BUSY"),
        ("scores", 200, True, 502, 3, True, "UPSTREAM_ERROR"),
    ],
)
def test_failed_query_summary_reports_actual_calls(
    tmp_path, logs, score_transport, phase, upstream_status, timeout, status, count, refreshed, code
):
    sent, behavior = score_transport
    behavior.update(phase=phase, status=upstream_status, timeout=timeout)
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            osu_client_id_3=987653,
            osu_client_secret_3="private-site-secret",
        )
    )
    app.state.osu.limiter = Mock()
    app.state.osu.limiter.defer.return_value = 60
    client = TestClient(app)
    response = client.get("/api/v1/players/Player/scores")
    assert response.status_code == status
    (summary,) = [item for item in entries(logs) if item["event"] == "scores_query_completed"]
    assert summary["request_id"] == response.headers["X-Request-ID"]
    assert "query" not in summary
    assert summary["upstream_requests"] == len(sent) == count
    assert summary["token_refreshed"] is refreshed
    assert summary["api_slot"] == 3
    assert summary["cache"] == "MISS"
    assert summary["status"] == status
    assert summary["error_code"] == code
    assert summary["level"] == "WARNING"
    assert "error" in summary["message"]
    assert "private-" not in logs.getvalue()
    if status == 404:
        again = client.get("/api/v1/players/Player/scores")
        cached = [item for item in entries(logs) if item["event"] == "scores_query_completed"][-1]
        assert again.status_code == 404
        assert cached["cache"] == "HIT"
        assert cached["upstream_requests"] == 0
        assert cached["api_slot"] is None
        assert cached["token_refreshed"] is False


@pytest.mark.parametrize(
    ("case", "status", "code", "cache"),
    [
        ("validation", 422, "INVALID_REQUEST", "NOT_CHECKED"),
        ("player", 422, "INVALID_PLAYER", "NOT_CHECKED"),
        ("rate", 429, "RATE_LIMITED", "NOT_CHECKED"),
        ("busy", 503, "SERVER_BUSY", "MISS"),
        ("budget", 503, "UPSTREAM_BUSY", "MISS"),
        ("unconfigured", 503, "NOT_CONFIGURED", "MISS"),
        ("unexpected", 500, "INTERNAL_ERROR", "MISS"),
    ],
)
def test_query_summary_covers_failures_before_http(
    tmp_path, logs, monkeypatch, score_transport, case, status, code, cache
):
    sent, _behavior = score_transport
    credentials = (
        {}
        if case == "unconfigured"
        else {
            "osu_client_id_3": 987653,
            "osu_client_secret_3": "private-site-secret",
        }
    )
    app = create_app(Settings(_env_file=None, cache_path=tmp_path, **credentials))
    app.state.osu.limiter = Mock()
    if case == "rate":
        monkeypatch.setattr(app.state.limiter, "check", lambda *_args: 60)
    elif case == "busy":
        app.state.fetch_lock = Mock(acquire=Mock(return_value=False))
    elif case == "budget":
        app.state.osu.limiter.ensure_capacity.side_effect = UpstreamBusy(60)
    elif case == "unexpected":
        monkeypatch.setattr(app.state.osu, "get_user_scores", Mock(side_effect=RuntimeError()))
    name = "invalid-player-" * 3 if case == "player" else "Player"
    url = f"/api/v1/players/{name}/scores"
    response = TestClient(app).get(url + ("?mode=invalid" if case == "validation" else ""))
    assert response.status_code == status
    (summary,) = [item for item in entries(logs) if item["event"] == "scores_query_completed"]
    assert summary["status"] == status
    assert summary["error_code"] == code
    assert summary["cache"] == cache
    assert summary["upstream_requests"] == len(sent) == 0
    assert summary["token_refreshed"] is False
    assert summary["api_slot"] == (3 if case == "budget" else None)
    assert score_query_log.get() is None


def test_concurrent_queries_do_not_share_summary_fields(
    tmp_path, logs, monkeypatch, score_transport
):
    _sent, _behavior = score_transport
    app = create_app(
        Settings(
            _env_file=None,
            cache_path=tmp_path,
            osu_client_id_3=987653,
            osu_client_secret_3="private-site-secret",
        )
    )
    app.state.osu.limiter = Mock()
    entered, release = Event(), Event()
    send = HTTPAdapter.send

    def blocked_send(adapter, request, **kwargs):
        if "/users/" in request.url and "/scores/" not in request.url:
            entered.set()
            assert release.wait(5)
        return send(adapter, request, **kwargs)

    monkeypatch.setattr(HTTPAdapter, "send", blocked_send)
    client = TestClient(app)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.get, "/api/v1/players/Player/scores")
        try:
            assert entered.wait(5)
            busy = client.get("/api/v1/players/OtherPlayer/scores")
            assert busy.status_code == 503
        finally:
            release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 200
    summaries = [item for item in entries(logs) if item["event"] == "scores_query_completed"]
    assert len(summaries) == 2
    by_id = {item["request_id"]: item for item in summaries}
    active = by_id[response.headers["X-Request-ID"]]
    rejected = by_id[busy.headers["X-Request-ID"]]
    assert "query" not in active
    assert active["upstream_requests"] == 3
    assert active["api_slot"] == 3
    assert active["token_refreshed"] is True
    assert "query" not in rejected
    assert rejected["upstream_requests"] == 0
    assert rejected["api_slot"] is None
    assert rejected["token_refreshed"] is False


@pytest.mark.parametrize("slots", [(1,), (1, 2), (1, 2, 3), (1, 3), (3,)])
def test_upstream_query_logs_identify_configured_slot_and_custom_credentials(
    logs, monkeypatch, slots
):
    configure_logging()
    values = {}
    for slot in slots:
        suffix = "" if slot == 1 else f"_{slot}"
        values[f"osu_client_id{suffix}"] = 987650 + slot
        values[f"osu_client_secret{suffix}"] = f"private-secret-{slot}"
    service = OsuClient(Settings(_env_file=None, **values))
    service.limiter = Mock()
    api = SimpleNamespace(
        user=lambda *_args, **_kwargs: SimpleNamespace(
            id=123,
            username="Player",
            country_code="CN",
            avatar_url="",
            playmode="mania",
            statistics=None,
        ),
        user_scores=lambda *_args, **_kwargs: [],
    )
    for token in service._tokens:
        token.client = api
        token.expires_at = time.monotonic() + 3600
    for _ in range(2):
        for slot in slots:
            service.get_user_scores("Player")
            started = next(
                item for item in reversed(entries(logs)) if item["event"] == "osu_query_started"
            )
            assert started["api_slot"] == slot
            assert started["credentials"] == "site"
            assert "query" not in started
            assert started["required_requests"] == 2

    monkeypatch.setattr(service, "get_ossapi_client", lambda *_args: api)
    service.get_user_scores("123", client_id=987654321, client_secret="private-custom-secret")
    started = next(item for item in reversed(entries(logs)) if item["event"] == "osu_query_started")
    assert started["credentials"] == "custom"
    assert started["api_slot"] is None
    assert "query" not in started
    assert "98765" not in logs.getvalue()
    assert "private-" not in logs.getvalue()


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
