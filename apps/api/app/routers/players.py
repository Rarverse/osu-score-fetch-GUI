import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from app.schemas.scores import ErrorResponse, Ruleset, ScoresResponse
from app.services.cache import normalize_player, score_cache_key
from app.services.osu_client import ServiceError

router = APIRouter(prefix="/api/v1/players", tags=["players"])
logger = logging.getLogger(__name__)


@router.get(
    "/{username}/scores",
    response_model=ScoresResponse,
    responses={status: {"model": ErrorResponse} for status in (404, 422, 429, 502, 503)},
)
def player_scores(
    username: str,
    request: Request,
    response: Response,
    type: Literal["best"] = "best",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    mode: Ruleset = "mania",
):
    name = normalize_player(username)
    if not name or len(name) > 32 or any(ord(char) < 32 or char in "/\\?#" for char in name):
        raise ServiceError(422, "INVALID_PLAYER", "请输入 1–32 字符的用户名或 ID。")
    state = request.app.state
    settings = state.settings
    ip = request.client.host if request.client else "unknown"
    retry_after = state.limiter.check(
        [
            (f"ip:{ip}", settings.rate_limit_per_ip),
            (f"player:{name}", settings.rate_limit_per_player),
        ]
    )
    if retry_after:
        error = ServiceError(429, "RATE_LIMITED", "查询过于频繁，请稍后重试。")
        error.retry_after = retry_after
        raise error

    key = score_cache_key(name, mode)
    data = state.cache.get(key)
    cache_status = "HIT"
    if data is None:
        # ossapi uses a shared OAuth session. Serialize misses and recheck the cache.
        if not state.fetch_lock.acquire(blocking=False):
            raise ServiceError(503, "SERVER_BUSY", "当前查询人数较多，请稍候。", retry_after=3)
        try:
            data = state.cache.get(key)
            if data is None:
                result = state.osu.get_user_scores(name, mode)
                data = result.model_dump(mode="json")
                try:
                    for alias in {name, str(result.player.user_id), result.player.username}:
                        state.cache.set(score_cache_key(alias, mode), data)
                    cache_status = "MISS"
                except OSError:
                    cache_status = "BYPASS"
                    logger.warning("Score cache write failed")
        finally:
            state.fetch_lock.release()
    response.headers["X-Cache"] = cache_status
    response.headers["Cache-Control"] = "no-store"
    logger.info("Score query cache=%s", cache_status)
    result = ScoresResponse.model_validate(data)
    age = (datetime.now(UTC) - result.fetched_at).total_seconds()
    response.headers["X-Cache-TTL"] = str(
        max(0, min(settings.cache_timeout, int(settings.cache_timeout - age)))
    )
    return result.model_copy(update={"scores": result.scores[:limit]})
