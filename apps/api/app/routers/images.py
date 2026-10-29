import asyncio
import base64
import binascii
import hashlib
import logging
import re
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from fastapi import APIRouter, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.client_ip import client_ip
from app.logging_setup import safe_error_fields
from app.services.osu_client import ServiceError
from app.services.rate_limit import UpstreamBusy, UpstreamLimiter

router = APIRouter(prefix="/api/v1/images", tags=["images"])
logger = logging.getLogger(__name__)
# Browser cache lifetime; server entries follow CACHE_RETENTION from their last write.
IMAGE_MAX_AGE = 31536000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def validate_image_url(url: str) -> str:
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
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def cached_image(cache, key: str) -> Response | None:
    cached = cache.get_fresh(key)
    if cached:
        data, _ttl = cached
        try:
            content = base64.b64decode(data["content"], validate=True)
            media_type = data["media_type"]
            if media_type in IMAGE_TYPES and content:
                return Response(
                    content,
                    media_type=media_type,
                    headers={
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": f"public, max-age={IMAGE_MAX_AGE}",
                        "X-Cache": "HIT",
                    },
                )
        except (KeyError, TypeError, ValueError, binascii.Error):
            pass
    return None


def fetch_image(url: str, limiter: UpstreamLimiter) -> tuple[bytes, str]:
    # Artwork has its own paced budget so CDN traffic cannot block score lookups.
    queued = time.perf_counter()
    limiter.acquire()
    wait_ms = round((time.perf_counter() - queued) * 1000, 1)
    started = time.perf_counter()
    fields = {"wait_ms": wait_ms}
    try:
        with requests.get(url, timeout=(5, 15), stream=True, allow_redirects=False) as upstream:
            fields["status"] = upstream.status_code
            if upstream.status_code == 429:
                raise UpstreamBusy(limiter.defer(upstream.headers.get("Retry-After")))
            media_type = upstream.headers.get("Content-Type", "").split(";")[0].strip()
            fields["media_type"] = media_type if media_type in IMAGE_TYPES else "unsupported"
            if upstream.status_code != 200 or media_type not in IMAGE_TYPES:
                fields["reason"] = (
                    "http_status" if upstream.status_code != 200 else "unsupported_type"
                )
                raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘暂时无法加载。")
            content = bytearray()
            for chunk in upstream.iter_content(64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_IMAGE_BYTES:
                    fields["reason"] = "image_too_large"
                    raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘文件过大。")
            if not content:
                fields["reason"] = "empty_image"
                raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘暂时无法加载。")
    except requests.RequestException as error:
        logger.warning(
            "image_http_failed",
            extra={
                "fields": {
                    **fields,
                    **safe_error_fields(error),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        raise ServiceError(502, "IMAGE_UNAVAILABLE", "头像或曲绘暂时无法加载。") from None
    except ServiceError:
        logger.warning("image_http_failed", extra={"fields": fields})
        raise
    logger.info(
        "image_http_completed",
        extra={
            "fields": {
                **fields,
                "bytes": len(content),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        },
    )
    return bytes(content), media_type


@router.get("")
async def image(request: Request, url: str = Query(max_length=2048)):
    # A fixed host/path allowlist and disabled redirects prevent an open proxy.
    state = request.app.state
    settings = state.settings
    ip = client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        settings.forwarded_allow_ips,
    )
    retry_after = state.limiter.check(
        [
            ("images-global:all", settings.rate_limit_images_global),
            (f"image-ip:{ip}", settings.rate_limit_images_per_ip),
        ]
    )
    if retry_after:
        raise ServiceError(
            429, "RATE_LIMITED", "图片请求过于频繁，请稍后重试。", retry_after=retry_after
        )
    return await get_image(state, validate_image_url(url))


async def get_image(state, url: str) -> Response:
    key = hashlib.sha256(url.encode()).hexdigest()
    cached = cached_image(state.images, key)
    if cached is not None:
        logger.debug("image_cache_lookup", extra={"fields": {"cache": "HIT"}})
        return cached
    logger.debug("image_cache_lookup", extra={"fields": {"cache": "MISS"}})
    queued = time.perf_counter()
    try:
        # Queue misses without occupying the HTTP thread pool. Recheck after
        # waiting so simultaneous page/export requests only fetch each image once.
        async with asyncio.timeout(75), state.image_lock:
            wait_ms = round((time.perf_counter() - queued) * 1000, 1)
            logger.debug(
                "image_cache_lookup", extra={"fields": {"stage": "after_queue", "wait_ms": wait_ms}}
            )
            cached = cached_image(state.images, key)
            if cached is not None:
                return cached
            while True:
                try:
                    content, media_type = await run_in_threadpool(
                        fetch_image, url, state.image_limiter
                    )
                    break
                except UpstreamBusy as busy:
                    logger.info(
                        "image_fetch_wait", extra={"fields": {"retry_after": busy.retry_after}}
                    )
                    await asyncio.sleep(busy.retry_after)
            try:
                state.images.set(
                    key, {"content": base64.b64encode(content).decode(), "media_type": media_type}
                )
            except OSError as error:
                logger.warning(
                    "image_cache_write_failed", extra={"fields": safe_error_fields(error)}
                )
    except TimeoutError:
        logger.warning(
            "image_queue_timeout",
            extra={
                "fields": {
                    "wait_ms": round((time.perf_counter() - queued) * 1000, 1),
                    "error_code": "IMAGE_BUSY",
                }
            },
        )
        raise ServiceError(
            503, "IMAGE_BUSY", "图片服务繁忙，请稍后重试下载。", retry_after=5
        ) from None
    return Response(
        content,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": f"public, max-age={IMAGE_MAX_AGE}",
            "X-Cache": "MISS",
        },
    )


async def enqueue_images(state, urls: list[str]) -> None:
    # Called after the score response is sent. The bounded queue deduplicates
    # page visits while the existing image lock also covers concurrent exports.
    added = 0
    skipped = 0
    dropped = 0
    unique = list(dict.fromkeys(urls))
    for index, raw_url in enumerate(unique):
        if not raw_url:
            skipped += 1
            continue
        try:
            url = validate_image_url(raw_url)
            if url in state.image_pending:
                skipped += 1
                continue
            state.image_queue.put_nowait(url)
        except ServiceError:
            skipped += 1
            continue
        except asyncio.QueueFull:
            dropped = len(unique) - index
            break
        state.image_pending.add(url)
        added += 1
    logger.log(
        logging.WARNING if dropped else logging.DEBUG,
        "images_enqueued",
        extra={
            "fields": {
                "added": added,
                "skipped": skipped,
                "dropped": dropped,
                "queue_size": state.image_queue.qsize(),
            }
        },
    )


async def warm_images(state) -> None:
    while True:
        url = await state.image_queue.get()
        try:
            await get_image(state, url)
            logger.debug(
                "image_warm_completed",
                extra={"fields": {"source": "background", "queue_size": state.image_queue.qsize()}},
            )
        except ServiceError as error:
            logger.warning(
                "image_warm_failed",
                extra={
                    "fields": {
                        "source": "background",
                        "error_code": error.code,
                        "retry_after": error.retry_after,
                    }
                },
            )
        except OSError as error:
            logger.warning(
                "image_warm_failed",
                extra={"fields": {"source": "background", **safe_error_fields(error)}},
            )
        finally:
            state.image_pending.discard(url)
            state.image_queue.task_done()
