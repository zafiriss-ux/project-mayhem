"""JWT authentication utilities for Phase 8B API."""

from __future__ import annotations

import functools
import uuid
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, NamedTuple

import bcrypt
import jwt
from jwt import InvalidTokenError

from titan.api.models import AuthUser, TokenPayload
from titan.config.settings import get_settings

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
MAX_ACTIVE_REFRESH_TOKENS = 3
ACCESS_COOKIE_NAME = "titan_access_token"
REFRESH_COOKIE_NAME = "titan_refresh_token"

LOCKOUT_MAX_ATTEMPTS: int = 5
LOCKOUT_WINDOW_SECONDS: float = 300.0
LOCKOUT_DURATION_SECONDS: float = 900.0

JWT_ISSUER = "titan-os"
JWT_AUDIENCE = "titan-api"


class RefreshRotation(NamedTuple):
    """Result of one refresh: the next token, or None and whether the old one was a replay."""

    token: tuple[str, str, datetime] | None
    reused: bool


class AuthError(Exception):
    """Raised when auth verification or lifecycle operations fail."""


class AuthStore:
    """SQLite-backed auth persistence for users and refresh tokens (HD-04 / T5-70).

    Accepts an optional ``DatabaseManager``. When none is provided, an in-memory
    SQLite database is created — existing tests that call ``AuthStore()`` continue
    to work without modification.
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        if db is None:
            from titan.core.database import DatabaseManager
            db = DatabaseManager(db_name=":memory:")
        self._db = db
        self._lock: Lock = Lock()

    def upsert_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role: str,
        athlete_id: str | None,
        is_active: bool = True,
    ) -> None:
        self._db.upsert_auth_user(user_id, username, password_hash, role, athlete_id, is_active)

    def verify_credentials(self, username: str, plain_password: str) -> AuthUser | None:
        row = self._db.get_auth_user_by_username(username)
        if row is None:
            # SP-07: run bcrypt anyway, so an unknown username answers as slowly as a wrong
            # password and the timing does not tell which usernames exist (RBP-05).
            verify_password(plain_password, _dummy_password_hash())
            return None
        if not verify_password(plain_password, row["password_hash"]):
            return None
        if not row["is_active"]:
            # SP-02: a disabled account gets the wrong-password answer, no token (RBP-05).
            return None
        return AuthUser(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            athlete_id=row["athlete_id"],
            is_active=row["is_active"],
        )

    def record_failed_attempt(self, username: str) -> None:
        # Per username, as decided (D-006); only failures within the window add up (D-108).
        # An unknown username is counted the same way, so both take the same path (RBP-05).
        self._db.record_failed_login(
            username, LOCKOUT_DURATION_SECONDS, LOCKOUT_MAX_ATTEMPTS, window_seconds=LOCKOUT_WINDOW_SECONDS
        )

    def is_locked_out(self, username: str) -> bool:
        return self._db.is_login_locked_out(username)

    def clear_failed_attempts(self, username: str) -> None:
        self._db.clear_login_lockout(username)

    def get_user(self, user_id: str) -> AuthUser | None:
        row = self._db.get_auth_user_by_id(user_id)
        if row is None:
            return None
        return AuthUser(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            athlete_id=row["athlete_id"],
            is_active=row["is_active"],
        )

    def add_refresh_token(self, jti: str, user_id: str, expires_at: datetime, issued_at: datetime) -> None:
        self._db.insert_auth_token(jti, user_id, issued_at.isoformat(), expires_at.isoformat())
        self._trim_active_refresh_tokens(user_id)

    def revoke_refresh_token(self, jti: str) -> None:
        self._db.set_auth_token_revoked(jti)

    def rotate_refresh_token(self, jti: str, user: AuthUser) -> RefreshRotation:
        """Use refresh token *jti* once and issue the next one.

        The use, the new token and the trim of the oldest active tokens are one database
        transaction (#1503), so this holds across API processes too. A token already used by
        a refresh may be stolen (#1494, #1503): every refresh token of the user is revoked,
        also when the second use comes much later, and ``reused`` is True. A token that was
        logged out, revoked, expired or is unknown is refused and changes nothing. A failure
        raises; the caller answers 401.
        """
        issued_at = _utc_now()
        token, new_jti, expires_at = _encode_refresh_token(user, issued_at)
        with self._lock:
            outcome = self._db.rotate_auth_token(
                jti,
                user.id,
                (new_jti, issued_at.isoformat(), expires_at.isoformat()),
                issued_at.isoformat(),
                MAX_ACTIVE_REFRESH_TOKENS,
            )
        if outcome == "rotated":
            return RefreshRotation(token=(token, new_jti, expires_at), reused=False)
        return RefreshRotation(token=None, reused=outcome == "reused")

    def is_refresh_token_active(self, jti: str) -> bool:
        row = self._db.get_auth_token(jti)
        if row is None or row["revoked"]:
            return False
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
        except (ValueError, TypeError):
            return False
        return expires_at > _utc_now()

    def revoke_all_if_used(self, jti: str, user_id: str) -> bool:
        """Revoke every refresh token of *user_id* when *jti* was already used (#1503)."""
        with self._lock:
            return self._db.revoke_auth_tokens_if_used(jti, user_id)

    def was_refresh_token_used(self, jti: str) -> bool:
        """True when a refresh already used *jti*: one more use is a replay (#1503)."""
        row = self._db.get_auth_token(jti)
        return row is not None and bool(row.get("used"))

    def cleanup_expired(self) -> None:
        """Remove tokens past their expiry time (housekeeping)."""
        self._db.delete_expired_auth_tokens(_utc_now().isoformat())

    def _trim_active_refresh_tokens(self, user_id: str) -> None:
        """Revoke oldest active tokens when user exceeds MAX_ACTIVE_REFRESH_TOKENS."""
        now_iso = _utc_now().isoformat()
        active = self._db.get_active_auth_tokens_for_user(user_id, now_iso)
        if len(active) <= MAX_ACTIVE_REFRESH_TOKENS:
            return
        # Sort by issued_at ascending (oldest first) and revoke the excess
        try:
            active_sorted = sorted(active, key=lambda r: r["issued_at"])
        except (KeyError, TypeError):
            return
        for row in active_sorted[: len(active) - MAX_ACTIVE_REFRESH_TOKENS]:
            self.revoke_refresh_token(row["id"])


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _pem_from_env(value: str) -> str:
    # scripts/generate_jwt_keys.sh writes each PEM on one .env line with literal
    # "\n", and Docker's env_file passes them through unescaped.
    return value.replace("\\n", "\n")


def _jwt_private_key() -> str:
    key = get_settings().TITAN_JWT_PRIVATE_KEY.get_secret_value() if get_settings().TITAN_JWT_PRIVATE_KEY else None
    if not key:
        raise AuthError("TITAN_JWT_PRIVATE_KEY is not configured")
    return _pem_from_env(key)


def _jwt_public_key() -> str:
    key = get_settings().TITAN_JWT_PUBLIC_KEY or None
    if not key:
        raise AuthError("TITAN_JWT_PUBLIC_KEY is not configured")
    return _pem_from_env(key)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


_BCRYPT_MAX_BYTES = 72


def verify_password(plain_password: str, password_hash: str) -> bool:
    candidate = plain_password.encode("utf-8")
    if len(candidate) > _BCRYPT_MAX_BYTES:
        # bcrypt 5 raises on more than 72 bytes, and hash_password could never have stored
        # such a password: deny, after the same bcrypt work, instead of a 500 (SP-07).
        bcrypt.checkpw(candidate[:_BCRYPT_MAX_BYTES], password_hash.encode("utf-8"))
        return False
    return bcrypt.checkpw(candidate, password_hash.encode("utf-8"))


@functools.cache
def _dummy_password_hash() -> str:
    """A hash of nothing anyone knows, at the cost hash_password uses (SP-07).

    Made once, on the first unknown username, so the API start does not pay for it.
    """
    return hash_password(uuid.uuid4().hex)


def create_access_token(user: AuthUser, now: datetime | None = None) -> tuple[str, datetime]:
    issued_at = now or _utc_now()
    expires_at = issued_at + ACCESS_TOKEN_TTL
    payload = {
        "sub": user.id,
        "role": user.role,
        "athlete_id": user.athlete_id,
        "exp": expires_at,
        # Bandit B105: JWT claim value, not a secret.
        "token_type": "access",  # nosec B105
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, _jwt_private_key(), algorithm="RS256"), expires_at


def create_refresh_token(
    user: AuthUser,
    store: AuthStore,
    now: datetime | None = None,
) -> tuple[str, str, datetime]:
    issued_at = now or _utc_now()
    token, jti, expires_at = _encode_refresh_token(user, issued_at)
    store.add_refresh_token(jti, user.id, expires_at, issued_at)
    return token, jti, expires_at


def _encode_refresh_token(user: AuthUser, issued_at: datetime) -> tuple[str, str, datetime]:
    """A signed refresh token for *user* with a new jti; the caller stores it."""
    expires_at = issued_at + REFRESH_TOKEN_TTL
    jti = str(uuid.uuid4())
    payload = {
        "sub": user.id,
        "role": user.role,
        "athlete_id": user.athlete_id,
        "exp": expires_at,
        # Bandit B105: JWT claim value, not a secret.
        "token_type": "refresh",  # nosec B105
        "jti": jti,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, _jwt_private_key(), algorithm="RS256"), jti, expires_at


def decode_token(token: str, expected_type: str) -> TokenPayload:
    try:
        decoded = jwt.decode(
            token,
            _jwt_public_key(),
            algorithms=["RS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"verify_aud": True},
        )
    except InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc
    payload = TokenPayload(**decoded)
    if payload.token_type != expected_type:
        raise AuthError("Invalid token type")
    return payload


def validate_jwt_keys_at_startup() -> None:
    """Fail fast if JWT keys are missing, malformed or not one key pair (RBP-04).

    ``create_app()`` calls this while building the app, so a bad key stops the
    API at construction instead of at the first login. A probe token is signed
    with the private key and verified with the public key.
    Raises AuthError with descriptive message.
    """
    try:
        private_key = _jwt_private_key()
    except AuthError as exc:
        raise AuthError(
            "TITAN_JWT_PRIVATE_KEY missing or invalid. "
            "Set env var before starting API."
        ) from exc
    try:
        public_key = _jwt_public_key()
    except AuthError as exc:
        raise AuthError(
            "TITAN_JWT_PUBLIC_KEY missing or invalid. "
            "Set env var before starting API."
        ) from exc
    try:
        probe = jwt.encode(
            {"sub": "startup-key-check", "aud": JWT_AUDIENCE, "iss": JWT_ISSUER},
            private_key,
            algorithm="RS256",
        )
        jwt.decode(probe, public_key, algorithms=["RS256"], audience=JWT_AUDIENCE, issuer=JWT_ISSUER)
    except Exception as exc:
        raise AuthError(
            "TITAN_JWT_PRIVATE_KEY and TITAN_JWT_PUBLIC_KEY are not a valid RS256 key pair. "
            "Regenerate them with scripts/generate_jwt_keys.sh."
        ) from exc
