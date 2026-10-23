import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.services.osu_client import OsuClient, ServiceError


def settings(count):
    values = {}
    for index in range(count):
        suffix = f"_{index + 1}" if index else ""
        values[f"osu_client_id{suffix}"] = index + 1
        values[f"osu_client_secret{suffix}"] = f"secret-{index}"
    return Settings(_env_file=None, **values)


def api():
    return SimpleNamespace(
        user=lambda *args, **kwargs: SimpleNamespace(
            id=1,
            username="Player",
            country_code="CN",
            avatar_url="",
            playmode="mania",
            statistics=SimpleNamespace(pp=1, global_rank=1, hit_accuracy=99, play_time=7265),
        ),
        user_scores=lambda *args, **kwargs: [],
        session=Mock(),
    )


@pytest.mark.parametrize("count", [1, 2, 3])
def test_rotation_reuses_each_token_and_returns_play_time(count, monkeypatch):
    service = OsuClient(settings(count))
    service.limiter = Mock()
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    session = Mock()
    session.post.return_value = token_response
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("app.services.osu_client.requests.Session", lambda: session)
    created = []
    clients = []

    def create(client_id, *args, **kwargs):
        created.append(client_id)
        client = api()
        client.user = Mock(side_effect=client.user)
        client.user_scores = Mock(side_effect=client.user_scores)
        clients.append(client)
        return client

    monkeypatch.setattr("app.services.osu_client.Ossapi", create)
    slots = []
    for _ in range(count * 2):
        assert service.get_user_scores("Player").player.play_time == 7265
        slots.append(service._slot)
        assert sum(client.user.call_count for client in clients) == len(slots)
        assert sum(client.user_scores.call_count for client in clients) == len(slots)
    assert slots == list(range(count)) * 2
    assert created == list(range(1, count + 1))
    assert session.post.call_count == count


def test_custom_credentials_do_not_advance_rotation(monkeypatch):
    service = OsuClient(settings(2))
    service.limiter = Mock()
    monkeypatch.setattr(service, "get_ossapi_client", lambda *args: api())
    service.get_user_scores("Player")
    service.get_user_scores("Player", client_id=99, client_secret="personal")
    service.get_user_scores("Player")
    assert service._slot == 1


def test_401_invalidates_only_selected_token():
    service = OsuClient(settings(2))
    service.limiter = Mock()
    for token in service._tokens:
        token.client = api()
        token.expires_at = time.monotonic() + 3600
    response = requests.Response()
    response.status_code = 401
    service._tokens[0].client.user = Mock(side_effect=requests.HTTPError(response=response))
    with pytest.raises(ServiceError):
        service.get_user_scores("Player")
    assert service._tokens[0].client is None
    assert service._tokens[1].client is not None
    assert service.get_user_scores("Player").player.play_time == 7265


def test_gaps_are_skipped():
    configured = Settings(_env_file=None, osu_client_id_3=3, osu_client_secret_3="secret")
    assert [item[0] for item in configured.osu_credentials] == [3]


@pytest.mark.parametrize(
    "values",
    [
        {"osu_client_id_2": 2},
        {"osu_client_secret_3": "secret"},
        {"osu_client_id_2": 2, "osu_client_secret_2": " "},
    ],
)
def test_incomplete_pairs_are_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_concurrent_and_cached_queries_do_not_duplicate_upstream(count, tmp_path, monkeypatch):
    configured = settings(count).model_copy(
        update={
            "cache_path": tmp_path / "cache",
            "stats_path": tmp_path / "stats.json",
        }
    )
    app = create_app(configured)
    service = app.state.osu
    service.limiter = Mock()
    entered, release = Event(), Event()
    upstream = api()
    original_user = upstream.user

    def blocked_user(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_user(*args, **kwargs)

    upstream.user = Mock(side_effect=blocked_user)
    upstream.user_scores = Mock(side_effect=upstream.user_scores)
    select_client = Mock(return_value=upstream)
    monkeypatch.setattr(service, "get_ossapi_client", select_client)
    client = TestClient(app)
    url = "/api/v1/players/Player/scores"
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.get, url)
        try:
            assert entered.wait(5)
            busy = client.get(url)
            assert busy.status_code == 503
            assert busy.json()["error"]["code"] == "SERVER_BUSY"
            assert select_client.call_count == 1
            assert upstream.user.call_count == 1
            assert upstream.user_scores.call_count == 0
        finally:
            release.set()
        first = pending.result(timeout=5)
    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    next_slot = service._next_slot
    for cached_url in (url, url + "?limit=50", "/api/v1/players/1/scores?mode=mania"):
        cached = client.get(cached_url)
        assert cached.status_code == 200
        assert cached.headers["X-Cache"] == "HIT"
    assert select_client.call_count == 1
    assert upstream.user.call_count == 1
    assert upstream.user_scores.call_count == 1
    assert service._next_slot == next_slot


@pytest.mark.parametrize("count", [1, 2, 3])
def test_real_ossapi_transport_sends_only_one_request_per_endpoint(count, monkeypatch):
    import json
    from urllib.parse import parse_qs

    from ossapi import Ossapi
    from requests.adapters import HTTPAdapter

    service = OsuClient(settings(count))
    service.limiter = Mock()
    sent = []

    def send(adapter, request, **kwargs):
        sent.append((request.method, request.url, request.headers.get("Authorization")))
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url.endswith("/oauth/token"):
            client_id = parse_qs(request.body)["client_id"][0]
            body = {"access_token": f"token-{client_id}", "expires_in": 3600}
        else:
            body = [] if "/scores/" in request.url else {"id": 1}
        response._content = json.dumps(body).encode()
        response._content_consumed = True
        return response

    # Keep the real OAuth session, constructor, endpoint methods and HTTP adapter;
    # replace only the network and unrelated model deserialization.
    monkeypatch.setattr(HTTPAdapter, "send", send)
    monkeypatch.setattr(
        Ossapi,
        "_instantiate_type",
        lambda self, type_, data: [] if isinstance(data, list) else api().user("Player"),
    )
    for lookup in range(count * 2):
        start = len(sent)
        service.get_user_scores("Player")
        requests_for_lookup = sent[start:]
        expected = 3 if lookup < count else 2
        assert len(requests_for_lookup) == expected
        assert [method for method, _, _ in requests_for_lookup] == (
            ["POST", "GET", "GET"] if expected == 3 else ["GET", "GET"]
        )
        assert "/users/Player/" in requests_for_lookup[-2][1]
        assert "/users/1/scores/best" in requests_for_lookup[-1][1]
        selected = lookup % count + 1
        assert requests_for_lookup[-2][2] == f"Bearer token-{selected}"
        assert requests_for_lookup[-1][2] == f"Bearer token-{selected}"
    assert len(sent) == count + 2 * count * 2
