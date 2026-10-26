from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.admin.crypto import AuditCipher, decode_key, read_secret
from app.admin.logs import LokiClient
from app.admin.monitoring import PrometheusClient
from app.admin.oidc import OIDCClient
from app.admin.store import AdminStore
from app.config import Settings


def create_admin_services(settings: Settings):
    if not settings.admin_enabled:
        return (
            None,
            None,
            LokiClient(
                settings.loki_url,
                tenant_id=settings.loki_tenant_id,
                environment=settings.log_environment,
                max_range_days=settings.admin_log_max_range_days,
                max_limit=settings.admin_log_query_max_limit,
            ),
            PrometheusClient(settings.prometheus_url),
        )
    encryption_key = decode_key(
        read_secret(
            settings.audit_encryption_key,
            settings.audit_encryption_key_file,
            "AUDIT_ENCRYPTION_KEY",
        ),
        "AUDIT_ENCRYPTION_KEY",
    )
    lookup_key = decode_key(
        read_secret(
            settings.audit_lookup_key,
            settings.audit_lookup_key_file,
            "AUDIT_LOOKUP_KEY",
        ),
        "AUDIT_LOOKUP_KEY",
    )
    cipher = AuditCipher(encryption_key, lookup_key)
    engine_options = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite") and ":memory:" in settings.database_url:
        engine_options.update(
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    engine = create_engine(settings.database_url, **engine_options)
    store = AdminStore(
        engine,
        cipher,
        session_idle_seconds=settings.admin_session_idle_seconds,
        session_absolute_seconds=settings.admin_session_absolute_seconds,
        result_retention_days=settings.query_result_retention_days,
        metadata_retention_days=settings.query_metadata_retention_days,
        admin_audit_retention_days=settings.admin_audit_retention_days,
    )
    oidc_secret = read_secret(
        settings.oidc_client_secret,
        settings.oidc_client_secret_file,
        "OIDC_CLIENT_SECRET",
    )
    oidc = OIDCClient(
        settings.oidc_issuer,
        settings.oidc_client_id,
        oidc_secret,
        settings.oidc_redirect_uri,
        settings.oidc_scopes,
    )
    loki = LokiClient(
        settings.loki_url,
        tenant_id=settings.loki_tenant_id,
        environment=settings.log_environment,
        max_range_days=settings.admin_log_max_range_days,
        max_limit=settings.admin_log_query_max_limit,
    )
    return store, oidc, loki, PrometheusClient(settings.prometheus_url)
