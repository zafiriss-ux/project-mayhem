"""Phase 8B FastAPI app with auth layer wired in."""

from __future__ import annotations

import json
import logging
import secrets
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from titan.api.auth import (
    ACCESS_COOKIE_NAME,
    ACCESS_TOKEN_TTL,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL,
    AuthError,
    AuthStore,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_jwt_keys_at_startup,
)
from titan.api.dependencies import (
    get_auth_store,
    require_coach,
    require_coach_athlete_access,
)
from titan.api.models import AuthUser, LoginRequest, LoginResponse, TokenPayload
from titan.config.thresholds import RATE_LIMITER_MAX_KEYS
from titan.core.structured_events import EventSeverity, structured_event_payload

_RATE_LIMIT_WINDOW_SECONDS = 60.0
_log = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "titan_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = {"/health", "/readyz", "/auth/login"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in CSRF_SAFE_METHODS:
            return await call_next(request)

        if request.url.path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)

        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP: restrictive for API; HSTS omitted until TLS termination is resolved (C-2)
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response


@dataclass(frozen=True)
class RateLimitConfig:
    coach_per_minute: int = 100
    athlete_per_minute: int = 30


class AuthenticatedRateLimiter:
    """In-memory fixed-window limiter keyed by authenticated identity and endpoint."""

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig()
        self._requests: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        user = self._resolve_user(request)
        if user is None:
            return await call_next(request)

        key = (user.id, user.role, f"{request.method}:{request.url.path}")
        limit = self._limit_for_role(user.role)
        now = monotonic()

        with self._lock:
            bucket = self._requests[key]
            cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return Response(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    media_type="application/json",
                    content='{"detail":"Rate limit exceeded"}',
                )
            bucket.append(now)
            if len(self._requests) > RATE_LIMITER_MAX_KEYS:
                self._evict_lru_keys()

        return await call_next(request)

    def _evict_lru_keys(self) -> None:
        """Evict least-recently-used keys to stay within RATE_LIMITER_MAX_KEYS.

        Must be called while ``self._lock`` is held.
        Last-access for a key is the most recent timestamp in its deque
        (rightmost element), or 0.0 for an empty deque.
        """
        n_to_evict = len(self._requests) - RATE_LIMITER_MAX_KEYS
        if n_to_evict <= 0:
            return
        sorted_keys = sorted(
            self._requests.keys(),
            key=lambda k: self._requests[k][-1] if self._requests[k] else 0.0,
        )
        for k in sorted_keys[:n_to_evict]:
            del self._requests[k]
        _log.warning(
            json.dumps(
                structured_event_payload(
                    "rate_limiter",
                    "limiter_eviction",
                    severity=EventSeverity.WARNING,
                    keys_evicted=n_to_evict,
                ),
                default=str,
            )
        )

    def _resolve_user(self, request: Request) -> AuthUser | None:
        token = request.cookies.get(ACCESS_COOKIE_NAME)
        if not token:
            return None

        try:
            payload = decode_token(token, expected_type="access")
        except AuthError:
            return None

        store = request.app.state.auth_store
        if not isinstance(store, AuthStore):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auth store unavailable",
            )

        user = store.get_user(payload.sub)
        if user is None or not user.is_active:
            return None
        return user

    def _limit_for_role(self, role: str) -> int:
        if role == "COACH":
            return self._config.coach_per_minute
        return self._config.athlete_per_minute


class LoginRateLimiter:
    """IP-based fixed-window limiter for pre-auth endpoints."""

    LOGIN_RATE_LIMIT_ATTEMPTS: int = 10
    LOGIN_RATE_LIMIT_WINDOW: float = 60.0

    def __init__(self, *, limit: int | None = None, window: float | None = None) -> None:
        self._limit = limit if limit is not None else self.LOGIN_RATE_LIMIT_ATTEMPTS
        self._window = window if window is not None else self.LOGIN_RATE_LIMIT_WINDOW
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, client_ip: str) -> bool:
        with self._lock:
            now = monotonic()
            bucket = self._requests[client_ip]
            cutoff = now - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True


class AuditActionType(StrEnum):
    VIEW_DATA = "VIEW_DATA"
    SUBMIT_OVERRIDE = "SUBMIT_OVERRIDE"
    EXPORT_DATA = "EXPORT_DATA"
    DELETE_DATA = "DELETE_DATA"


@dataclass(frozen=True)
class CoachAuditRow:
    coach_id: str
    athlete_id: str
    action_type: str
    resource: str
    action_detail: dict[str, Any] | None
    performed_at: datetime


class CoachAuditStore:
    """In-memory audit persistence adapter for API layer."""

    def __init__(self) -> None:
        self._rows: list[CoachAuditRow] = []

    def log_action(self, row: CoachAuditRow) -> None:
        self._rows.append(row)

    @property
    def rows(self) -> list[CoachAuditRow]:
        return list(self._rows)


def create_app(
    auth_store: AuthStore | None = None,
    audit_store: CoachAuditStore | None = None,
    db: Any = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN001
        from titan.observability.metrics import get_metrics
        validate_jwt_keys_at_startup()
        get_metrics().counter("api_startup")
        yield

    app = FastAPI(title="TITAN OS API", version="8B", lifespan=lifespan)
    app.state.auth_store = auth_store or AuthStore()
    app.state.audit_store = audit_store or CoachAuditStore()
    app.state.db = db

    if db is not None:
        _db_path = str(getattr(db, "db_path", ""))
        if _db_path != ":memory:" and "titan_core.db" not in _db_path:
            raise RuntimeError(
                f"Wrong DB: {_db_path}. "
                "Must use titan_core.db — titan.db is stale."
            )

    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    rate_limiter = AuthenticatedRateLimiter()
    login_rate_limiter = LoginRateLimiter()
    refresh_rate_limiter = LoginRateLimiter(limit=5, window=60.0)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        return await rate_limiter(request, call_next)

    @app.middleware("http")
    async def coach_audit_middleware(request: Request, call_next):
        response = await call_next(request)
        _audit_request(request)
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        checks: dict[str, object] = {}
        ok = True

        try:
            _db = request.app.state.db
            if _db is None:
                checks["db_error"] = "no db attached"
                ok = False
            else:
                db_path = str(getattr(_db, "db_path", ""))
                checks["db_file"] = "titan_core.db" in db_path
                if not checks["db_file"]:
                    ok = False

                checks["db_reachable"] = _db.is_db_reachable()
                if not checks["db_reachable"]:
                    ok = False

        except Exception as e:  # noqa: BLE001
            checks["db_error"] = str(e)
            ok = False

        return JSONResponse(
            status_code=200 if ok else 503,
            content={"ready": ok, "checks": checks},
        )

    @app.get("/api/csrf-token")
    def get_csrf_token(response: Response) -> dict[str, str]:
        """Issue a CSRF token cookie. Call this before any state-changing request."""
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            httponly=False,
            secure=True,
            samesite="strict",
        )
        return {"csrf_token": token}

    @app.post("/auth/login", response_model=LoginResponse)
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        store: AuthStore = Depends(get_auth_store),
    ) -> Any:
        client_ip = request.client.host if request.client else "unknown"
        if not login_rate_limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts",
            )

        if store.is_locked_out(payload.username):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account temporarily locked",
            )

        user = store.verify_credentials(payload.username, payload.password)
        if user is None:
            store.record_failed_attempt(payload.username)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        store.clear_failed_attempts(payload.username)
        access_token, access_expires_at = create_access_token(user)
        refresh_token, _, _ = create_refresh_token(user, store)
        _set_auth_cookies(response, access_token, refresh_token)
        return LoginResponse(access_token=access_token, expires_at=access_expires_at)

    @app.post("/auth/refresh", response_model=LoginResponse)
    def refresh(
        request: Request,
        response: Response,
        store: AuthStore = Depends(get_auth_store),
    ) -> Any:
        client_ip = request.client.host if request.client else "unknown"
        if not refresh_rate_limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many refresh attempts. Wait 60 seconds.",
            )
        refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

        if payload.jti is None or not store.is_refresh_token_active(payload.jti):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

        user = store.get_user(payload.sub)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

        store.revoke_refresh_token(payload.jti)
        access_token, access_expires_at = create_access_token(user)
        new_refresh_token, _, _ = create_refresh_token(user, store)
        _set_auth_cookies(response, access_token, new_refresh_token)
        return LoginResponse(access_token=access_token, expires_at=access_expires_at)

    @app.post("/auth/logout")
    def logout(
        request: Request,
        response: Response,
        store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, str]:
        refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
        if refresh_token:
            try:
                payload = decode_token(refresh_token, expected_type="refresh")
            except AuthError:
                payload = None
            if payload and payload.jti:
                store.revoke_refresh_token(payload.jti)

        response.delete_cookie(ACCESS_COOKIE_NAME)
        response.delete_cookie(REFRESH_COOKIE_NAME)
        return {"status": "logged_out"}

    @app.get("/athletes/{athlete_id}/dashboard")
    def athlete_dashboard(
        athlete_id: str,
        current_user: AuthUser = Depends(require_coach_athlete_access),
    ) -> dict[str, str]:
        if current_user.role != "COACH" and current_user.athlete_id != athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete isolation violation")
        return {"athlete_id": athlete_id, "viewer": current_user.id}

    @app.post("/coach/notes")
    def create_coach_note(_: dict[str, Any], __: AuthUser = Depends(require_coach)) -> dict[str, str]:
        return {"status": "created"}

    @app.post("/coach/overrides")
    def submit_coach_override(athlete_id: str, _: dict[str, Any], __: AuthUser = Depends(require_coach)) -> dict[str, str]:
        return {"status": "override_submitted", "athlete_id": athlete_id}

    @app.get("/coach/export")
    def export_health_data(athlete_id: str, _: AuthUser = Depends(require_coach)) -> dict[str, str]:
        return {"status": "export_ready", "athlete_id": athlete_id}

    @app.delete("/coach/athlete-data")
    def delete_athlete_data(athlete_id: str, _: AuthUser = Depends(require_coach)) -> dict[str, str]:
        return {"status": "deleted", "athlete_id": athlete_id}

    return app


def _get_user_from_request(request: Request) -> TokenPayload | None:
    """Decode access JWT from the request for audit DB writes only.

    Auth has already passed at this point; this reads the token a second time
    as a belt-and-suspenders path for DB persistence when request.state.current_user
    is unavailable. Returns a TokenPayload or None on any failure.
    """
    try:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get(ACCESS_COOKIE_NAME)
        if not token:
            return None
        return decode_token(token, "access")
    except Exception:
        return None


def _audit_request(request: Request) -> None:
    route = _match_audit_route(request)
    if route is None:
        return

    current_user = getattr(request.state, "current_user", None)
    if not isinstance(current_user, AuthUser) or current_user.role != "COACH":
        return

    athlete_id = _resolve_athlete_id(request)
    if athlete_id is None:
        return

    detail = _build_action_detail(request, route)
    row = CoachAuditRow(
        coach_id=current_user.id,
        athlete_id=athlete_id,
        action_type=route["action_type"],
        resource=route["resource"],
        action_detail=detail,
        performed_at=datetime.now(UTC),
    )
    request.app.state.audit_store.log_action(row)

    token_payload = _get_user_from_request(request)
    db = getattr(request.app.state, "db", None)
    if token_payload and db is not None:
        try:
            db.log_coach_action(
                coach_id=token_payload.sub,
                action_type=route["action_type"],
                target_athlete_id=athlete_id,
                resource=route["resource"],
            )
        except Exception as exc:
            from titan.observability.metrics import get_metrics
            _log.error("audit_db_persist_failed", extra={"error": str(exc)}, exc_info=True)
            get_metrics().counter("audit_write_failure")


def _match_audit_route(request: Request) -> dict[str, str] | None:
    method = request.method
    if method == "GET" and request.url.path.startswith("/athletes/") and request.url.path.endswith("/dashboard"):
        return {"action_type": AuditActionType.VIEW_DATA.value, "resource": "athlete_dashboard"}
    if method == "POST" and request.url.path == "/coach/overrides":
        return {"action_type": AuditActionType.SUBMIT_OVERRIDE.value, "resource": "coach_override"}
    if method == "GET" and request.url.path == "/coach/export":
        return {"action_type": AuditActionType.EXPORT_DATA.value, "resource": "health_export"}
    if method == "DELETE" and request.url.path == "/coach/athlete-data":
        return {"action_type": AuditActionType.DELETE_DATA.value, "resource": "athlete_data"}
    return None


def _resolve_athlete_id(request: Request) -> str | None:
    path_params = request.path_params
    if "athlete_id" in path_params:
        value = path_params["athlete_id"]
        return value if isinstance(value, str) else None

    athlete_id = request.query_params.get("athlete_id")
    return athlete_id if athlete_id else None


def _build_action_detail(request: Request, route: dict[str, str]) -> dict[str, Any] | None:
    query = dict(request.query_params)
    if route["action_type"] == AuditActionType.SUBMIT_OVERRIDE.value:
        return {"source": "coach_override_endpoint", "query": query}
    return {"query": query} if query else None


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
    )


app = None  # must use create_app() directly; see titan.api.main:create_app
