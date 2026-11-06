"""Access domain SQL: login lockout, auth users and refresh tokens (HD-04 /
T5-70), coach-athlete RBAC scoping (ADR-0054), the coach audit log (T5-111) and
the external accounts of athletes other than the owner (ADR-0067 D9, D10), and the
pending-audit queue of consent withdrawals (ADR-0079)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:  # POSIX; the worker and the Docker image run on Linux
    import fcntl
except ImportError:  # pragma: no cover - Windows: one process only, see PendingAuditQueue
    fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


# Coach id of the seed assignment written by the migrations (system -> owner); never an API user.
SEED_COACH_ID = "system"


class OpenTransactionError(RuntimeError):
    """A write that must be its own BEGIN IMMEDIATE found a transaction already open (ADR-0083)."""


class AccessRepository:
    """Access SQL, on the owning DatabaseManager's connection and lock."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def record_failed_login(
        self,
        username: str,
        lockout_duration_seconds: float,
        max_attempts: int,
        *,
        window_seconds: float | None = None,
    ) -> bool:
        """Increment failed login count for username; lock account when threshold reached.

        With ``window_seconds``, a failure more than that long after the previous one starts
        the count again at 1, so old failures do not add up for ever (D-108, TK-06).
        Returns True if the account is now locked out.
        """
        import time
        now = time.time()
        # No window: every earlier failure counts, as before.
        stale_before = now - window_seconds if window_seconds is not None else float("-inf")
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute(
                """
                INSERT INTO login_lockout (username, failed_count, last_attempt_ts)
                VALUES (?, 1, ?)
                ON CONFLICT(username) DO UPDATE SET
                    failed_count = CASE
                        WHEN login_lockout.last_attempt_ts IS NOT NULL AND login_lockout.last_attempt_ts < ?
                        THEN 1 ELSE login_lockout.failed_count + 1 END,
                    last_attempt_ts = excluded.last_attempt_ts
                """,
                (username, now, stale_before),
            )
            c.execute(
                "SELECT failed_count FROM login_lockout WHERE username = ?",
                (username,),
            )
            row = c.fetchone()
            failed_count = row[0] if row else 1
            if failed_count >= max_attempts:
                c.execute(
                    "UPDATE login_lockout SET locked_until_ts = ? WHERE username = ?",
                    (now + lockout_duration_seconds, username),
                )
            self._db.conn.commit()
            return failed_count >= max_attempts

    def is_login_locked_out(self, username: str) -> bool:
        """Return True if the account has an active lockout that has not yet expired."""
        import time
        now = time.time()
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute(
                "SELECT locked_until_ts FROM login_lockout WHERE username = ?",
                (username,),
            )
            row = c.fetchone()
            if not row or row[0] is None:
                return False
            if now >= row[0]:
                c.execute(
                    "UPDATE login_lockout SET locked_until_ts = NULL, failed_count = 0 "
                    "WHERE username = ?",
                    (username,),
                )
                self._db.conn.commit()
                return False
            return True

    def clear_login_lockout(self, username: str) -> None:
        """Reset failed login count and lockout timestamp for username."""
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute(
                "UPDATE login_lockout SET failed_count = 0, locked_until_ts = NULL "
                "WHERE username = ?",
                (username,),
            )
            self._db.conn.commit()

    def upsert_auth_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role: str,
        athlete_id: str | None,
        is_active: bool = True,
    ) -> None:
        """Insert or replace an auth user record.

        SP-01: ``system`` is the coach id of the migration's ``('system', 'owner')`` seed row, so
        a user with that id would read the owner without a real assignment. It is refused.
        """
        if user_id == SEED_COACH_ID:
            raise ValueError(f"auth user id {SEED_COACH_ID!r} is reserved for the migration's seed row")
        with self._db._lock:
            self._db.conn.cursor().execute(
                "INSERT OR REPLACE INTO auth_users "
                "(id, username, password_hash, role, athlete_id, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, password_hash, role, athlete_id, int(is_active)),
            )
            self._db.conn.commit()

    def get_auth_user_by_id(self, user_id: str) -> dict | None:
        """Return the auth_users row for the given user_id, or None."""
        with self._db._lock:
            row = self._db.conn.cursor().execute(
                "SELECT id, username, password_hash, role, athlete_id, is_active "
                "FROM auth_users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "athlete_id": row[4],
            "is_active": bool(row[5]),
        }

    def get_auth_user_by_username(self, username: str) -> dict | None:
        """Return the auth_users row for the given username, or None."""
        with self._db._lock:
            row = self._db.conn.cursor().execute(
                "SELECT id, username, password_hash, role, athlete_id, is_active "
                "FROM auth_users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "athlete_id": row[4],
            "is_active": bool(row[5]),
        }

    def insert_auth_token(
        self, jti: str, user_id: str, issued_at: str, expires_at: str
    ) -> None:
        """Insert a new refresh token row (revoked=0 by default)."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "INSERT OR REPLACE INTO auth_tokens "
                "(id, user_id, issued_at, expires_at, revoked) VALUES (?, ?, ?, ?, 0)",
                (jti, user_id, issued_at, expires_at),
            )
            self._db.conn.commit()

    def get_auth_token(self, jti: str) -> dict | None:
        """Return the auth_tokens row for the given jti, or None."""
        with self._db._lock:
            row = self._db.conn.cursor().execute(
                "SELECT id, user_id, issued_at, expires_at, revoked "
                "FROM auth_tokens WHERE id = ?",
                (jti,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "user_id": row[1],
            "issued_at": row[2],
            "expires_at": row[3],
            "revoked": bool(row[4]),
            "used": row[4] == 2,
        }

    def set_auth_token_revoked(self, jti: str) -> None:
        """Mark an active refresh token as revoked.

        A token already used by a refresh keeps its mark (``revoked = 2``, #1503), so a logout
        with a stolen old token cannot hide a later reuse of it.
        """
        with self._db._lock:
            self._db.conn.cursor().execute(
                "UPDATE auth_tokens SET revoked = 1 WHERE id = ? AND revoked = 0",
                (jti,),
            )
            self._db.conn.commit()

    def rotate_auth_token(
        self,
        old_jti: str,
        user_id: str,
        new_token: tuple[str, str, str],
        now_iso: str,
        max_active: int,
    ) -> str:
        """Use refresh token *old_jti* of *user_id* once and store the next one, in one transaction.

        *new_token* is ``(jti, issued_at, expires_at)``. Returns ``"rotated"`` when the old token
        was active: it is marked as used (``revoked = 2``), the new one is stored and the user's
        oldest active tokens past *max_active* are revoked. Returns ``"reused"`` when the old
        token was already used by a refresh: a stolen token is being replayed (#1494, #1503), so
        every refresh token of the user is revoked. Returns ``"refused"`` for any other token
        (logged out, revoked, expired, unknown or another user's), which changes nothing.

        The checks and the writes are one ``BEGIN IMMEDIATE`` transaction, so two API processes
        cannot both use one token or leave the new token of the first use active after the
        second use revoked the rest (#1503). A failure rolls back and raises.
        """
        new_jti, issued_at, expires_at = new_token
        with self._db._lock, self._immediate_transaction() as cur:
            cur.execute(
                "UPDATE auth_tokens SET revoked = 2 "
                "WHERE id = ? AND user_id = ? AND revoked = 0 AND expires_at > ?",
                (old_jti, user_id, now_iso),
            )
            if cur.rowcount == 1:
                cur.execute(
                    "INSERT INTO auth_tokens (id, user_id, issued_at, expires_at, revoked) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (new_jti, user_id, issued_at, expires_at),
                )
                active = cur.execute(
                    "SELECT id FROM auth_tokens WHERE user_id = ? AND revoked = 0 AND expires_at > ? "
                    "ORDER BY issued_at, rowid",
                    (user_id, now_iso),
                ).fetchall()
                for (jti,) in active[: max(0, len(active) - max_active)]:
                    cur.execute("UPDATE auth_tokens SET revoked = 1 WHERE id = ?", (jti,))
                return "rotated"
            return "reused" if self._revoke_all_if_used(cur, old_jti, user_id) else "refused"

    def revoke_auth_tokens_if_used(self, jti: str, user_id: str) -> bool:
        """When *jti* of *user_id* was already used by a refresh, revoke every token of the user.

        A logout that presents a used token means someone else may hold its successor (#1503):
        the logout must end that chain too. True when the tokens were revoked. One
        ``BEGIN IMMEDIATE`` transaction; a failure rolls back and raises.
        """
        with self._db._lock, self._immediate_transaction() as cur:
            return self._revoke_all_if_used(cur, jti, user_id)

    @staticmethod
    def _revoke_all_if_used(cur, jti: str, user_id: str) -> bool:  # noqa: ANN001
        """In the caller's transaction: if *jti* of *user_id* is marked used, revoke all the user's tokens."""
        row = cur.execute(
            "SELECT revoked FROM auth_tokens WHERE id = ? AND user_id = ?",
            (jti, user_id),
        ).fetchone()
        if row is None or row[0] != 2:
            return False
        cur.execute("UPDATE auth_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (user_id,))
        return True

    def delete_expired_auth_tokens(self, before_iso: str) -> None:
        """Delete auth_tokens with expires_at < before_iso (housekeeping)."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "DELETE FROM auth_tokens WHERE expires_at < ?",
                (before_iso,),
            )
            self._db.conn.commit()

    def get_active_auth_tokens_for_user(self, user_id: str, now_iso: str) -> list[dict]:
        """Return active (non-revoked, non-expired) tokens for a user, by issued_at."""
        with self._db._lock:
            rows = self._db.conn.cursor().execute(
                "SELECT id, issued_at FROM auth_tokens "
                "WHERE user_id = ? AND revoked = 0 AND expires_at > ?",
                (user_id, now_iso),
            ).fetchall()
        return [{"id": r[0], "issued_at": r[1]} for r in rows]

    def get_athlete_account(self, athlete_id: str) -> dict | None:
        """Return the athlete's athlete_accounts row, or None (the owner never has one)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                "SELECT garmin_user_id, garmin_token_state, telegram_chat_id, updated_at, garmin_profile_id "
                "FROM athlete_accounts WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "garmin_user_id": row[0],
            "garmin_token_state": row[1],
            "telegram_chat_id": row[2],
            "updated_at": row[3],
            "garmin_profile_id": row[4],
        }

    @contextmanager
    def _immediate_transaction(self) -> Iterator[Any]:
        """One ``BEGIN IMMEDIATE`` transaction; the caller holds ``self._db._lock`` (ADR-0083).

        The thread lock alone is not enough: the API, the worker and the CLI are separate
        processes, and ``IMMEDIATE`` takes the database write lock before the first read.
        A transaction already open on the connection is refused, never joined or committed.
        Commit when the block ends, rollback on any error.
        """
        conn = self._db.conn
        if conn.in_transaction:
            raise OpenTransactionError("a transaction is already open on the database connection")
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    @staticmethod
    def _owner_garmin_identity(cursor) -> tuple[str | None, frozenset[int]]:  # noqa: ANN001
        """The owner's stored Garmin account name and every recorded profileId, in this transaction."""
        row = cursor.execute(
            "SELECT garmin_display_name FROM owner_garmin_identity WHERE athlete_id = 'owner'"
        ).fetchone()
        history = frozenset(
            r[0] for r in cursor.execute("SELECT garmin_profile_id FROM owner_garmin_profile_history")
        )
        return (row[0] if row else None), history

    def bind_garmin_account(
        self, athlete_id: str, garmin_user_id: str, garmin_profile_id: int, *, updated_at: str
    ) -> None:
        """Bind a Garmin account to the athlete; refuse the owner's or one bound elsewhere.

        ADR-0067 D9.4, ADR-0076 point 5 and ADR-0083 point 4. Refused while the owner's
        account name or profileId is not recorded (fail closed), when the name is the owner's
        or the profileId is in the owner's history, and when the name or the profileId is
        bound to another athlete. A binding of the same athlete writes both columns again.
        The row has no usable token ('missing') until the relogin writes one. The checks and
        the write are one ``BEGIN IMMEDIATE`` transaction; a database error is a refusal
        with a message that shows no value and no other athlete.
        """
        from titan.core.athlete import valid_garmin_profile_id

        profile_id = valid_garmin_profile_id(garmin_profile_id)
        if profile_id is None:
            raise ValueError("Garmin returned no valid profileId for this account; nothing was bound")
        with self._db._lock:
            self._db._ensure_open_locked()
            try:
                with self._immediate_transaction() as cursor:
                    owner_name, owner_history = self._owner_garmin_identity(cursor)
                    if owner_name is None or not owner_history:
                        raise ValueError(
                            "the owner's Garmin account is not recorded yet; run the owner's Garmin sync first"
                        )
                    if owner_name == garmin_user_id or profile_id in owner_history:
                        raise ValueError(
                            "this is the owner's Garmin account; an athlete binds their own account"
                        )
                    holders = {
                        row[0]
                        for row in cursor.execute(
                            "SELECT athlete_id FROM athlete_accounts "
                            "WHERE garmin_user_id = ? OR garmin_profile_id = ?",
                            (garmin_user_id, profile_id),
                        )
                    }
                    if holders - {athlete_id}:
                        raise ValueError("this Garmin account is already bound to another athlete")
                    cursor.execute(
                        """INSERT INTO athlete_accounts
                               (athlete_id, garmin_user_id, garmin_profile_id, garmin_token_state, updated_at)
                           VALUES (?, ?, ?, 'missing', ?)
                           ON CONFLICT(athlete_id) DO UPDATE SET
                                garmin_user_id = excluded.garmin_user_id,
                                garmin_profile_id = excluded.garmin_profile_id,
                                garmin_token_state = 'missing',
                                updated_at = excluded.updated_at""",
                        (athlete_id, garmin_user_id, profile_id, updated_at),
                    )
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                raise ValueError("the Garmin account could not be bound; nothing was changed") from exc

    def confirm_garmin_token_ok(
        self, athlete_id: str, garmin_user_id: str, garmin_profile_id: int, *, updated_at: str
    ) -> bool:
        """Set 'ok' after a relogin wrote the token, only if nothing changed since the binding.

        ADR-0083 point 4: one ``BEGIN IMMEDIATE`` transaction checks the owner's account again
        and sets 'ok' only on the row still in 'missing' and still bound to this account. An
        'expired' set in between (point 6) never becomes 'ok'. Returns False otherwise, and
        nothing is written.
        """
        from titan.core.athlete import valid_garmin_profile_id

        profile_id = valid_garmin_profile_id(garmin_profile_id)
        if profile_id is None:
            return False
        with self._db._lock:
            self._db._ensure_open_locked()
            with self._immediate_transaction() as cursor:
                owner_name, owner_history = self._owner_garmin_identity(cursor)
                if (
                    owner_name is None
                    or not owner_history
                    or owner_name == garmin_user_id
                    or profile_id in owner_history
                ):
                    return False
                cursor.execute(
                    "UPDATE athlete_accounts SET garmin_token_state = 'ok', updated_at = ? "
                    "WHERE athlete_id = ? AND garmin_token_state = 'missing' "
                    "AND garmin_user_id = ? AND garmin_profile_id = ?",
                    (updated_at, athlete_id, garmin_user_id, profile_id),
                )
                return cursor.rowcount == 1

    def get_owner_garmin_display_name(self) -> str | None:
        """The owner's Garmin account name (socialProfile displayName), or None (ADR-0076)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.execute(
                "SELECT garmin_display_name FROM owner_garmin_identity WHERE athlete_id = 'owner'"
            ).fetchone()
        return row[0] if row else None

    def get_owner_garmin_profile_ids(self) -> frozenset[int]:
        """Every Garmin profileId ever recorded for the owner (ADR-0083); empty when none."""
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.execute(
                "SELECT garmin_profile_id FROM owner_garmin_profile_history"
            ).fetchall()
        return frozenset(row[0] for row in rows)

    def record_owner_garmin_identity(
        self, display_name: str | None, profile_id: int | None, *, updated_at: str
    ) -> dict:
        """Store what the owner's connection read and stop athletes bound to the owner.

        ADR-0076 points 1, 3, 6 and ADR-0083 points 2 and 6, in one ``BEGIN IMMEDIATE``
        transaction. Each value is written on its own and only when given (the caller passes
        only valid values): the name replaces the old one; the profileId is added to the
        history, never replacing one, and its presence is checked before the commit. Then
        every athlete bound to the stored values (the whole history, and the stored name) gets
        'expired', even when nothing new was written. Not the owner, not rows already
        'expired'. Returns ``{"changed", "new_account", "expired_athletes"}``: the name
        changed; a profileId was added to a history that was not empty; who was stopped.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            with self._immediate_transaction() as cursor:
                previous_name, previous_history = self._owner_garmin_identity(cursor)
                if display_name is not None:
                    cursor.execute(
                        """INSERT INTO owner_garmin_identity (athlete_id, garmin_display_name, updated_at)
                           VALUES ('owner', ?, ?)
                           ON CONFLICT(athlete_id) DO UPDATE SET
                                garmin_display_name = excluded.garmin_display_name,
                                updated_at = excluded.updated_at""",
                        (display_name, updated_at),
                    )
                if profile_id is not None:
                    # Only the duplicate is ignored; any other violation stops the whole write.
                    cursor.execute(
                        "INSERT INTO owner_garmin_profile_history (garmin_profile_id, first_recorded_at) "
                        "VALUES (?, ?) ON CONFLICT(garmin_profile_id) DO NOTHING",
                        (profile_id, updated_at),
                    )
                    if cursor.execute(
                        "SELECT 1 FROM owner_garmin_profile_history WHERE garmin_profile_id = ?",
                        (profile_id,),
                    ).fetchone() is None:
                        raise RuntimeError("the owner's Garmin profileId was not recorded")
                stored_name, stored_history = self._owner_garmin_identity(cursor)
                bound: set[str] = set()
                if stored_history:
                    bound.update(
                        row[0]
                        for row in cursor.execute(
                            "SELECT athlete_id FROM athlete_accounts WHERE garmin_profile_id IN "
                            "(SELECT garmin_profile_id FROM owner_garmin_profile_history) "
                            "AND athlete_id != 'owner' AND garmin_token_state != 'expired'"
                        )
                    )
                if stored_name is not None:
                    bound.update(
                        row[0]
                        for row in cursor.execute(
                            "SELECT athlete_id FROM athlete_accounts WHERE garmin_user_id = ? "
                            "AND athlete_id != 'owner' AND garmin_token_state != 'expired'",
                            (stored_name,),
                        )
                    )
                expired = sorted(bound)
                for athlete_id in expired:
                    cursor.execute(
                        "UPDATE athlete_accounts SET garmin_token_state = 'expired', updated_at = ? "
                        "WHERE athlete_id = ?",
                        (updated_at, athlete_id),
                    )
        return {
            "changed": (
                display_name is not None and previous_name is not None and previous_name != display_name
            ),
            "new_account": (
                profile_id is not None and bool(previous_history) and profile_id not in previous_history
            ),
            "expired_athletes": expired,
        }

    def set_garmin_token_state(self, athlete_id: str, state: str, *, updated_at: str) -> None:
        """Record the athlete's Garmin token state ('missing' or 'expired'; 'ok' only via confirm)."""
        if state not in ("missing", "expired"):
            raise ValueError(f"not a Garmin token state this setter writes: {state!r}")
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "UPDATE athlete_accounts SET garmin_token_state = ?, updated_at = ? WHERE athlete_id = ?",
                (state, updated_at, athlete_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("the athlete has no Garmin account bound")
            self._db.conn.commit()

    def bind_telegram_chat(self, athlete_id: str, telegram_chat_id: str, *, updated_at: str) -> None:
        """Bind a private Telegram chat to the athlete; refuse one bound elsewhere (ADR-0067 D10.1).

        An athlete without a Garmin account yet gets a row with token state 'missing'.
        The check and the write run under one lock, and the UNIQUE column backs it.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            # Every stored id is compared in its canonical form (D-107), so a row written
            # before as "01001" or "+1001" still holds chat 1001, where it would be sent.
            from titan.core.athlete import canonical_chat_id

            holders = {
                row[0]: row[1]
                for row in cursor.execute(
                    "SELECT athlete_id, telegram_chat_id FROM athlete_accounts WHERE telegram_chat_id IS NOT NULL"
                ).fetchall()
                if canonical_chat_id(row[1], allow_negative=True) == telegram_chat_id
            }
            if any(holder != athlete_id for holder in holders):
                raise ValueError("this Telegram chat is already bound to another athlete")
            if holders.get(athlete_id) == telegram_chat_id:
                return
            cursor.execute(
                """INSERT INTO athlete_accounts (athlete_id, garmin_token_state, telegram_chat_id, updated_at)
                   VALUES (?, 'missing', ?, ?)
                   ON CONFLICT(athlete_id) DO UPDATE SET
                        telegram_chat_id = excluded.telegram_chat_id,
                        updated_at = excluded.updated_at""",
                (athlete_id, telegram_chat_id, updated_at),
            )
            self._db.conn.commit()

    def get_athlete_for_telegram_chat(self, telegram_chat_id: str) -> str | None:
        """Return the athlete bound to this Telegram chat, or None."""
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                "SELECT athlete_id FROM athlete_accounts WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            ).fetchone()
        return row[0] if row else None

    def get_consent_rows(self, athlete_id: str) -> list[dict]:
        """Return the athlete's consent_log rows, oldest first."""
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT text_version, granted_at, revoked_at FROM consent_log "
                "WHERE athlete_id = ? ORDER BY granted_at, id",
                (athlete_id,),
            ).fetchall()
        return [{"text_version": r[0], "granted_at": r[1], "revoked_at": r[2]} for r in rows]

    def grant_consent(
        self, athlete_id: str, *, consent_type: str, text_version: str, granted_at: str, channel: str
    ) -> None:
        """Insert one consent row (ADR-0067 D4.1); a new consent is always a new row."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "INSERT INTO consent_log (athlete_id, consent_type, text_version, granted_at, channel) "
                "VALUES (?, ?, ?, ?, ?)",
                (athlete_id, consent_type, text_version, granted_at, channel),
            )
            self._db.conn.commit()

    def revoke_consent(self, athlete_id: str, *, revoked_at: str) -> int:
        """Set revoked_at on the athlete's current consent rows (ADR-0067 D4.3); return the count."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ? AND revoked_at IS NULL",
                (revoked_at, athlete_id),
            )
            self._db.conn.commit()
            return cursor.rowcount

    def revoke_consent_with_audit(
        self, athlete_id: str, *, revoked_at: str, coach_id: str, action_type: str, resource: str
    ) -> int:
        """Revoke the athlete's current consent and write its audit row in ONE transaction (ADR-0079 §1).

        Either both rows are written or neither. Returns the consent rows revoked.
        """
        with self._db.transaction():
            cursor = self._db.conn.cursor()
            cursor.execute(
                "UPDATE consent_log SET revoked_at = ? WHERE athlete_id = ? AND revoked_at IS NULL",
                (revoked_at, athlete_id),
            )
            revoked = cursor.rowcount
            cursor.execute(
                """INSERT INTO coach_audit_log
                   (coach_id, athlete_id, action_type, resource, action_detail, performed_at)
                   VALUES (?, ?, ?, ?, '', datetime('now'))""",
                (coach_id, athlete_id, action_type, resource),
            )
        return revoked

    def apply_queued_withdrawal(self, entry: dict[str, Any], *, coach_id: str, resource: str) -> None:
        """Write one queued withdrawal to the database in ONE transaction (ADR-0079 §4).

        Nothing is written for an athlete who no longer exists. Revokes only the consents
        granted at or before the queued time (a later /agree is a new consent), and writes the audit row with the original time unless a row with the
        same queue id is already there, so a repeated drain never writes it twice.
        """
        revoked_at = datetime.fromisoformat(entry["revoked_at"])
        marker = f"queue_id:{entry['id']}"
        with self._db.transaction():
            cursor = self._db.conn.cursor()
            # An athlete erased since the /stop gets nothing written back (ADR-0079 §3).
            if cursor.execute("SELECT 1 FROM athletes WHERE athlete_id = ?", (entry["athlete_id"],)).fetchone() is None:
                return
            rows = cursor.execute(
                "SELECT id, granted_at FROM consent_log WHERE athlete_id = ? AND revoked_at IS NULL",
                (entry["athlete_id"],),
            ).fetchall()
            for row_id, granted_at in rows:
                if _granted_no_later_than(granted_at, revoked_at):
                    cursor.execute(
                        "UPDATE consent_log SET revoked_at = ? WHERE id = ?", (entry["revoked_at"], row_id)
                    )
            already = cursor.execute(
                "SELECT 1 FROM coach_audit_log WHERE athlete_id = ? AND instr(action_detail, ?) = 1",
                (entry["athlete_id"], marker),
            ).fetchone()
            if already is None:
                cursor.execute(
                    """INSERT INTO coach_audit_log
                       (coach_id, athlete_id, action_type, resource, action_detail, performed_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        coach_id, entry["athlete_id"], entry["action"], resource,
                        f"{marker} written late from the pending-audit queue (ADR-0079)",
                        revoked_at.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

    def _get_all_athlete_ids(self) -> list[str]:
        """Return all athlete_ids from the athletes table."""
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT athlete_id FROM athletes"
            ).fetchall()
        return [r[0] for r in rows]

    def list_athletes_in_order(self) -> list[str]:
        """Every athlete in the worker's fixed order: the owner first, then by registration (ADR-0067 D8.1)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT athlete_id FROM athletes ORDER BY athlete_id != 'owner', created_at, athlete_id"
            ).fetchall()
        return [r[0] for r in rows]

    def get_assigned_athletes(self, coach_id: str) -> list[str]:
        """Return athlete_ids the coach is permitted to access: its assignment rows, nothing else.

        No coach id is special (M0-05, INV-11). ``system`` gets the ``system → owner`` row the
        migration seeds, like any coach gets the rows assigned to it.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT athlete_id FROM coach_athlete_assignments WHERE coach_id = ?",
                (coach_id,),
            ).fetchall()
        return [r[0] for r in rows]

    def assign_athlete_to_coach(self, coach_id: str, athlete_id: str) -> None:
        """Grant coach_id access to athlete_id (idempotent via INSERT OR IGNORE)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "INSERT OR IGNORE INTO coach_athlete_assignments "
                "(coach_id, athlete_id, assigned_at) VALUES (?, ?, datetime('now'))",
                (coach_id, athlete_id),
            )
            self._db.conn.commit()

    def log_coach_action(
        self,
        coach_id: str,
        action_type: str,
        target_athlete_id: str,
        action_detail: str = "",
        resource: str = "",
    ) -> None:
        """Persist coach action to coach_audit_log. Survives process restart (T5-111)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                """INSERT INTO coach_audit_log
                   (coach_id, athlete_id, action_type, resource, action_detail,
                    performed_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (coach_id, target_athlete_id, action_type, resource, action_detail),
            )
            self._db.conn.commit()

    def get_coach_audit_log(
        self,
        coach_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve audit log entries ordered newest-first."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            if coach_id:
                cursor.execute(
                    """SELECT * FROM coach_audit_log
                       WHERE coach_id = ?
                       ORDER BY performed_at DESC
                       LIMIT ?""",
                    (coach_id, limit),
                )
            else:
                cursor.execute(
                    """SELECT * FROM coach_audit_log
                       ORDER BY performed_at DESC
                       LIMIT ?""",
                    (limit,),
                )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=True)) for row in rows]


def _granted_no_later_than(granted_at: str, revoked_at: datetime) -> bool:
    """True when a consent was given at or before the queued withdrawal (ADR-0079 §4).

    A time without a zone is read as UTC. A time that cannot be read counts as earlier, so
    the consent is revoked: an unreadable row never keeps a consent the athlete withdrew.
    """
    from datetime import UTC

    try:
        granted = datetime.fromisoformat(granted_at)
    except (TypeError, ValueError):
        return True
    if granted.tzinfo is None:
        granted = granted.replace(tzinfo=UTC)
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=UTC)
    return granted <= revoked_at


class PendingAuditUnreadable(Exception):
    """A complete line of the pending-audit queue cannot be read (ADR-0079 §3).

    Callers treat it as "no consent" for every athlete but the owner.
    """


class PendingAuditQueue:
    """The pending-audit queue of consent withdrawals (ADR-0079 §2–§4).

    One JSON object per line in ``pending_audit.jsonl`` beside the database: a withdrawal
    ``{"id", "athlete_id", "revoked_at", "action"}`` or a drained marker ``{"id", "done": true}``.
    It holds no chat id, token or health data.

    Every access takes ``flock`` on the separate ``pending_audit.lock`` (never renamed), so an
    append never lands in a file that compaction replaced. Appends, drains, compaction and
    removals take it exclusively; reads and the /agree path take it shared. The queue lock is
    always taken before ``DatabaseManager._lock``. Without ``fcntl`` (Windows) only a lock
    inside this process is taken.
    """

    FILE_NAME = "pending_audit.jsonl"
    LOCK_NAME = "pending_audit.lock"
    _thread_lock = threading.RLock()

    def __init__(self, directory: Path) -> None:
        self.path = directory / self.FILE_NAME
        self.lock_path = directory / self.LOCK_NAME
        self._log = logging.getLogger("titan.core.pending_audit")

    @contextmanager
    def locked(self, *, exclusive: bool) -> Iterator[None]:
        """Hold the queue lock (exclusive or shared) for the block."""
        if fcntl is None:  # pragma: no cover - Windows
            with self._thread_lock:
                yield
            return
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    # --- reads ------------------------------------------------------------------------

    def read_locked(self) -> list[dict[str, Any]]:
        """The withdrawals not yet drained. The caller holds the lock.

        A missing file is an empty queue. An unterminated last line is ignored and logged:
        its append never finished, so its /stop was never confirmed. A complete line that
        cannot be read raises PendingAuditUnreadable; an OSError propagates.
        """
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return []
        lines = data.split(b"\n")
        if lines[-1]:
            self._log.warning("pending_audit_torn_tail_ignored", extra={"bytes": len(lines[-1])})
        pending: dict[str, dict[str, Any]] = {}
        done: set[str] = set()
        for raw in lines[:-1]:
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
            except ValueError as exc:
                raise PendingAuditUnreadable("a line of the pending-audit queue is not JSON") from exc
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise PendingAuditUnreadable("a line of the pending-audit queue has no id")
            if item.get("done") is True:
                done.add(item["id"])
                continue
            if not all(isinstance(item.get(k), str) and item.get(k) for k in ("athlete_id", "revoked_at", "action")):
                raise PendingAuditUnreadable("a withdrawal in the pending-audit queue is incomplete")
            try:
                datetime.fromisoformat(item["revoked_at"])
            except ValueError as exc:
                raise PendingAuditUnreadable("a withdrawal in the pending-audit queue has a bad time") from exc
            pending[item["id"]] = item
        return [item for key, item in pending.items() if key not in done]

    def pending(self) -> list[dict[str, Any]]:
        """The withdrawals not yet drained, under a shared lock."""
        with self.locked(exclusive=False):
            return self.read_locked()

    def pending_athletes(self) -> set[str]:
        """Athletes with a withdrawal not yet drained, under a shared lock."""
        return {item["athlete_id"] for item in self.pending()}

    # --- writes (the caller holds the exclusive lock) -------------------------------------

    def append_locked(self, item: dict[str, Any]) -> None:
        """Append one line durably (O_APPEND, one write, fsync). The caller holds the exclusive lock.

        A torn tail left by an earlier crash is cut off first, so the new line starts on
        its own line and a complete line is never corrupted (ADR-0079 §4).
        """
        created = not self.path.exists()
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                data = os.pread(fd, size, 0)
                keep = data.rfind(b"\n") + 1
                os.ftruncate(fd, keep)
                os.fsync(fd)
                self._log.warning("pending_audit_torn_tail_dropped", extra={"bytes": size - keep})
            line = (json.dumps(item, sort_keys=True) + "\n").encode("utf-8")
            if os.write(fd, line) != len(line):
                raise OSError("short write to the pending-audit queue")
            os.fsync(fd)
        finally:
            os.close(fd)
        if created:
            self._fsync_dir()

    def append(self, item: dict[str, Any]) -> bool:
        """Append a withdrawal under the exclusive lock; True when the queue was empty before.

        An item without ``revoked_at`` is stamped here, under the lock, so no /agree that
        committed before this append can carry a later time than the withdrawal.
        """
        with self.locked(exclusive=True):
            try:
                was_empty = not self.read_locked()
            except (PendingAuditUnreadable, OSError):
                was_empty = False
            if "revoked_at" not in item:
                from datetime import UTC

                item["revoked_at"] = datetime.now(UTC).isoformat()
            self.append_locked(item)
        return was_empty

    def rewrite_locked(self, keep: list[dict[str, Any]]) -> None:
        """Replace the file with ``keep`` only: temp file, fsync, rename, fsync of the folder.

        The caller holds the exclusive lock and has read the file without error, so no
        unreadable line is ever dropped here (ADR-0079 §4).
        """
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            for item in keep:
                os.write(fd, (json.dumps(item, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.path)
        self._fsync_dir()

    def remove_athlete(self, athlete_id: str) -> int:
        """Drop an erased athlete's withdrawals, under the exclusive lock (ADR-0079 §3)."""
        with self.locked(exclusive=True):
            items = self.read_locked()
            keep = [item for item in items if item["athlete_id"] != athlete_id]
            if len(keep) != len(items):
                self.rewrite_locked(keep)
        return len(items) - len(keep)

    def _fsync_dir(self) -> None:
        if not hasattr(os, "O_DIRECTORY"):  # pragma: no cover - Windows
            return
        fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
