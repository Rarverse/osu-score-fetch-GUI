import asyncio
import logging
import time
import uuid
from asyncio import Lock as AsyncLock
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response as StarletteResponse

from app.admin.router import router as admin_router
from app.admin.services import create_admin_services
from app.config import Settings
from app.logging_setup import configure_logging, request_id, safe_error_fields, score_query_log
from app.routers.images import router as images_router
from app.routers.images import warm_images
from app.routers.players import router
from app.services.cache import JsonCache
from app.services.osu_client import OsuClient, ServiceError
from app.services.rate_limit import RateLimiter, UpstreamLimiter
from app.services.usage import UsageStats

logger = logging.getLogger(__name__)
REQUESTS = Counter("raru_http_requests_total", "HTTP requests", ("route", "method", "status"))
DURATION = Histogram(
    "raru_http_request_duration_seconds", "HTTP request duration", ("route", "method")
)


async def admin_cleanup_loop(store) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(store.cleanup)
        except Exception as error:
            logger.error("admin_cleanup_failed", extra={"fields": safe_error_fields(error)})


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = None
    if app.state.settings.admin_enabled:
        await asyncio.to_thread(app.state.admin_store.check)
        await asyncio.to_thread(app.state.admin_store.cleanup)
        cleanup_task = asyncio.create_task(admin_cleanup_loop(app.state.admin_store))
    logger.info(
        "api_started",
        extra={
            "fields": {
                "api_requests_per_minute": app.state.settings.osu_requests_per_minute,
                "rate_limit_window": app.state.settings.rate_limit_window,
                "rate_limit_per_ip": app.state.settings.rate_limit_per_ip,
                "rate_limit_per_player": app.state.settings.rate_limit_per_player,
                "cache_ttl": app.state.settings.cache_timeout,
                "negative_cache_ttl": app.state.settings.negative_cache_ttl,
                "log_format": app.state.settings.log_format,
                "log_level": app.state.settings.log_level,
                "site_credentials_configured": bool(app.state.settings.osu_credentials),
            }
        },
    )
    warmer = asyncio.create_task(warm_images(app.state))
    try:
        yield
    finally:
        warmer.cancel()
        with suppress(asyncio.CancelledError):
            await warmer
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
        logger.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_format, settings.log_level)
    app = FastAPI(title="Raru 查分器 API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.cache = JsonCache(
        settings.cache_path, settings.cache_timeout, settings.cache_retention
    )
    app.state.not_found = JsonCache(
        settings.cache_path / "not-found",
        settings.negative_cache_ttl,
        settings.negative_cache_ttl,
    )
    app.state.images = JsonCache(settings.cache_path / "images", ttl=None, retention=None)
    app.state.image_lock = AsyncLock()
    app.state.image_limiter = UpstreamLimiter(settings.osu_requests_per_minute, budget="images")
    app.state.image_queue = asyncio.Queue(maxsize=256)
    app.state.image_pending = set()
    app.state.stats = UsageStats(settings.stats_path)
    app.state.osu = OsuClient(settings)
    app.state.limiter = RateLimiter(settings.rate_limit_window)
    app.state.fetch_lock = Lock()
    (
        app.state.admin_store,
        app.state.oidc,
        app.state.loki,
        app.state.monitoring,
    ) = create_admin_services(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["X-Osu-Client-Id", "X-Osu-Client-Secret", "X-Visitor-Id"],
        expose_headers=["X-Cache", "X-Cache-TTL", "Retry-After", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        identifier = uuid.uuid4().hex
        token = request_id.set(identifier)
        query_fields = {
            "query": None,
            "username": None,
            "user_id": None,
            "api_slot": None,
            "cache": "NOT_CHECKED",
            "upstream_requests": 0,
            "token_refreshed": False,
        }
        query_token = score_query_log.set(query_fields)
        started = time.perf_counter()
        started_at = datetime.now(UTC)
        credentials = (
            "custom"
            if "x-osu-client-id" in request.headers or "x-osu-client-secret" in request.headers
            else "site"
        )
        if request.url.path != "/health":
            logger.info(
                "request_started",
                extra={"fields": {"method": request.method, "credentials": credentials}},
            )
        try:
            try:
                response = await call_next(request)
            except Exception as error:
                request.state.error_code = "INTERNAL_ERROR"
                logger.error("request_failed", extra={"fields": safe_error_fields(error)})
                content = {"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用。"}}
                request.state.audit_result = content
                response = JSONResponse(
                    status_code=500,
                    content=content,
                    headers={"Cache-Control": "no-store"},
                )
            response.headers["X-Request-ID"] = identifier
            if request.url.path.startswith("/api/admin/"):
                response.headers["Cache-Control"] = "no-store"
                response.headers["Pragma"] = "no-cache"
            route = request.scope.get("route")
            route_name = getattr(route, "path", "unmatched")
            duration_seconds = time.perf_counter() - started
            if route_name != "/internal/metrics":
                REQUESTS.labels(route_name, request.method, str(response.status_code)).inc()
                DURATION.labels(route_name, request.method).observe(duration_seconds)
            if request.url.path != "/health" or response.status_code >= 400:
                fields = {
                    "method": request.method,
                    "route": route_name,
                    "status": response.status_code,
                    "duration_ms": round(duration_seconds * 1000, 1),
                    "credentials": credentials,
                }
                for header, field in (
                    ("X-Cache", "cache"),
                    ("X-Cache-TTL", "cache_ttl"),
                    ("Retry-After", "retry_after"),
                ):
                    if value := response.headers.get(header):
                        fields[field] = value
                if code := getattr(request.state, "error_code", None):
                    fields["error_code"] = code
                if fields["route"] == "/api/v1/players/{username}/scores":
                    safe_query_fields = {
                        key: value
                        for key, value in query_fields.items()
                        if key not in {"query", "username", "user_id"}
                    }
                    logger.log(
                        logging.WARNING if response.status_code >= 400 else logging.INFO,
                        "scores_query_completed",
                        extra={"fields": {**safe_query_fields, **fields}},
                    )
                logger.log(
                    logging.WARNING if response.status_code >= 400 else logging.INFO,
                    "request_completed",
                    extra={"fields": fields},
                )
                if (
                    settings.admin_enabled
                    and fields["route"] == "/api/v1/players/{username}/scores"
                ):
                    audit_fields = {**query_fields, **fields}
                    if audit_fields.get("query") is None:
                        audit_fields["query"] = request.path_params.get("username")
                    try:
                        await asyncio.to_thread(
                            app.state.admin_store.record_query,
                            request_id=identifier,
                            started_at=started_at,
                            completed_at=datetime.now(UTC),
                            fields=audit_fields,
                            status=response.status_code,
                            duration_ms=fields["duration_ms"],
                            credentials=credentials,
                            result=getattr(request.state, "audit_result", None),
                        )
                    except Exception as error:
                        logger.error(
                            "audit_write_failed", extra={"fields": safe_error_fields(error)}
                        )
            return response
        finally:
            score_query_log.reset(query_token)
            request_id.reset(token)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        request.state.error_code = error.code
        logger.warning(
            "request_rejected",
            extra={
                "fields": {
                    "error_code": error.code,
                    "status": error.status,
                    **({"retry_after": error.retry_after} if error.retry_after is not None else {}),
                }
            },
        )
        headers = {"Cache-Control": "no-store"}
        if error.retry_after is not None:
            headers["Retry-After"] = str(error.retry_after)
        if error.cache:
            headers["X-Cache"] = error.cache
        if error.cache_ttl is not None:
            headers["X-Cache-TTL"] = str(error.cache_ttl)
        content = {"error": {"code": error.code, "message": error.message}}
        request.state.audit_result = content
        return JSONResponse(
            status_code=error.status,
            content=content,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        request.state.error_code = "INVALID_REQUEST"
        content = {
            "error": {"code": "INVALID_REQUEST", "message": "请检查 mode、type 与 limit 参数。"}
        }
        request.state.audit_result = content
        return JSONResponse(
            status_code=422,
            content=content,
        )

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok", "modes": ["osu", "taiko", "fruits", "mania"]}

    @app.get("/internal/metrics", include_in_schema=False)
    def metrics():
        return StarletteResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(router)
    app.include_router(images_router)
    app.include_router(admin_router)
    return app


app = create_app()
