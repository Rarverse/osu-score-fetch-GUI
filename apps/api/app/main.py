import logging
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings
from app.routers.players import router
from app.services.cache import JsonCache
from app.services.osu_client import OsuClient, ServiceError
from app.services.rate_limit import RateLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="rarverse osu! scores API", version="1.0.0")
    app.state.settings = settings
    app.state.cache = JsonCache(settings.cache_path, settings.cache_timeout)
    app.state.osu = OsuClient(settings)
    app.state.limiter = RateLimiter(settings.rate_limit_window)
    app.state.fetch_lock = Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        expose_headers=["X-Cache", "Retry-After"],
    )

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        headers = {"Cache-Control": "no-store"}
        if hasattr(error, "retry_after"):
            headers["Retry-After"] = str(error.retry_after)
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
    return app


logging.getLogger("ossapi").setLevel(logging.WARNING)
app = create_app()
