import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.admin.logs import LogSearch
from app.admin.oidc import OIDCError, has_required_authentication, has_role
from app.admin.store import SessionIdentity

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)
SESSION_COOKIE = "raru_admin_session"
LOGIN_COOKIE = "raru_admin_login"


def _disabled() -> HTTPException:
    return HTTPException(status_code=404, detail="Administrator access is not configured")


async def current_admin(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> SessionIdentity:
    if not request.app.state.settings.admin_enabled:
        raise _disabled()
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    identity = await asyncio.to_thread(request.app.state.admin_store.get_session, session_token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Session expired")
    return identity


@router.get("/auth/login", include_in_schema=False)
async def login(request: Request):
    settings = request.app.state.settings
    if not settings.admin_enabled:
        raise _disabled()
    url, challenge = await request.app.state.oidc.authorization_url()
    await asyncio.to_thread(
        request.app.state.admin_store.create_login_challenge,
        challenge["state"],
        challenge["binding"],
        challenge["verifier"],
        challenge["nonce"],
    )
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        LOGIN_COOKIE,
        challenge["binding"],
        max_age=300,
        httponly=True,
        secure=settings.admin_secure_cookies,
        samesite="lax",
        path="/api/admin/auth/callback",
    )
    return response


@router.get("/auth/callback", include_in_schema=False)
async def callback(
    request: Request,
    code: str,
    state: str,
    binding: Annotated[str | None, Cookie(alias=LOGIN_COOKIE)] = None,
):
    settings = request.app.state.settings
    if not settings.admin_enabled:
        raise _disabled()
    if not binding:
        raise HTTPException(status_code=400, detail="Login challenge cookie is missing")
    challenge = await asyncio.to_thread(
        request.app.state.admin_store.consume_login_challenge, state, binding
    )
    if challenge is None:
        raise HTTPException(status_code=400, detail="Login challenge is invalid or expired")
    verifier, nonce = challenge
    try:
        claims = await request.app.state.oidc.exchange(code, verifier, nonce)
    except (OIDCError, httpx.HTTPError):
        logger.warning("admin_login_failed", extra={"fields": {"reason": "oidc_validation"}})
        raise HTTPException(status_code=401, detail="Administrator login failed") from None
    required_methods = {
        value.strip() for value in settings.admin_required_amr.split(",") if value.strip()
    }
    if (
        not claims.get("email")
        or (settings.admin_require_verified_email and claims.get("email_verified") is not True)
        or not has_required_authentication(claims, required_methods)
    ):
        logger.warning("admin_login_failed", extra={"fields": {"reason": "mfa_required"}})
        raise HTTPException(status_code=403, detail="Password and email MFA are required")
    if not has_role(claims, settings.admin_role_claim, settings.admin_required_role):
        logger.warning("admin_login_failed", extra={"fields": {"reason": "role_required"}})
        raise HTTPException(status_code=403, detail="Administrator role is required")
    token, _csrf, absolute = await asyncio.to_thread(
        request.app.state.admin_store.create_session,
        subject=str(claims["sub"]),
        email=claims.get("email"),
        name=claims.get("name") or claims.get("preferred_username"),
    )
    response = RedirectResponse("/admin", status_code=302)
    response.delete_cookie(LOGIN_COOKIE, path="/api/admin/auth/callback")
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max(1, int((absolute - datetime.now(UTC)).total_seconds())),
        httponly=True,
        secure=settings.admin_secure_cookies,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/session")
async def session_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not request.app.state.settings.admin_enabled:
        return {"enabled": False, "authenticated": False}
    token = request.cookies.get(SESSION_COOKIE)
    identity = (
        await asyncio.to_thread(request.app.state.admin_store.get_session, token) if token else None
    )
    if identity is None:
        return {"enabled": True, "authenticated": False}
    return {
        "enabled": True,
        "authenticated": True,
        "name": identity.name,
        "email": identity.email,
        "expires_at": identity.absolute_expires_at,
        "csrf_token": identity.csrf_token,
    }


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    csrf: Annotated[str, Header(alias="X-CSRF-Token")],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
):
    if not token or not await asyncio.to_thread(
        request.app.state.admin_store.delete_session, token, csrf
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/v1/overview")
async def overview(request: Request, _admin: Annotated[SessionIdentity, Depends(current_admin)]):
    return await asyncio.to_thread(request.app.state.admin_store.overview)


@router.get("/v1/monitoring")
async def monitoring(request: Request, _admin: Annotated[SessionIdentity, Depends(current_admin)]):
    try:
        return await request.app.state.monitoring.status()
    except (RuntimeError, httpx.HTTPError, ValueError):
        raise HTTPException(status_code=503, detail="Monitoring storage is unavailable") from None


@router.get("/v1/requests")
async def requests_list(
    request: Request,
    _admin: Annotated[SessionIdentity, Depends(current_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: datetime | None = None,
):
    return {
        "items": await asyncio.to_thread(
            request.app.state.admin_store.list_queries, limit=limit, before=before
        )
    }


@router.get("/v1/requests/{event_id}")
async def request_detail(
    event_id: str,
    request: Request,
    admin: Annotated[SessionIdentity, Depends(current_admin)],
):
    result = await asyncio.to_thread(request.app.state.admin_store.get_query, event_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Request record was not found")
    await asyncio.to_thread(
        request.app.state.admin_store.record_admin_event,
        admin.subject,
        "request_detail_viewed",
        event_id,
    )
    return result


@router.post("/v1/logs/search")
async def log_search(
    query: LogSearch,
    request: Request,
    admin: Annotated[SessionIdentity, Depends(current_admin)],
):
    try:
        items = await request.app.state.loki.search(query)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except (RuntimeError, httpx.HTTPError):
        raise HTTPException(status_code=503, detail="Log storage is unavailable") from None
    await asyncio.to_thread(
        request.app.state.admin_store.record_admin_event,
        admin.subject,
        "logs_searched",
        detail={"count": len(items)},
    )
    return {"items": items}
