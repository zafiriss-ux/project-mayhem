"""Synthetic Garmin accounts for tests (ADR-0076, ADR-0083).

A Garmin account is its socialProfile ``displayName`` and its stable ``profileId``. Every
value here is made up: no real account name or id.
"""

from __future__ import annotations

import zlib

OWNER_GARMIN_NAME = "owner-garmin-name"
OWNER_GARMIN_PROFILE_ID = 900_000_001


def profile_id_for(account: str) -> int:
    """A stable synthetic profileId for a synthetic account name; never the owner's."""
    value = 1_000_000 + zlib.crc32(account.encode())
    assert value != OWNER_GARMIN_PROFILE_ID
    return value


def record_owner(db, name: str = OWNER_GARMIN_NAME, profile_id: int = OWNER_GARMIN_PROFILE_ID) -> dict:  # noqa: ANN001
    """What one sync of the owner records: the account name and the profileId."""
    return db.record_owner_garmin_identity(name, profile_id)


def bind(db, athlete_id: str, account: str) -> None:  # noqa: ANN001
    """Bind the synthetic account to the athlete, with its synthetic profileId."""
    db.bind_garmin_account(athlete_id, account, profile_id_for(account))


def set_token_ok(db, athlete_id: str) -> None:  # noqa: ANN001
    """Test setup only: a ready athlete, as after a confirmed relogin. Production sets 'ok'
    only through ``confirm_garmin_token_ok`` (ADR-0083 point 4)."""
    cursor = db.conn.execute(
        "UPDATE athlete_accounts SET garmin_token_state = 'ok' WHERE athlete_id = ?", (athlete_id,)
    )
    assert cursor.rowcount == 1
    db.conn.commit()
