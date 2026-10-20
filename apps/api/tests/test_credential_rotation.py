import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from pydantic import ValidationError

from app.config import Settings
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

    def create(client_id, *args, **kwargs):
        created.append(client_id)
        return api()

    monkeypatch.setattr("app.services.osu_client.Ossapi", create)
    slots = []
    for _ in range(count * 2):
        assert service.get_user_scores("Player").player.play_time == 7265
        slots.append(service._slot)
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
