import base64
import hashlib
import json
import os
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.routers.images import IMAGE_TTL, MAX_IMAGE_BYTES

AVATAR = "https://a.ppy.sh/2?12345"
COVER = "https://assets.ppy.sh/beatmaps/1/covers/list@2x.jpg"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aMasAAAAASUVORK5CYII="
)


def upstream(monkeypatch, *, status=200, media_type="image/png", chunks=None):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Content-Type": media_type}
    response.iter_content.side_effect = lambda _: iter(chunks if chunks is not None else [PNG])
    response.__enter__.return_value = response
    get = MagicMock(return_value=response)
    monkeypatch.setattr("app.routers.images.requests.get", get)
    return get


def make_app(tmp_path):
    return create_app(Settings(_env_file=None, cache_path=tmp_path))


@pytest.mark.parametrize(
    "url", [AVATAR, COVER, "https://osu.ppy.sh/images/layout/avatar-guest.png"]
)
def test_images_are_same_origin_and_persist_across_app_restarts(tmp_path, monkeypatch, url):
    get = upstream(monkeypatch)
    first = TestClient(make_app(tmp_path)).get("/api/v1/images", params={"url": url})
    assert first.status_code == 200
    assert first.content == PNG
    assert first.headers["content-type"] == "image/png"
    assert first.headers["x-cache"] == "MISS"
    assert first.headers["cache-control"] == f"public, max-age={IMAGE_TTL}"
    get.assert_called_once_with(url, timeout=(5, 15), stream=True, allow_redirects=False)
    # A fresh application must reuse the disk cache, without fetching upstream.
    second = TestClient(make_app(tmp_path)).get("/api/v1/images", params={"url": url})
    assert second.content == PNG
    assert second.headers["x-cache"] == "HIT"
    assert get.call_count == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://a.ppy.sh/2",
        "https://a.ppy.sh.evil.test/2",
        "https://a.ppy.sh@127.0.0.1/2",
        "https://127.0.0.1/private",
        "https://a.ppy.sh:443/2",
        "https://a.ppy.sh/../../private",
        "https://assets.ppy.sh/beatmaps/1/file.osz",
        "https://osu.ppy.sh/oauth/token",
        "https://a.ppy.sh/2#fragment",
        "https://[broken/2",
    ],
)
def test_image_proxy_rejects_non_artwork_urls(tmp_path, monkeypatch, url):
    get = upstream(monkeypatch)
    response = TestClient(make_app(tmp_path)).get("/api/v1/images", params={"url": url})
    assert response.status_code == 422
    get.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        {"status": 302},
        {"status": 404},
        {"media_type": "text/html"},
        {"media_type": "image/svg+xml"},
        {"chunks": []},
        {"chunks": [b"x" * (MAX_IMAGE_BYTES + 1)]},
    ],
)
def test_invalid_upstream_images_are_not_cached(tmp_path, monkeypatch, options):
    upstream(monkeypatch, **options)
    response = TestClient(make_app(tmp_path)).get("/api/v1/images", params={"url": AVATAR})
    assert response.status_code == 502
    assert response.headers["cache-control"] == "no-store"
    assert not list((tmp_path / "images").glob("*.json"))


def test_image_timeouts_can_be_retried(tmp_path, monkeypatch):
    get = upstream(monkeypatch)
    get.side_effect = requests.Timeout("private details")
    client = TestClient(make_app(tmp_path))
    failed = client.get("/api/v1/images", params={"url": AVATAR})
    assert failed.status_code == 502
    assert "private details" not in failed.text
    get.side_effect = None
    assert client.get("/api/v1/images", params={"url": AVATAR}).status_code == 200


def test_expired_and_corrupt_image_cache_is_refetched(tmp_path, monkeypatch):
    get = upstream(monkeypatch)
    app = make_app(tmp_path)
    client = TestClient(app)
    client.get("/api/v1/images", params={"url": AVATAR})
    key = hashlib.sha256(AVATAR.encode()).hexdigest()
    path = tmp_path / "images" / f"{key}.json"
    # Keep the file but make its reusable timestamp expire.
    data = json.loads(path.read_text())
    data["created_at"] -= IMAGE_TTL
    path.write_text(json.dumps(data))
    assert client.get("/api/v1/images", params={"url": AVATAR}).headers["x-cache"] == "MISS"
    app.state.images.set(key, {"content": "broken base64", "media_type": "image/png"})
    assert client.get("/api/v1/images", params={"url": AVATAR}).content == PNG
    assert get.call_count == 3
    # The existing retention policy also cleans old image cache files.
    os.utime(path, (0, 0))
    app.state.images.next_cleanup = 0
    assert client.get("/api/v1/images", params={"url": AVATAR}).headers["x-cache"] == "MISS"


def test_image_is_still_returned_if_disk_cache_write_fails(tmp_path, monkeypatch):
    upstream(monkeypatch)
    app = make_app(tmp_path)

    def fail(*args):
        raise OSError("read-only disk")

    monkeypatch.setattr(app.state.images, "set", fail)
    response = TestClient(app).get("/api/v1/images", params={"url": AVATAR})
    assert response.status_code == 200
    assert response.content == PNG


def test_simultaneous_page_and_export_requests_fetch_each_image_once(tmp_path, monkeypatch):
    import asyncio
    import time

    import httpx

    get = upstream(monkeypatch)
    response = get.return_value

    def slow_get(*args, **kwargs):
        time.sleep(0.05)  # All concurrent requests arrive before the first completes.
        return response

    get.side_effect = slow_get
    app = make_app(tmp_path)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            results = await asyncio.gather(
                *(client.get("/api/v1/images", params={"url": AVATAR}) for _ in range(8))
            )
            assert all(result.content == PNG for result in results)
            assert [result.headers["x-cache"] for result in results].count("MISS") == 1
            assert get.call_count == 1
            # Cached artwork must stay available while uncached images are queued.
            async with app.state.image_lock:
                cached = await asyncio.wait_for(
                    client.get("/api/v1/images", params={"url": AVATAR}), timeout=0.5
                )
                assert cached.headers["x-cache"] == "HIT"

    asyncio.run(check())


@pytest.fixture
def paced_clock(monkeypatch):
    clock = {"now": 0.0, "waits": []}
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", lambda: clock["now"])

    def sleep(seconds):
        clock["now"] += seconds

    async def wait(seconds):
        clock["waits"].append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("app.services.rate_limit.time.sleep", sleep)
    monkeypatch.setattr("app.routers.images.asyncio.sleep", wait)
    return clock


def test_artwork_oauth_and_api_share_pacing_and_budget(tmp_path, monkeypatch, paced_clock):
    from requests.adapters import HTTPAdapter

    from app.services.osu_client import TimeoutAdapter

    app = create_app(Settings(_env_file=None, cache_path=tmp_path, osu_requests_per_minute=3))
    times = []
    get = upstream(monkeypatch)
    response = get.return_value

    def fetch(*args, **kwargs):
        times.append(paced_clock["now"])
        return response

    def send(*args, **kwargs):
        times.append(paced_clock["now"])
        result = requests.Response()
        result.status_code = 200
        return result

    get.side_effect = fetch
    monkeypatch.setattr(HTTPAdapter, "send", send)
    adapter = TimeoutAdapter(app.state.osu.limiter)
    adapter.send(requests.Request("POST", "https://osu.ppy.sh/oauth/token").prepare())
    client = TestClient(app)
    assert client.get("/api/v1/images", params={"url": AVATAR}).status_code == 200
    adapter.send(requests.Request("GET", "https://osu.ppy.sh/api/v2/users/2").prepare())
    assert client.get("/api/v1/images", params={"url": COVER}).status_code == 200
    assert times == [0, 20, 40, 60]  # A configured 3/minute applies to every upstream path.
    before = len(app.state.osu.limiter.requests)
    assert client.get("/api/v1/images", params={"url": COVER}).headers["x-cache"] == "HIT"
    assert len(app.state.osu.limiter.requests) == before
    assert get.call_count == 2


def test_image_429_respects_retry_after_before_retrying(tmp_path, monkeypatch, paced_clock):
    get = upstream(monkeypatch)
    ok = get.return_value
    limited = MagicMock()
    limited.status_code = 429
    limited.headers = {"Retry-After": "12"}
    limited.__enter__.return_value = limited
    times = []

    def fetch(*args, **kwargs):
        times.append(paced_clock["now"])
        return limited if len(times) == 1 else ok

    get.side_effect = fetch
    client = TestClient(make_app(tmp_path))
    response = client.get("/api/v1/images", params={"url": AVATAR})
    assert response.content == PNG
    assert times == [0, 12]
    assert paced_clock["waits"] == [12]


def sample_scores():
    from datetime import UTC, datetime

    from app.schemas.scores import Player, Score, ScoresResponse

    return ScoresResponse(
        player=Player(
            user_id=2,
            username="Player",
            country="JP",
            avatar_url=AVATAR,
            pp=100,
            global_rank=10,
            hit_accuracy=99,
        ),
        scores=[
            Score(
                score_id=index,
                beatmap_id=index,
                beatmap_title="Song",
                artist="Artist",
                version="Hard",
                cover_url=f"https://assets.ppy.sh/beatmaps/{index}/covers/list@2x.jpg",
                star_rating=4.2,
                accuracy=0.99,
                pp=100,
                rank="S",
                mods=[],
                max_combo=100,
                played_at=None,
            )
            for index in [1, 2]
        ],
        fetched_at=datetime.now(UTC),
    )


def test_score_response_queues_only_selected_artwork_and_deduplicates(tmp_path, monkeypatch):
    get = upstream(monkeypatch)
    app = make_app(tmp_path)
    app.state.osu.get_user_scores = lambda *_args: sample_scores()
    client = TestClient(app)
    for _ in range(2):
        response = client.get("/api/v1/players/Player/scores?limit=1")
        assert response.status_code == 200
    assert app.state.image_queue.qsize() == 2
    assert app.state.image_pending == {AVATAR, COVER}
    get.assert_not_called()  # Enqueuing does not wait on image HTTP requests.


def test_background_warming_does_not_delay_scores_and_exports_reuse_it(tmp_path, monkeypatch):
    from threading import Event

    get = upstream(monkeypatch)
    response = get.return_value
    started, release = Event(), Event()

    def blocked_get(*args, **kwargs):
        started.set()
        assert release.wait(3), "Score response waited for background images"
        return response

    get.side_effect = blocked_get
    app = make_app(tmp_path)
    app.state.osu.get_user_scores = lambda *_args: sample_scores()
    with TestClient(app) as client:
        result = client.get("/api/v1/players/Player/scores?limit=1")
        assert result.status_code == 200
        assert started.wait(1)
        release.set()
        client.portal.call(app.state.image_queue.join)
        assert get.call_count == 2
        assert app.state.image_pending == set()
        for url in [AVATAR, COVER]:
            assert client.get("/api/v1/images", params={"url": url}).headers["x-cache"] == "HIT"
        client.get("/api/v1/players/Player/scores?limit=1")
        client.portal.call(app.state.image_queue.join)
        assert get.call_count == 2  # Query hits and downloads do not fetch artwork again.


def test_background_worker_continues_after_unavailable_avatar(tmp_path, monkeypatch):
    get = upstream(monkeypatch)
    response = get.return_value
    missing = MagicMock()
    missing.status_code = 404
    missing.headers = {}
    missing.__enter__.return_value = missing
    get.side_effect = lambda url, **_kwargs: missing if url == AVATAR else response
    app = make_app(tmp_path)
    app.state.osu.get_user_scores = lambda *_args: sample_scores()
    with TestClient(app) as client:
        assert client.get("/api/v1/players/Player/scores?limit=1").status_code == 200
        client.portal.call(app.state.image_queue.join)
        assert client.get("/api/v1/images", params={"url": COVER}).headers["x-cache"] == "HIT"
        assert app.state.image_pending == set()
        assert get.call_count == 2


def test_background_queue_is_bounded_and_skips_invalid_urls(tmp_path):
    import asyncio

    from app.routers.images import enqueue_images

    app = make_app(tmp_path)
    urls = ["https://evil.test/private", "", *(f"https://a.ppy.sh/{index}" for index in range(300))]
    asyncio.run(enqueue_images(app.state, urls))
    assert app.state.image_queue.qsize() == 256
    assert len(app.state.image_pending) == 256
