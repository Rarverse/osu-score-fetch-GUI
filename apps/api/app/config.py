from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    osu_client_id: int | None = None
    osu_client_secret: SecretStr | None = None
    cache_timeout: int = Field(default=3600, ge=1)
    cache_path: Path = API_ROOT / ".cache"
    rate_limit_window: int = Field(default=60, ge=1)
    rate_limit_per_ip: int = Field(default=20, ge=1)
    rate_limit_per_player: int = Field(default=10, ge=1)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
