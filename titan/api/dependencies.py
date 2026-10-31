"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from titan.api.auth import ACCESS_COOKIE_NAME, AuthError, AuthStore, decode_token
from titan.api.models import AuthUser

# Coach id of the migrations' ('system', 'owner') seed row (titan/core/repositories/access.py
# SEED_COACH_ID). No API coach may use it, even if a row was written by hand (SP-01).
_SEED_COACH_ID = "system"


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


def _get_athlete_id_from_request(request: Request) -> str | None:
    """Extract athlete_id from path params or query string."""
    athlete_id = request.path_params.get("athlete_id")
    if not athlete_id:
        athlete_id = request.query_params.get("athlete_id")
    return athlete_id


def require_coach(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if current_user.role != "COACH":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Coach role required")
    return current_user


def require_coach_athlete_access(
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    """Dependency for athlete-scoped endpoints: verifies COACH assignment.

    Use on routes with an ``athlete_id`` path or query parameter.
    Global endpoints (/health, /auth/*) must NOT use this dependency.
    """
    if current_user.role != "COACH":
        return current_user
    if current_user.id == _SEED_COACH_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coach id is reserved for the seed assignment — access denied",
        )
    athlete_id = _get_athlete_id_from_request(request)
    # INV-11: owner is assignment-scoped like any athlete (no role-only bypass).
    # A request with no athlete_id at all remains permissive (not an athlete-scoped route).
    # One that names athlete_id with an empty value is refused (MA-F6): blank is no bypass.
    if not athlete_id:
        if "athlete_id" in request.path_params or "athlete_id" in request.query_params:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Coach request names an empty athlete_id — access denied",
            )
        return current_user
    db = getattr(request.app.state, "db", None)
    if db is None:
        # Cannot verify assignment without the DB → deny (INV-11 fail-closed).
        # An unverifiable coach-to-athlete assignment must never default-allow.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coach assignment cannot be verified (datastore unavailable) — access denied",
        )
    allowed = db.get_assigned_athletes(current_user.id)
    if athlete_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Coach not assigned to athlete {athlete_id}",
        )
    return current_user
