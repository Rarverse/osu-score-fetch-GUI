import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request, Response

from app.client_ip import client_ip
from app.schemas.scores import ErrorResponse, Ruleset, ScoresResponse
from app.services.cache import normalize_player, not_found_cache_key, score_cache_key
from app.services.osu_client import ServiceError

router = APIRouter(prefix="/api/v1/players", tags=["players"])
logger = logging.getLogger(__name__)
NOT_FOUND = "未找到该玩家，请检查用户名或 ID。"


def _remember_missing(state, key: str) -> None:
    try:
        state.not_found.set(key, {"code": "PLAYER_NOT_FOUND"})
    except OSError:
        logger.warning("Negative cache write failed")


def _missing_player(cache: str, ttl: int) -> ServiceError:
    error = ServiceError(404, "PLAYER_NOT_FOUND", NOT_FOUND)
    error.cache = cache
    error.cache_ttl = ttl
    return error


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
    osu_client_id: Annotated[int | None, Header(alias="X-Osu-Client-Id", gt=0)] = None,
    osu_client_secret: Annotated[str | None, Header(alias="X-Osu-Client-Secret")] = None,
    visitor_id: Annotated[str | None, Header(alias="X-Visitor-Id")] = None,
):
    state = request.app.state
    settings = state.settings
    player_id: str | None = None
    try:
        name = normalize_player(username)
        if not name or len(name) > 32 or any(ord(char) < 32 or char in "/\\?#" for char in name):
            raise ServiceError(422, "INVALID_PLAYER", "请输入 1–32 字符的用户名或 ID。")
        if (osu_client_id is None) != (osu_client_secret is None) or (
            osu_client_secret is not None and not osu_client_secret.strip()
        ):
            raise ServiceError(
                422,
                "INVALID_CREDENTIALS",
                "请同时提供有效的 osu! Client ID 和 Client Secret。",
            )
        ip = client_ip(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            settings.forwarded_allow_ips,
        )
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
        missing_key = not_found_cache_key(name)
        cached_missing = state.not_found.get_fresh(missing_key)
        if cached_missing is not None:
            raise _missing_player("HIT", cached_missing[1])

        data = state.cache.get(key)
        cache_status = "HIT"
        if data is None:
            # ossapi uses a shared OAuth session. Serialize misses and recheck the cache.
            if not state.fetch_lock.acquire(blocking=False):
                raise ServiceError(503, "SERVER_BUSY", "当前查询人数较多，请稍候。", retry_after=3)
            try:
                cached_missing = state.not_found.get_fresh(missing_key)
                if cached_missing is not None:
                    raise _missing_player("HIT", cached_missing[1])
                data = state.cache.get(key)
                if data is None:
                    try:
                        if osu_client_id is None:
                            result = state.osu.get_user_scores(name, mode)
                        else:
                            result = state.osu.get_user_scores(
                                name, mode, osu_client_id, osu_client_secret
                            )
                    except ServiceError as error:
                        if error.code == "PLAYER_NOT_FOUND":
                            _remember_missing(state, missing_key)
                            error.cache = "MISS"
                            error.cache_ttl = settings.negative_cache_ttl
                        raise
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
        player_id = str(result.player.user_id)
        return result.model_copy(update={"scores": result.scores[:limit]})
    finally:
        try:
            state.stats.record(
                mode=mode,
                success=player_id is not None,
                player_id=player_id,
                visitor_id=visitor_id,
            )
        except Exception:
            logger.warning("Usage stats were not recorded")
