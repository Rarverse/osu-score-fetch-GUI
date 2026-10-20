from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Ruleset = Literal["osu", "taiko", "fruits", "mania"]


class Player(BaseModel):
    user_id: int
    username: str
    country: str
    avatar_url: str
    pp: float | None
    global_rank: int | None
    hit_accuracy: float | None  # Percentage, 0–100 (user statistics).

    play_time: int | None = Field(default=None, ge=0)  # Total seconds in this ruleset.


class Score(BaseModel):
    score_id: int | None
    beatmap_id: int | None
    beatmap_title: str
    artist: str
    version: str
    cover_url: str | None
    star_rating: float | None  # Base difficulty, without mods.
    accuracy: float = Field(ge=0, le=1)
    pp: float | None  # Unavailable pp stays null, never a fabricated zero.
    rank: str
    mods: list[str]
    max_combo: int
    played_at: datetime | None


class ScoresResponse(BaseModel):
    player: Player
    mode: Ruleset = "mania"
    type: Literal["best"] = "best"
    scores: list[Score]
    fetched_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
