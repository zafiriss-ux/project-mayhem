"""Phase 8B FastAPI app with auth layer wired in."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status

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
)
from titan.api.dependencies import (
    get_auth_store,
    get_current_user,
    require_athlete_access,
    require_coach,
)
from titan.api.models import AuthUser, LoginRequest, LoginResponse


def create_app(auth_store: AuthStore | None = None) -> FastAPI:
    app = FastAPI(title="TITAN OS API", version="8B")
    app.state.auth_store = auth_store or AuthStore()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/login", response_model=LoginResponse)
    def login(payload: LoginRequest, response: Response, store: AuthStore = Depends(get_auth_store)) -> Any:
        user = store.verify_credentials(payload.username, payload.password)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

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
        current_user: AuthUser = Depends(get_current_user),
    ) -> dict[str, str]:
        require_athlete_access(current_user, athlete_id)
        return {"athlete_id": athlete_id, "viewer": current_user.id}

    @app.post("/coach/notes")
    def create_coach_note(_: dict[str, Any], __: AuthUser = Depends(require_coach)) -> dict[str, str]:
        return {"status": "created"}

    return app


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


app = create_app()
