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
    rate_limit_per_ip: int = Field(default=20, ge=1)
    rate_limit_per_player: int = Field(default=10, ge=1)
    osu_requests_per_minute: int = Field(default=60, ge=3, le=60)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Comma-separated IPs or CIDRs that may set X-Forwarded-For. Compose sets
    # this to the web container address. Do not use "*".
    forwarded_allow_ips: str = "127.0.0.1"
    admin_enabled: bool = False
    database_url: str | None = None
    admin_public_origin: str | None = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_client_secret_file: Path | None = None
    oidc_redirect_uri: str | None = None
    oidc_scopes: str = "openid profile email"
    admin_required_role: str = "raru-admin"
    admin_role_claim: str = "groups"
    admin_required_amr: str = "pwd,mfa"
    admin_require_verified_email: bool = False
    admin_secure_cookies: bool = True
    admin_session_idle_seconds: int = Field(default=1800, ge=300, le=86400)
    admin_session_absolute_seconds: int = Field(default=28800, ge=900, le=604800)
    audit_encryption_key: SecretStr | None = None
    audit_encryption_key_file: Path | None = None
    audit_lookup_key: SecretStr | None = None
    audit_lookup_key_file: Path | None = None
    query_result_retention_days: int = Field(default=7, ge=1, le=365)
    query_metadata_retention_days: int = Field(default=30, ge=1, le=3650)
    admin_audit_retention_days: int = Field(default=180, ge=30, le=3650)
    loki_url: str | None = None
    loki_tenant_id: str | None = None
    prometheus_url: str | None = None
    log_environment: str = "production"
    admin_log_max_range_days: int = Field(default=30, ge=1, le=365)
    admin_log_query_max_limit: int = Field(default=500, ge=50, le=5000)

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

    @model_validator(mode="after")
    def validate_admin(self):
        if not self.admin_enabled:
            return self
        required = {
            "DATABASE_URL": self.database_url,
            "ADMIN_PUBLIC_ORIGIN": self.admin_public_origin,
            "OIDC_ISSUER": self.oidc_issuer,
            "OIDC_CLIENT_ID": self.oidc_client_id,
            "OIDC_REDIRECT_URI": self.oidc_redirect_uri,
        }
        missing = [name for name, value in required.items() if not value]
        if not self.oidc_client_secret and not self.oidc_client_secret_file:
            missing.append("OIDC_CLIENT_SECRET or OIDC_CLIENT_SECRET_FILE")
        if not self.audit_encryption_key and not self.audit_encryption_key_file:
            missing.append("AUDIT_ENCRYPTION_KEY or AUDIT_ENCRYPTION_KEY_FILE")
        if not self.audit_lookup_key and not self.audit_lookup_key_file:
            missing.append("AUDIT_LOOKUP_KEY or AUDIT_LOOKUP_KEY_FILE")
        if missing:
            raise ValueError(
                f"Admin is enabled but required settings are missing: {', '.join(missing)}"
            )
        origin = self.admin_public_origin.rstrip("/")
        if not origin.startswith("https://") and not origin.startswith("http://localhost"):
            raise ValueError("ADMIN_PUBLIC_ORIGIN must use HTTPS except on localhost")
        if not self.oidc_redirect_uri.startswith(f"{origin}/"):
            raise ValueError("OIDC_REDIRECT_URI must be under ADMIN_PUBLIC_ORIGIN")
        scopes = set(self.oidc_scopes.split())
        if "openid" not in scopes:
            raise ValueError("OIDC_SCOPES must include openid")
        if not {value.strip() for value in self.admin_required_amr.split(",") if value.strip()}:
            raise ValueError("ADMIN_REQUIRED_AMR must not be empty")
        return self
