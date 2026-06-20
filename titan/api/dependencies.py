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


def require_athlete_access(
    current_user: AuthUser,
    requested_athlete_id: str,
    request: Request | None = None,
) -> None:
    if current_user.role == "COACH":
        # Verify coach is assigned to the requested athlete (TD-01 / ADR-0054)
        athlete_id = requested_athlete_id
        if athlete_id and athlete_id != "owner":
            db = getattr(request.app.state, "db", None) if request is not None else None
            if db is not None:
                allowed = db.get_assigned_athletes(current_user.id)
                if athlete_id not in allowed:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Coach not assigned to athlete {athlete_id}",
                    )
        return
    if current_user.athlete_id != requested_athlete_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete isolation violation")


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
    athlete_id = _get_athlete_id_from_request(request)
    # INV-11: owner is assignment-scoped like any athlete (no role-only bypass).
    # A path with no athlete_id at all remains permissive (not an athlete-scoped route).
    if not athlete_id:
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
