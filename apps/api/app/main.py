import logging
from asyncio import Lock as AsyncLock
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.routers.images import IMAGE_TTL
from app.routers.images import router as images_router
from app.routers.players import router
from app.services.cache import JsonCache
from app.services.osu_client import OsuClient, ServiceError
from app.services.rate_limit import RateLimiter
from app.services.usage import UsageStats


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Rarsu查分器 API", version="1.0.0")
    app.state.settings = settings
    app.state.cache = JsonCache(
        settings.cache_path, settings.cache_timeout, settings.cache_retention
    )
    app.state.not_found = JsonCache(
        settings.cache_path / "not-found",
        settings.negative_cache_ttl,
        settings.negative_cache_ttl,
    )
    app.state.images = JsonCache(
        settings.cache_path / "images", IMAGE_TTL, max(IMAGE_TTL, settings.cache_retention)
    )
    app.state.image_lock = AsyncLock()
    app.state.stats = UsageStats(settings.stats_path)
    app.state.osu = OsuClient(settings)
    app.state.limiter = RateLimiter(settings.rate_limit_window)
    app.state.fetch_lock = Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["X-Osu-Client-Id", "X-Osu-Client-Secret", "X-Visitor-Id"],
        expose_headers=["X-Cache", "X-Cache-TTL", "Retry-After"],
    )

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
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


logging.getLogger("ossapi").setLevel(logging.WARNING)
app = create_app()
