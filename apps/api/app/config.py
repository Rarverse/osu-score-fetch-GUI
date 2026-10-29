from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    osu_client_id: int | None = None
    osu_client_secret: SecretStr | None = None
    osu_client_id_2: int | None = None
    osu_client_secret_2: SecretStr | None = None
    osu_client_id_3: int | None = None
    osu_client_secret_3: SecretStr | None = None
    log_format: Literal["text", "json"] = "text"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cache_timeout: int = Field(default=180, ge=60)
    cache_retention: int = Field(default=15552000, ge=60)
    cache_path: Path = API_ROOT / ".cache"
    # Salted daily aggregates. Override in production so this stays outside release dirs.
    stats_path: Path = API_ROOT / "data" / "cache" / "usage.json"
    negative_cache_ttl: int = Field(default=60, ge=1, le=86400)
    rate_limit_window: int = Field(default=60, ge=1)
    rate_limit_global: int = Field(default=120, ge=1)
    rate_limit_per_ip: int = Field(default=20, ge=1)
    rate_limit_per_player: int = Field(default=10, ge=1)
    rate_limit_upstream_cost_per_ip: int = Field(default=30, ge=3)
    rate_limit_images_global: int = Field(default=300, ge=1)
    rate_limit_images_per_ip: int = Field(default=120, ge=1)
    osu_requests_per_minute: int = Field(default=60, ge=3, le=60)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Comma-separated IPs or CIDRs that may set X-Forwarded-For. Compose sets
    # this to the web container address. Do not use "*".
    forwarded_allow_ips: str = "127.0.0.1"

    @model_validator(mode="after")
    def validate_cache_retention(self):
        if self.cache_retention < self.cache_timeout:
            raise ValueError("CACHE_RETENTION must be at least CACHE_TIMEOUT")
        return self

    @property
    def osu_credentials(self) -> list[tuple[int, SecretStr]]:
        return [
            (client_id, secret)
            for client_id, secret in (
                (self.osu_client_id, self.osu_client_secret),
                (self.osu_client_id_2, self.osu_client_secret_2),
                (self.osu_client_id_3, self.osu_client_secret_3),
            )
            if client_id and secret and secret.get_secret_value().strip()
        ]

    @model_validator(mode="after")
    def validate_credentials(self):
        for suffix in ("", "_2", "_3"):
            client_id = getattr(self, f"osu_client_id{suffix}")
            secret = getattr(self, f"osu_client_secret{suffix}")
            if client_id is None and secret is None:
                continue
            if (
                not client_id
                or client_id < 1
                or not secret
                or not secret.get_secret_value().strip()
            ):
                raise ValueError(
                    f"OSU_CLIENT_ID{suffix} and OSU_CLIENT_SECRET{suffix} must form a complete pair"
                )
        ids = [client_id for client_id, _ in self.osu_credentials]
        if len(ids) != len(set(ids)):
            raise ValueError("Each osu! credential slot must use a distinct Client ID")
        return self
