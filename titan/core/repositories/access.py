"""Access domain SQL: login lockout, auth users and refresh tokens (HD-04 /
T5-70), coach-athlete RBAC scoping (ADR-0054), the coach audit log (T5-111) and
the external accounts of athletes other than the owner (ADR-0067 D9, D10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


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
        """Insert or replace an auth user record."""
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
        }

    def set_auth_token_revoked(self, jti: str) -> None:
        """Mark a refresh token as revoked."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "UPDATE auth_tokens SET revoked = 1 WHERE id = ?",
                (jti,),
            )
            self._db.conn.commit()

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
                "SELECT garmin_user_id, garmin_token_state, telegram_chat_id, updated_at "
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
        }

    def bind_garmin_account(self, athlete_id: str, garmin_user_id: str, *, updated_at: str) -> None:
        """Bind a Garmin account to the athlete; refuse one already bound elsewhere (ADR-0067 D9.4).

        A new or changed binding has no usable token yet ('missing') until a relogin.
        The check and the write run under one lock, and the UNIQUE column backs it.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            holder = cursor.execute(
                "SELECT athlete_id FROM athlete_accounts WHERE garmin_user_id = ?",
                (garmin_user_id,),
            ).fetchone()
            if holder is not None and holder[0] != athlete_id:
                raise ValueError("this Garmin account is already bound to another athlete")
            if holder is not None:
                return
            cursor.execute(
                """INSERT INTO athlete_accounts (athlete_id, garmin_user_id, garmin_token_state, updated_at)
                   VALUES (?, ?, 'missing', ?)
                   ON CONFLICT(athlete_id) DO UPDATE SET
                        garmin_user_id = excluded.garmin_user_id,
                        garmin_token_state = 'missing',
                        updated_at = excluded.updated_at""",
                (athlete_id, garmin_user_id, updated_at),
            )
            self._db.conn.commit()

    def set_garmin_token_state(self, athlete_id: str, state: str, *, updated_at: str) -> None:
        """Record the athlete's Garmin token state ('missing', 'ok' or 'expired')."""
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
