"""Authentication endpoints for user registration, login, logout, and profile."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from openjarvis.auth.manager import get_user_manager
from openjarvis.security.rate_limiter import RateLimitConfig, RateLimiter

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# IP-based rate limiters for auth abuse prevention
_login_limiter = RateLimiter(
    RateLimitConfig(requests_per_minute=10, burst_size=5, enabled=True)
)
_register_limiter = RateLimiter(
    RateLimitConfig(requests_per_minute=5, burst_size=3, enabled=True)
)


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


def _get_client_ip(request: Request) -> str:
    """Extract client IP, honoring reverse-proxy headers if present."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@auth_router.post("/register")
async def register(req: RegisterRequest, request: Request, response: Response):
    """Register a new user account."""
    ip = _get_client_ip(request)
    allowed, wait_time = _register_limiter.check(f"register:{ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many registration requests. Please wait {wait_time:.1f}s.",
        )

    mgr = get_user_manager()
    try:
        user = mgr.register(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    token = mgr.create_session(user.id)
    is_secure = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
    )
    response.set_cookie(
        key="oj_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=86400 * 7,
    )
    return {
        "status": "registered",
        "token": token,
        "user": user.to_dict(),
    }


@auth_router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Authenticate and obtain session token."""
    ip = _get_client_ip(request)
    allowed, wait_time = _login_limiter.check(f"login:{ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Please wait {wait_time:.1f}s.",
        )

    mgr = get_user_manager()
    if mgr.is_locked(req.username):
        raise HTTPException(
            status_code=423,
            detail="Account is temporarily locked due to repeated failed logins. Please try again later.",
        )

    user = mgr.authenticate(req.username, req.password, ip=ip)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = mgr.create_session(user.id)
    is_secure = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
    )
    response.set_cookie(
        key="oj_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=86400 * 7,
    )
    return {
        "status": "authenticated",
        "token": token,
        "user": user.to_dict(),
    }


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """Revoke active session token."""
    token = _extract_token(request)
    if token:
        mgr = get_user_manager()
        mgr.revoke_session(token)

    response.delete_cookie("oj_session")
    return {"status": "logged_out"}


@auth_router.get("/me")
async def get_current_user_profile(request: Request):
    """Get active user profile."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": user.to_dict() if hasattr(user, "to_dict") else user}


@auth_router.delete("/account")
async def delete_account(request: Request, response: Response):
    """Delete current user account and all personal data."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mgr = get_user_manager()
    mgr.delete_user(user.id)
    response.delete_cookie("oj_session")
    return {"status": "account_deleted"}


def _extract_token(request: Request) -> Optional[str]:
    """Extract session token from Authorization header or cookie."""
    auth = request.headers.get("Authorization", "")
    if auth:
        scheme, _, token = auth.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    cookie_token = request.cookies.get("oj_session")
    if cookie_token:
        return cookie_token.strip()
    return None
