"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from titan.api.auth import ACCESS_COOKIE_NAME, AuthError, AuthStore, decode_token
from titan.api.models import AuthUser


def get_auth_store(request: Request) -> AuthStore:
    return request.app.state.auth_store  # type: ignore[no-any-return]


def get_current_user(
    request: Request,
    store: AuthStore = Depends(get_auth_store),
) -> AuthUser:
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(token, expected_type="access")
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = store.get_user(payload.sub)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    request.state.current_user = user
    return user


def require_coach(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if current_user.role != "COACH":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Coach role required")
    return current_user


def require_athlete_access(current_user: AuthUser, requested_athlete_id: str) -> None:
    if current_user.role == "COACH":
        return
    if current_user.athlete_id != requested_athlete_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete isolation violation")
