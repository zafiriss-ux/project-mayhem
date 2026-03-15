"""JWT authentication utilities for Phase 8B API."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt import InvalidTokenError

from titan.api.models import AuthUser, TokenPayload

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
MAX_ACTIVE_REFRESH_TOKENS = 3
ACCESS_COOKIE_NAME = "titan_access_token"
REFRESH_COOKIE_NAME = "titan_refresh_token"


class AuthError(Exception):
    """Raised when auth verification or lifecycle operations fail."""


class AuthStore:
    """In-memory auth persistence for users and refresh tokens."""

    def __init__(self) -> None:
        self._users: dict[str, dict[str, str | bool | None]] = {}
        self._tokens: dict[str, dict[str, str | datetime | bool]] = {}

    def upsert_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role: str,
        athlete_id: str | None,
        is_active: bool = True,
    ) -> None:
        self._users[user_id] = {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "athlete_id": athlete_id,
            "is_active": is_active,
        }

    def verify_credentials(self, username: str, plain_password: str) -> AuthUser | None:
        for row in self._users.values():
            if row["username"] != username:
                continue
            if not verify_password(plain_password, str(row["password_hash"])):
                return None
            return AuthUser(
                id=str(row["id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                athlete_id=row["athlete_id"] if isinstance(row["athlete_id"], str) else None,
                is_active=bool(row["is_active"]),
            )
        return None

    def get_user(self, user_id: str) -> AuthUser | None:
        row = self._users.get(user_id)
        if row is None:
            return None
        return AuthUser(
            id=str(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            athlete_id=row["athlete_id"] if isinstance(row["athlete_id"], str) else None,
            is_active=bool(row["is_active"]),
        )

    def add_refresh_token(self, jti: str, user_id: str, expires_at: datetime, issued_at: datetime) -> None:
        self._tokens[jti] = {
            "id": jti,
            "user_id": user_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "revoked": False,
        }
        self._trim_active_refresh_tokens(user_id)

    def revoke_refresh_token(self, jti: str) -> None:
        token = self._tokens.get(jti)
        if token is not None:
            token["revoked"] = True

    def is_refresh_token_active(self, jti: str) -> bool:
        token = self._tokens.get(jti)
        if token is None or bool(token["revoked"]):
            return False
        expires_at = token["expires_at"]
        return isinstance(expires_at, datetime) and expires_at > _utc_now()

    def _trim_active_refresh_tokens(self, user_id: str) -> None:
        active = []
        now = _utc_now()
        for jti, row in self._tokens.items():
            if row["user_id"] != user_id or bool(row["revoked"]):
                continue
            expires_at = row["expires_at"]
            issued_at = row["issued_at"]
            if isinstance(expires_at, datetime) and expires_at > now and isinstance(issued_at, datetime):
                active.append((issued_at, jti))
        if len(active) <= MAX_ACTIVE_REFRESH_TOKENS:
            return
        active.sort(key=lambda item: item[0])
        for _, jti in active[: len(active) - MAX_ACTIVE_REFRESH_TOKENS]:
            self.revoke_refresh_token(jti)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _jwt_private_key() -> str:
    key = os.getenv("TITAN_JWT_PRIVATE_KEY")
    if not key:
        raise AuthError("TITAN_JWT_PRIVATE_KEY is not configured")
    return key


def _jwt_public_key() -> str:
    key = os.getenv("TITAN_JWT_PUBLIC_KEY")
    if not key:
        raise AuthError("TITAN_JWT_PUBLIC_KEY is not configured")
    return key


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user: AuthUser, now: datetime | None = None) -> tuple[str, datetime]:
    issued_at = now or _utc_now()
    expires_at = issued_at + ACCESS_TOKEN_TTL
    payload = {
        "sub": user.id,
        "role": user.role,
        "athlete_id": user.athlete_id,
        "exp": expires_at,
        "token_type": "access",
    }
    return jwt.encode(payload, _jwt_private_key(), algorithm="RS256"), expires_at


def create_refresh_token(
    user: AuthUser,
    store: AuthStore,
    now: datetime | None = None,
) -> tuple[str, str, datetime]:
    issued_at = now or _utc_now()
    expires_at = issued_at + REFRESH_TOKEN_TTL
    jti = str(uuid.uuid4())
    payload = {
        "sub": user.id,
        "role": user.role,
        "athlete_id": user.athlete_id,
        "exp": expires_at,
        "token_type": "refresh",
        "jti": jti,
    }
    store.add_refresh_token(jti, user.id, expires_at, issued_at)
    return jwt.encode(payload, _jwt_private_key(), algorithm="RS256"), jti, expires_at


def decode_token(token: str, expected_type: str) -> TokenPayload:
    try:
        decoded = jwt.decode(token, _jwt_public_key(), algorithms=["RS256"])
    except InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc
    payload = TokenPayload(**decoded)
    if payload.token_type != expected_type:
        raise AuthError("Invalid token type")
    return payload
