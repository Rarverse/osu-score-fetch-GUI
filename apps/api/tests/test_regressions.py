import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient
from test_usage import _scores

from app.config import Settings
from app.main import create_app
from app.services.osu_client import OsuClient, ServiceError
from app.services.usage import UsageStats


@pytest.mark.parametrize(
    "raw",
    [
        "broken",
        "[]",
        "{}",
        '{"salt":"short","visitors":{},"days":{}}',
        '{"salt":"0123456789abcdef","visitors":[],"days":{}}',
    ],
)
def test_invalid_stats_are_never_overwritten(tmp_path, raw):
    path = tmp_path / "usage.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        UsageStats(path).record(mode="mania", success=True, player_id="123", visitor_id=None)
    assert path.read_text() == raw


def test_unreadable_stats_are_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "usage.json"
    raw = json.dumps({"salt": "0123456789abcdef", "visitors": {"old": "2026-01-01"}, "days": {}})
    path.write_text(raw)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", Mock(side_effect=PermissionError))
        with pytest.raises(PermissionError):
            UsageStats(path).record(mode="mania", success=True, player_id="123", visitor_id=None)
    assert path.read_text() == raw


@pytest.mark.parametrize("operation", ["user", "user_scores"])
def test_401_discards_cached_token_and_next_query_refreshes(operation, monkeypatch):
    client = OsuClient(Settings(_env_file=None))
    response = requests.Response()
    response.status_code = 401
    old = Mock()
    old.user.return_value = SimpleNamespace(id=123, playmode="mania")
    getattr(old, operation).side_effect = requests.HTTPError(response=response)
    client.client, client.expires_at = old, time.monotonic() + 3600
    with pytest.raises(ServiceError):
        client.get_user_scores("Player")
    assert client.client is None
    assert client.expires_at == 0
    old.session.close.assert_called_once()
    refresh = Mock(side_effect=ServiceError(503, "NOT_CONFIGURED", "test"))
    monkeypatch.setattr(client, "get_ossapi_client", refresh)
    with pytest.raises(ServiceError):
        client.get_user_scores("Player")
    refresh.assert_called_once()


def test_successful_id_query_invalidates_negative_name_cache_across_modes(tmp_path):
    app = create_app(Settings(_env_file=None, cache_path=tmp_path))
    found = False

    def fetch(name, mode):
        nonlocal found
        if name == "player" and not found:
            raise ServiceError(404, "PLAYER_NOT_FOUND", "missing")
        found = True
        return _scores(mode, 123, "Player")

    app.state.osu.get_user_scores = fetch
    client = TestClient(app)
    assert client.get("/api/v1/players/Player/scores").status_code == 404
    assert client.get("/api/v1/players/123/scores").status_code == 200
    assert client.get("/api/v1/players/Player/scores").status_code == 200
    assert client.get("/api/v1/players/Player/scores?mode=osu").status_code == 200


@pytest.mark.parametrize("status", [400, 401])
def test_rejected_personal_credentials_are_actionable(status, monkeypatch):
    client = OsuClient(Settings(_env_file=None))
    response = requests.Response()
    response.status_code = status
    monkeypatch.setattr(
        client, "get_ossapi_client", Mock(side_effect=requests.HTTPError(response=response))
    )
    with pytest.raises(ServiceError) as failure:
        client.get_user_scores("Player", None, 123, "test-only-secret")
    assert failure.value.status == 422
    assert failure.value.code == "INVALID_CREDENTIALS"
    assert failure.value.retry_after is None
