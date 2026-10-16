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
from prometheus_client import make_asgi_app as _prom_asgi
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
from titan.api.models import AuthUser, LoginRequest, LoginResponse
from titan.config.settings import get_settings
from titan.config.thresholds import RATE_LIMITER_MAX_KEYS
from titan.core.structured_events import EventSeverity, structured_event_payload

_RATE_LIMIT_WINDOW_SECONDS = 60.0
_log = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "titan_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = {"/health", "/readyz", "/auth/login", "/metrics", "/api/csrf-token"}


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


class _BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Request body too large")


class BodySizeLimitMiddleware:
    """RBP-01 (AGENTS §8.11): cap request bodies before they are parsed.

    A declared Content-Length over the limit gets 413 before any read; a body
    without one (chunked) is counted while it streams and stopped at the limit.
    Pure ASGI, so it sees the raw byte stream before any other layer reads it.
    """

    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            if not declared.isdigit():
                await JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})(scope, receive, send)
                return
            if int(declared) > self.max_bytes:
                await self._reject(scope, receive, send)
                return

        received = 0
        started = False
        exceeded = False

        async def limited_receive() -> Any:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Any) -> None:
            nonlocal started
            # Inner layers may turn the read error into their own response
            # (FastAPI answers 400 when a wrapped body read fails); drop it.
            if exceeded and not started:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except Exception:
            if not exceeded or started:
                raise
        if exceeded and not started:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Any, receive: Any, send: Any) -> None:
        _log.warning("request_body_too_large", extra={"path": scope.get("path"), "limit": self.max_bytes})
        await JSONResponse(status_code=413, content={"detail": "Request body too large"})(scope, receive, send)


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
            # S3 / F1.2: emit structured event — token decode failure is
            # observable in the telemetry pipeline (failure_class, not silent).
            logging.getLogger("titan.api").info(
                json.dumps(
                    {
                        "flow": "api",
                        "action": "auth_token_decode_failed",
                        "failure_class": "TOKEN_DECODE_FAIL",
                        "severity": "WARNING",
                    },
                    default=str,
                )
            )
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
    # RBP-04: invalid or missing JWT keys stop the API here, at construction,
    # not later in the lifespan hook.
    validate_jwt_keys_at_startup()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN001
        from titan.observability.metrics import get_metrics
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
    # Outside CSRF and the routes, inside the security headers (so a 413 still
    # carries them); none of the outer layers reads the body.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=get_settings().API_MAX_BODY_SIZE_BYTES)
    app.add_middleware(SecurityHeadersMiddleware)

    rate_limiter = AuthenticatedRateLimiter()
    login_rate_limiter = LoginRateLimiter()
    refresh_rate_limiter = LoginRateLimiter(limit=5, window=60.0)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        return await rate_limiter(request, call_next)

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
            # /readyz is unauthenticated: name the error class only, keep the
            # message (paths, SQL) in the server log.
            _log.warning("readyz db check failed: %s: %s", type(e).__name__, e)
            checks["db_error"] = type(e).__name__
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
            # RBP-05: scripts never read the cookie; clients send the body copy.
            httponly=True,
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
            logging.getLogger("titan.api").info(json.dumps({
                "flow": "api", "action": "auth_login_failed",
                "failure_class": "ACCOUNT_LOCKED", "severity": "WARNING",
            }, default=str))
            # RBP-05: same answer as a wrong password, so the response does not
            # reveal that the account exists and is locked.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        user = store.verify_credentials(payload.username, payload.password)
        if user is None:
            store.record_failed_attempt(payload.username)
            logging.getLogger("titan.api").info(json.dumps({
                "flow": "api", "action": "auth_login_failed",
                "failure_class": "BAD_CREDENTIALS", "severity": "WARNING",
            }, default=str))
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
            logging.getLogger("titan.api").info(json.dumps({
                "flow": "api", "action": "auth_token_rejected",
                "failure_class": "REFRESH_TOKEN_INVALID", "severity": "WARNING",
            }, default=str))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

        if payload.jti is None or not store.is_refresh_token_active(payload.jti):
            logging.getLogger("titan.api").info(json.dumps({
                "flow": "api", "action": "auth_token_rejected",
                "failure_class": "REFRESH_TOKEN_REVOKED", "severity": "WARNING",
            }, default=str))
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
        current_user: AuthUser = Depends(_audited(AuditActionType.VIEW_DATA, "athlete_dashboard", coach_only=False)),
    ) -> dict[str, str]:
        if current_user.role != "COACH" and current_user.athlete_id != athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete isolation violation")
        return {"athlete_id": athlete_id, "viewer": current_user.id}

    @app.post("/coach/notes")
    def create_coach_note(_: dict[str, Any], __: AuthUser = Depends(require_coach)) -> dict[str, str]:
        return {"status": "created"}

    @app.post("/coach/overrides")
    def submit_coach_override(
        athlete_id: str,
        _: dict[str, Any],
        __: AuthUser = Depends(_audited(AuditActionType.SUBMIT_OVERRIDE, "coach_override")),
    ) -> dict[str, str]:
        return {"status": "override_submitted", "athlete_id": athlete_id}

    # GET /coach/export and DELETE /coach/athlete-data were stubs that reported an export or a
    # deletion that never happened. They are removed (ADR-0067 D2.5, D6.2; D-097): export and
    # deletion run on the routine machine with `python scripts/athletes.py export|remove`.

    # Mount Prometheus scrape endpoint — no auth; internal scrape only.
    # Bind to localhost in prod via compose network policy.
    app.mount("/metrics", _prom_asgi())

    return app


def _audited(action: AuditActionType, resource: str, *, coach_only: bool = True) -> Callable[..., AuthUser]:
    """Route dependency: authorize, then write the coach audit record before the handler runs.

    INV-22 (AGENTS §8.13, T-PRA-21): the record is durable (``coach_audit_log``)
    and ordered before the route's effect. If it cannot be written the request
    fails closed with 503 and the handler never runs.

    ``coach_only`` (the default) refuses every non-COACH user with 403 before
    the assignment check: ``require_coach_athlete_access`` lets non-coaches
    through for the route's own isolation check, which only routes that serve
    athletes too (``coach_only=False``) have.
    """

    def _dependency(
        request: Request,
        current_user: AuthUser = Depends(require_coach_athlete_access),
    ) -> AuthUser:
        if coach_only:
            require_coach(current_user)
        _audit_before_effect(request, current_user, action, resource)
        return current_user

    return _dependency


def _audit_before_effect(
    request: Request, current_user: AuthUser, action: AuditActionType, resource: str
) -> None:
    if current_user.role != "COACH":
        return
    athlete_id = _resolve_athlete_id(request)
    if athlete_id is None:
        return

    db = getattr(request.app.state, "db", None)
    try:
        if db is None:
            raise RuntimeError("no datastore attached for the coach audit log")
        db.log_coach_action(
            coach_id=current_user.id,
            action_type=action.value,
            target_athlete_id=athlete_id,
            resource=resource,
        )
    except Exception as exc:
        from titan.observability.metrics import get_metrics

        _log.critical(
            "audit_write_failed",
            extra={"action_type": action.value, "resource": resource, "error": str(exc)},
            exc_info=True,
        )
        get_metrics().counter("audit_write_failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit log unavailable: action not performed",
        ) from exc

    request.app.state.audit_store.log_action(CoachAuditRow(
        coach_id=current_user.id,
        athlete_id=athlete_id,
        action_type=action.value,
        resource=resource,
        action_detail=_build_action_detail(request, action),
        performed_at=datetime.now(UTC),
    ))


def _resolve_athlete_id(request: Request) -> str | None:
    path_params = request.path_params
    if "athlete_id" in path_params:
        value = path_params["athlete_id"]
        return value if isinstance(value, str) else None

    athlete_id = request.query_params.get("athlete_id")
    return athlete_id if athlete_id else None


def _build_action_detail(request: Request, action: AuditActionType) -> dict[str, Any] | None:
    query = dict(request.query_params)
    if action == AuditActionType.SUBMIT_OVERRIDE:
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
