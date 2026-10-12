"""API key and multi-user authentication middleware for the OpenJarvis server."""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from openjarvis.auth.manager import get_user_manager
from openjarvis.auth.models import Role, User

logger = logging.getLogger(__name__)

_WS_AUTH_PROTOCOL = "openjarvis.auth.v1"
_WS_KEY_PROTOCOL_PREFIX = "openjarvis.key.b64url."
_MAX_REQUEST_BODY_BYTES = 25 * 1024 * 1024  # 25 MB max payload

_EXEMPT_EXACT_PATHS = {
    "/health",
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/hologram",
    "/favicon.ico",
    "/robots.txt",
}


def _api_keys_match(presented: str, expected: str) -> bool:
    """Compare API keys as bytes so non-ASCII values do not raise ``TypeError``."""
    if not presented or not expected:
        return False
    try:
        presented_bytes = presented.encode("utf-8")
        expected_bytes = expected.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return secrets.compare_digest(presented_bytes, expected_bytes)


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates session tokens or API keys on sensitive endpoints.

    In multi-user mode:
      - Validates session tokens (Bearer oj_usr_... or cookie oj_session)
      - Attaches request.state.user
      - Exempts registration, login, health checks, and static assets
      - Enforces strict tenant isolation and role-based permissions

    In single-user mode:
      - Validates OPENJARVIS_API_KEY if configured
      - Allows unauthenticated loopback access if no key is configured
      - Defaults request.state.user to a local admin user
    """

    def __init__(
        self,
        app,  # noqa: ANN001
        api_key: str = "",
        multi_user: bool = False,
    ) -> None:
        super().__init__(app)
        self._api_key = api_key or os.environ.get("OPENJARVIS_API_KEY", "")
        env_multi = os.environ.get("OPENJARVIS_MULTI_USER", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        self._multi_user = multi_user or env_multi

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        # Payload size enforcement to prevent denial of service
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > _MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        {"detail": "Payload too large. Maximum body size is 25 MB."},
                        status_code=413,
                    )
            except ValueError:
                pass

        # Browser CORS preflights never carry Authorization
        if self._is_cors_preflight(request):
            return await call_next(request)

        path = request.url.path

        # Extract credentials if present
        token = self._extract_token(request)
        user: Optional[User] = None
        if token and token.startswith("oj_usr_"):
            try:
                mgr = get_user_manager()
                user = mgr.validate_session(token)
            except Exception as exc:
                logger.debug("Session validation error: %s", exc)

        # Multi-user mode enforcement
        if self._multi_user:
            if self._is_exempt(path):
                request.state.user = user
                return await call_next(request)

            if self._requires_auth(path):
                if user is not None:
                    request.state.user = user
                    return await call_next(request)

                # Also accept admin server API key if presented
                if self._api_key and token and _api_keys_match(token, self._api_key):
                    request.state.user = User(
                        id="api_admin",
                        username="api_admin",
                        role=Role.ADMIN.value,
                    )
                    return await call_next(request)

                return JSONResponse(
                    {
                        "detail": "Authentication required. Please provide a valid session token or log in."
                    },
                    status_code=401,
                )

            request.state.user = user
            return await call_next(request)

        # Single-user mode
        if self._requires_auth(path) and not self._is_exempt(path):
            if self._api_key:
                if not token or not _api_keys_match(token, self._api_key):
                    # Check if valid user session token exists even in single-user mode
                    if user is not None:
                        request.state.user = user
                        return await call_next(request)
                    return JSONResponse(
                        {"detail": "Invalid or missing API key"},
                        status_code=401,
                    )
                request.state.user = User(
                    id="default",
                    username="local_admin",
                    role=Role.ADMIN.value,
                )
            else:
                request.state.user = user or User(
                    id="default",
                    username="local_admin",
                    role=Role.ADMIN.value,
                )
        else:
            request.state.user = user or User(
                id="default",
                username="local_admin",
                role=Role.ADMIN.value,
            )

        return await call_next(request)

    @staticmethod
    def _is_cors_preflight(request: Request) -> bool:
        return (
            request.method == "OPTIONS"
            and bool(request.headers.get("Origin"))
            and bool(request.headers.get("Access-Control-Request-Method"))
        )

    @staticmethod
    def _extract_token(request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        if auth:
            scheme, _, token = auth.partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
        cookie_token = request.cookies.get("oj_session")
        if cookie_token:
            return cookie_token.strip()
        return ""

    @staticmethod
    def _is_exempt(path: str) -> bool:
        """Paths that are exempt from mandatory authentication."""
        if path in _EXEMPT_EXACT_PATHS:
            return True
        if (
            path.startswith("/assets/")
            or path.startswith("/static/")
            or path.startswith("/webhooks/")
        ):
            return True
        return False

    @staticmethod
    def _requires_auth(path: str) -> bool:
        """Sensitive paths that require authentication."""
        if path.startswith("/api/auth/login") or path.startswith("/api/auth/register"):
            return False
        return (
            path.startswith("/v1/")
            or path.startswith("/api/")
            or path == "/metrics"
            or path.startswith("/metrics/")
            or path in ("/openapi.json", "/docs", "/redoc")
            or path.startswith("/docs/")
            or path.startswith("/redoc/")
        )


def generate_api_key() -> str:
    """Generate a new API key with ``oj_sk_`` prefix."""
    return f"oj_sk_{secrets.token_urlsafe(32)}"


def check_bind_safety(
    host: str,
    *,
    api_key: str,
    multi_user: bool = False,
) -> None:
    """Refuse to bind non-loopback without an API key or multi-user auth enabled."""
    import ipaddress
    import sys

    try:
        is_loop = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loop = host in ("localhost", "")

    if not is_loop and not api_key and not multi_user:
        logger.error(
            "Binding to %s requires OPENJARVIS_API_KEY to be set or "
            "multi-user authentication enabled (--multi-user).",
            host,
        )
        sys.exit(1)


def _websocket_key_protocol(api_key: str) -> str:
    """Encode an API key as a browser-safe WebSocket protocol token."""
    try:
        encoded = base64.urlsafe_b64encode(api_key.encode("utf-8")).decode("ascii")
    except UnicodeEncodeError:
        return ""
    return f"{_WS_KEY_PROTOCOL_PREFIX}{encoded.rstrip('=')}"


def _offered_websocket_auth(websocket) -> tuple[str, str | None]:  # noqa: ANN001
    offered = getattr(websocket, "scope", {}).get("subprotocols", [])
    if not isinstance(offered, (list, tuple)) or len(offered) != 2:
        return "", None
    if offered.count(_WS_AUTH_PROTOCOL) != 1:
        return "", None
    credentials = [
        protocol
        for protocol in offered
        if isinstance(protocol, str) and protocol != _WS_AUTH_PROTOCOL
    ]
    if len(credentials) != 1 or not credentials[0].startswith(_WS_KEY_PROTOCOL_PREFIX):
        return "", None
    if credentials[0] == _WS_KEY_PROTOCOL_PREFIX:
        return "", None
    return credentials[0], _WS_AUTH_PROTOCOL


def authenticate_websocket(
    websocket,  # noqa: ANN001
    expected_key: str,
    multi_user: bool = False,
) -> tuple[bool, str | None]:
    """Authenticate a WebSocket using session token or API key."""
    credential_protocol, selected_protocol = _offered_websocket_auth(websocket)

    env_multi = os.environ.get("OPENJARVIS_MULTI_USER", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    is_multi = multi_user or env_multi

    # Local single-user without expected key
    if not expected_key and not is_multi:
        return True, selected_protocol

    auth = websocket.headers.get("authorization", "")
    scheme, _, header_token = auth.partition(" ")
    raw_token = header_token if scheme.lower() == "bearer" else ""

    # Check session token
    if raw_token.startswith("oj_usr_"):
        try:
            mgr = get_user_manager()
            user = mgr.validate_session(raw_token)
            if user is not None:
                websocket.state.user = user
                return True, selected_protocol
        except Exception:
            pass

    header_valid = False
    if expected_key:
        header_valid = scheme.lower() == "bearer" and _api_keys_match(
            raw_token, expected_key
        )

    expected_protocol = _websocket_key_protocol(expected_key) if expected_key else ""
    protocol_valid = bool(credential_protocol and expected_protocol) and (
        _api_keys_match(credential_protocol, expected_protocol)
    )

    return header_valid or protocol_valid, selected_protocol


def websocket_authorized(
    websocket,  # noqa: ANN001
    expected_key: str,
    multi_user: bool = False,
) -> bool:
    """Return ``True`` if a WebSocket connection presents valid credentials."""
    return authenticate_websocket(websocket, expected_key, multi_user=multi_user)[0]
