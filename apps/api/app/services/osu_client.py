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

    def get_ossapi_client(self) -> Ossapi:
        if self.client and time.monotonic() < self.expires_at:
            return self.client
        secret = self.settings.osu_client_secret
        if not self.settings.osu_client_id or not secret or not secret.get_secret_value():
            raise ServiceError(503, "NOT_CONFIGURED", "服务端尚未配置 osu! OAuth 凭据。")
        # Manage the client credentials token in memory, with a bounded OAuth request.
        # Supplying access_token prevents ossapi from persisting credentials via pickle.
        with requests.Session() as session:
            session.mount("https://", TimeoutAdapter(self.limiter))
            response = session.post(
                "https://osu.ppy.sh/oauth/token",
                json={
                    "client_id": self.settings.osu_client_id,
                    "client_secret": secret.get_secret_value(),
                    "grant_type": "client_credentials",
                    "scope": "public",
                },
            )
        response.raise_for_status()
        token = response.json()
        self.client = Ossapi(
            self.settings.osu_client_id,
            secret.get_secret_value(),
            access_token=token["access_token"],
        )
        self.client.session.mount("https://", TimeoutAdapter(self.limiter))
        self.expires_at = time.monotonic() + max(0, token["expires_in"] - 60)
        return self.client

    def get_user_scores(self, username: str, mode: Ruleset = "mania") -> ScoresResponse:
        try:
            # Check headroom for the whole lookup while the route holds the fetch lock.
            needed = 2 if self.client and time.monotonic() < self.expires_at else 3
            self.limiter.ensure_capacity(needed)
            api = self.get_ossapi_client()
            try:
                user = api.user(username, mode=GameMode(mode))
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    raise ServiceError(
                        404, "PLAYER_NOT_FOUND", "未找到该玩家，请检查用户名或 ID。"
                    ) from None
                raise
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
        except ServiceError:
            raise
        except Exception:
            # Keep tokens, raw upstream bodies and exception details out of responses/logs.
            raise ServiceError(
                502, "UPSTREAM_ERROR", "osu! 服务暂时无法访问，请稍后重试。"
            ) from None
