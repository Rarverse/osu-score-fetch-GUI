from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    osu_client_id: int | None = None
    osu_client_secret: SecretStr | None = None
    cache_timeout: int = Field(default=60, ge=60)
    cache_retention: int = Field(default=15552000, ge=60)
    cache_path: Path = API_ROOT / ".cache"
    rate_limit_window: int = Field(default=60, ge=1)
    rate_limit_per_ip: int = Field(default=20, ge=1)
    rate_limit_per_player: int = Field(default=10, ge=1)
    osu_requests_per_minute: int = Field(default=60, ge=3, le=60)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def validate_cache_retention(self):
        if self.cache_retention < self.cache_timeout:
            raise ValueError("CACHE_RETENTION must be at least CACHE_TIMEOUT")
        return self
