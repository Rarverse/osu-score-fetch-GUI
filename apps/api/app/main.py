import asyncio
import logging
import time
import uuid
from asyncio import Lock as AsyncLock
from contextlib import asynccontextmanager, suppress
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.logging_setup import configure_logging, request_id, safe_error_fields
from app.routers.images import router as images_router
from app.routers.images import warm_images
from app.routers.players import router
from app.services.cache import JsonCache
from app.services.osu_client import OsuClient, ServiceError
from app.services.rate_limit import RateLimiter, UpstreamLimiter
from app.services.usage import UsageStats

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
                "site_credentials_configured": bool(
                    app.state.settings.osu_client_id and app.state.settings.osu_client_secret
                ),
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
        logger.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_format, settings.log_level)
    app = FastAPI(title="Rarsu查分器 API", version="1.0.0", lifespan=lifespan)
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
        started = time.perf_counter()
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
                response = JSONResponse(
                    status_code=500,
                    content={"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用。"}},
                    headers={"Cache-Control": "no-store"},
                )
            response.headers["X-Request-ID"] = identifier
            if request.url.path != "/health" or response.status_code >= 400:
                route = request.scope.get("route")
                fields = {
                    "method": request.method,
                    "route": getattr(route, "path", "unmatched"),
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
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
                logger.log(
                    logging.WARNING if response.status_code >= 400 else logging.INFO,
                    "request_completed",
                    extra={"fields": fields},
                )
            return response
        finally:
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
        return JSONResponse(
            status_code=error.status,
            content={"error": {"code": error.code, "message": error.message}},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        request.state.error_code = "INVALID_REQUEST"
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "INVALID_REQUEST", "message": "请检查 mode、type 与 limit 参数。"}
            },
        )

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok", "modes": ["osu", "taiko", "fruits", "mania"]}

    app.include_router(router)
    app.include_router(images_router)
    return app


app = create_app()
