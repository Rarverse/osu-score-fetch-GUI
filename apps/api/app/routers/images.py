import asyncio
import base64
import binascii
import hashlib
import logging
import re
from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.services.osu_client import ServiceError
from app.services.rate_limit import UpstreamBusy, UpstreamLimiter

router = APIRouter(prefix="/api/v1/images", tags=["images"])
logger = logging.getLogger(__name__)
IMAGE_TTL = 86400
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def validate_image_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise ServiceError(422, "INVALID_IMAGE", "图片地址无效。") from None
    allowed = (
        parsed.netloc == "a.ppy.sh"
        and re.fullmatch(r"/\d+", parsed.path)
        or parsed.netloc == "assets.ppy.sh"
        and re.fullmatch(r"/beatmaps/\d+/covers/[\w@.-]+\.(?:jpg|jpeg|png|webp)", parsed.path)
        or parsed.netloc == "osu.ppy.sh"
        and parsed.path == "/images/layout/avatar-guest.png"
    )
    if parsed.scheme != "https" or parsed.fragment or not allowed:
        raise ServiceError(422, "INVALID_IMAGE", "仅支持 osu! 玩家头像和谱面曲绘。")


def cached_image(cache, key: str) -> Response | None:
    cached = cache.get_fresh(key)
    if cached:
        data, ttl = cached
        try:
            content = base64.b64decode(data["content"], validate=True)
            media_type = data["media_type"]
            if media_type in IMAGE_TYPES and content:
                return Response(
                    content,
                    media_type=media_type,
                    headers={
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": f"public, max-age={ttl}",
                        "X-Cache": "HIT",
                    },
                )
        except (KeyError, TypeError, ValueError, binascii.Error):
            pass
    return None


def fetch_image(url: str, limiter: UpstreamLimiter) -> tuple[bytes, str]:
    # OAuth, scores and artwork use the same process-wide paced budget.
    limiter.acquire()
    try:
        with requests.get(url, timeout=(5, 15), stream=True, allow_redirects=False) as upstream:
            if upstream.status_code == 429:
                raise UpstreamBusy(limiter.defer(upstream.headers.get("Retry-After")))
            media_type = upstream.headers.get("Content-Type", "").split(";")[0].strip()
            if upstream.status_code != 200 or media_type not in IMAGE_TYPES:
                raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘暂时无法加载。")
            content = bytearray()
            for chunk in upstream.iter_content(64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_IMAGE_BYTES:
                    raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘文件过大。")
            if not content:
                raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘暂时无法加载。")
    except requests.RequestException:
        raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘暂时无法加载。") from None
    return bytes(content), media_type


@router.get("")
async def image(request: Request, url: str = Query(max_length=2048)):
    # A fixed host/path allowlist and disabled redirects prevent an open proxy.
    validate_image_url(url)
    return await get_image(request.app.state, url)


async def get_image(state, url: str) -> Response:
    key = hashlib.sha256(url.encode()).hexdigest()
    cached = cached_image(state.images, key)
    if cached is not None:
        return cached
    try:
        # Queue misses without occupying the HTTP thread pool. Recheck after
        # waiting so simultaneous page/export requests only fetch each image once.
        async with asyncio.timeout(75), state.image_lock:
            cached = cached_image(state.images, key)
            if cached is not None:
                return cached
            while True:
                try:
                    content, media_type = await run_in_threadpool(
                        fetch_image, url, state.osu.limiter
                    )
                    break
                except UpstreamBusy as busy:
                    await asyncio.sleep(busy.retry_after)
            try:
                state.images.set(
                    key, {"content": base64.b64encode(content).decode(), "media_type": media_type}
                )
            except OSError:
                logger.warning("Image cache write failed")
    except TimeoutError:
        raise ServiceError(
            503, "IMAGE_BUSY", "图片服务繁忙，请稍后重试下载。", retry_after=5
        ) from None
    return Response(
        content,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": f"public, max-age={IMAGE_TTL}",
            "X-Cache": "MISS",
        },
    )


async def enqueue_images(state, urls: list[str]) -> None:
    # Called after the score response is sent. The bounded queue deduplicates
    # page visits while the existing image lock also covers concurrent exports.
    for url in dict.fromkeys(urls):
        if not url or url in state.image_pending:
            continue
        try:
            validate_image_url(url)
            state.image_queue.put_nowait(url)
        except ServiceError:
            continue
        except asyncio.QueueFull:
            break
        state.image_pending.add(url)


async def warm_images(state) -> None:
    while True:
        url = await state.image_queue.get()
        try:
            await get_image(state, url)
        except ServiceError:
            logger.info("Background artwork caching skipped an unavailable image")
        except OSError:
            logger.warning("Background artwork cache unavailable")
        finally:
            state.image_pending.discard(url)
            state.image_queue.task_done()
