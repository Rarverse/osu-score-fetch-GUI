import time
from datetime import UTC, datetime

import requests
from ossapi import GameMode, Ossapi, ScoreType
from requests.adapters import HTTPAdapter

from app.config import Settings
from app.schemas.scores import Player, Ruleset, Score, ScoresResponse
from app.services.rate_limit import UpstreamBusy, UpstreamLimiter


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        self.status, self.code, self.message = status, code, message
        self.retry_after = retry_after
        self.cache: str | None = None
        self.cache_ttl: int | None = None


class TimeoutAdapter(HTTPAdapter):
    def __init__(self, limiter: UpstreamLimiter):
        super().__init__()
        self.limiter = limiter

    def send(self, request, **kwargs):
        self.limiter.acquire()
        kwargs["timeout"] = (5, 20)
        response = super().send(request, **kwargs)
        if response.status_code == 429:
            retry_after = self.limiter.defer(response.headers.get("Retry-After"))
            response.close()
            raise UpstreamBusy(retry_after)
        response.raise_for_status()
        return response


def structure_scores(scores) -> list[Score]:
    result = []
    for score in scores:
        beatmap, beatmapset = score.beatmap, score.beatmapset
        rank = score.rank.value
        result.append(
            Score(
                score_id=score.id,
                beatmap_id=beatmap.id if beatmap else None,
                beatmap_title=beatmapset.title if beatmapset else "Unknown beatmap",
                artist=beatmapset.artist if beatmapset else "",
                version=beatmap.version if beatmap else "",
                cover_url=beatmapset.covers.list_2x if beatmapset else None,
                star_rating=beatmap.difficulty_rating if beatmap else None,
                accuracy=score.accuracy,
                pp=score.pp,
                rank={"X": "SS", "XH": "SSH"}.get(rank, rank),
                mods=[mod.acronym for mod in score.mods],
                max_combo=score.max_combo,
                played_at=score.ended_at,
            )
        )
    return result


class OsuClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Ossapi | None = None
        self.expires_at = 0.0
        self.limiter = UpstreamLimiter(settings.osu_requests_per_minute)

    def get_ossapi_client(
        self, client_id: int | None = None, client_secret: str | None = None
    ) -> Ossapi:
        custom_credentials = client_id is not None or client_secret is not None
        if not custom_credentials and self.client and time.monotonic() < self.expires_at:
            return self.client
        configured_secret = self.settings.osu_client_secret
        resolved_client_id = client_id or self.settings.osu_client_id
        resolved_secret = client_secret or (
            configured_secret.get_secret_value() if configured_secret else None
        )
        if not resolved_client_id or not resolved_secret:
            raise ServiceError(503, "NOT_CONFIGURED", "服务端尚未配置 osu! OAuth 凭据。")
        # Manage the client credentials token in memory, with a bounded OAuth request.
        # Supplying access_token prevents ossapi from persisting credentials via pickle.
        with requests.Session() as session:
            session.mount("https://", TimeoutAdapter(self.limiter))
            response = session.post(
                "https://osu.ppy.sh/oauth/token",
                data={
                    "client_id": resolved_client_id,
                    "client_secret": resolved_secret,
                    "grant_type": "client_credentials",
                    "scope": "public",
                },
            )
        response.raise_for_status()
        token = response.json()
        client = Ossapi(
            resolved_client_id,
            resolved_secret,
            access_token=token["access_token"],
        )
        client.session.mount("https://", TimeoutAdapter(self.limiter))
        if custom_credentials:
            # User-supplied secrets and tokens are used for this lookup only.
            return client
        self.client = client
        self.expires_at = time.monotonic() + max(0, token["expires_in"] - 60)
        return client

    def get_user_scores(
        self,
        username: str,
        mode: Ruleset | None = None,
        client_id: int | None = None,
        client_secret: str | None = None,
    ) -> ScoresResponse:
        api = None
        try:
            # Check headroom for the whole lookup while the route holds the fetch lock.
            has_cached_token = (
                client_id is None
                and client_secret is None
                and self.client is not None
                and time.monotonic() < self.expires_at
            )
            needed = 2 if has_cached_token else 3
            self.limiter.ensure_capacity(needed)
            api = (
                self.get_ossapi_client()
                if client_id is None and client_secret is None
                else self.get_ossapi_client(client_id, client_secret)
            )
            try:
                user = api.user(username, mode=GameMode(mode) if mode else None)
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    raise ServiceError(
                        404, "PLAYER_NOT_FOUND", "未找到该玩家，请检查用户名或 ID。"
                    ) from None
                raise
            mode = GameMode(mode or user.playmode).value
            scores = api.user_scores(
                user.id, ScoreType.BEST, mode=GameMode(mode), limit=50, include_fails=False
            )
            stats = user.statistics
            return ScoresResponse(
                mode=mode,
                player=Player(
                    user_id=user.id,
                    username=user.username,
                    country=user.country_code,
                    avatar_url=user.avatar_url,
                    pp=stats.pp if stats else None,
                    global_rank=stats.global_rank if stats else None,
                    hit_accuracy=stats.hit_accuracy if stats else None,
                ),
                scores=structure_scores(scores),
                fetched_at=datetime.now(UTC),
            )
        except UpstreamBusy as error:
            raise ServiceError(
                503, "UPSTREAM_BUSY", "查询服务正在等待 osu! 请求额度。", error.retry_after
            ) from None
        except requests.HTTPError as error:
            if (
                error.response is not None
                and error.response.status_code == 401
                and api is not None
                and api is self.client
            ):
                self.client = None
                self.expires_at = 0.0
                api.session.close()
            raise ServiceError(
                502, "UPSTREAM_ERROR", "osu! 服务暂时无法访问，请稍后重试。"
            ) from None
        except ServiceError:
            raise
        except Exception:
            # Keep tokens, raw upstream bodies and exception details out of responses/logs.
            raise ServiceError(
                502, "UPSTREAM_ERROR", "osu! 服务暂时无法访问，请稍后重试。"
            ) from None
