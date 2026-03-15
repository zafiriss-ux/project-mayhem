"""Authentication models for TITAN OS API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Role = Literal["COACH", "ATHLETE"]


class AuthUser(BaseModel):
    """Authenticated principal payload."""

    id: str
    username: str
    role: Role
    athlete_id: str | None
    is_active: bool = True


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str
    role: Role
    athlete_id: str | None = None
    exp: int
    token_type: Literal["access", "refresh"]
    jti: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
