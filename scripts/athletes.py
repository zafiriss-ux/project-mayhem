"""Athletes other than the owner: new-key, add, relogin, list, export, remove, purge (ADR-0067 D2, D5, D6, D9).

Runs on the routine machine. Zaf runs it; the athlete is present for ``relogin`` and types
their own Garmin password, which is never stored (D9.1). Consent is not given here: the
athlete gives it in their own Telegram chat with /agree (D4.1).

Usage:
    python scripts/athletes.py new-key
    python scripts/athletes.py add --name "Maria" --profile profile.json --chat 123456789
    python scripts/athletes.py relogin a-1234abcd
    python scripts/athletes.py list
    python scripts/athletes.py export a-1234abcd --out a-1234abcd.json
    python scripts/athletes.py remove a-1234abcd
    python scripts/athletes.py purge-expired
    python scripts/athletes.py reapply-deletions
    docker compose exec titan-worker python scripts/athletes.py list
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from titan.config.settings import get_settings  # noqa: E402
from titan.core import athlete_lifecycle as lifecycle  # noqa: E402
from titan.core.database import DatabaseManager  # noqa: E402


def _db() -> DatabaseManager:
    return DatabaseManager(db_dir=Path(get_settings().TITAN_DATA_DIR))


def cmd_add(args: argparse.Namespace, db: DatabaseManager) -> int:
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    athlete_id = lifecycle.add_athlete(db, args.name, profile, args.chat)
    print(athlete_id)
    print(f"Next: python scripts/athletes.py relogin {athlete_id}  (with the athlete present)")
    print("Then the athlete sends /consent and /agree in their own Telegram chat.")
    return 0


def cmd_relogin(args: argparse.Namespace, db: DatabaseManager) -> int:
    from titan.integrations.garmin_sync import relogin_athlete

    if not lifecycle.athlete_exists(db, args.athlete_id):
        print(f"no athlete {args.athlete_id}", file=sys.stderr)
        return 1
    print("The athlete types their own Garmin login now. It is not stored.")
    email = input("Garmin e-mail: ").strip()
    password = getpass.getpass("Garmin password: ")
    relogin_athlete(db, args.athlete_id, email, password, lambda: input("Garmin MFA code: ").strip())
    print(f"Garmin connected for {args.athlete_id}.")
    return 0


def cmd_new_key(_args: argparse.Namespace, _db: DatabaseManager) -> int:
    from titan.integrations.garmin_sync import create_athlete_token_key

    print(f"Wrote a new athletes' key to {create_athlete_token_key()} (mode 0600). Keep a copy outside the backups.")
    return 0


def _today(db: DatabaseManager, athlete_id: str) -> str:
    """This UTC day's morning briefing of the athlete, from worker_routine_executions (ADR-0060, D8)."""
    from titan.worker import ROUTINE_MAX_ATTEMPTS, ROUTINE_MORNING, _utc_now

    row = db.conn.execute(
        "SELECT attempts, delivered_at, completed_at FROM worker_routine_executions "
        "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
        (athlete_id, _utc_now().date().isoformat(), ROUTINE_MORNING),
    ).fetchone()
    if row is None:
        return "not started"
    attempts, delivered_at, completed_at = row
    if delivered_at:
        return "delivered"
    if completed_at:
        return f"left after {ROUTINE_MAX_ATTEMPTS} attempts"
    return f"attempt {attempts} not delivered"


def cmd_list(_args: argparse.Namespace, db: DatabaseManager) -> int:
    from titan.worker import _readiness_problem

    rows = db.conn.execute(
        "SELECT a.athlete_id, a.display_name, acc.garmin_token_state, acc.telegram_chat_id IS NOT NULL "
        "FROM athletes a LEFT JOIN athlete_accounts acc ON acc.athlete_id = a.athlete_id "
        "WHERE a.athlete_id != 'owner' ORDER BY a.created_at"
    ).fetchall()
    for athlete_id, name, garmin, chat in rows:
        consent = "yes" if db.has_current_consent(athlete_id) else "no"
        problem = _readiness_problem(db, athlete_id)
        ready = "yes" if problem is None else f"no ({problem})"
        print(
            f"{athlete_id}  {name}  garmin={garmin or 'none'}  chat={'yes' if chat else 'no'}  consent={consent}"
            f"  ready={ready}  today={_today(db, athlete_id)}"
        )
    return 0


def cmd_export(args: argparse.Namespace, db: DatabaseManager) -> int:
    text = lifecycle.export_json(lifecycle.export_athlete(db, args.athlete_id))
    if args.out is None:
        print(text)
        return 0
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if os.name == "posix":
        # The mode of os.open applies only to a new file; an existing one is tightened here,
        # before any personal data is written to it (D-108, TK-05).
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"Exported {args.athlete_id} to {args.out}")
    return 0


def cmd_remove(args: argparse.Namespace, db: DatabaseManager) -> int:
    if not lifecycle.athlete_exists(db, args.athlete_id):
        print(f"no athlete {args.athlete_id}", file=sys.stderr)
        return 1
    if not args.yes and input(f"Type {args.athlete_id} to delete every row of this athlete: ").strip() != args.athlete_id:
        print("Nothing deleted.")
        return 1
    try:
        counts = lifecycle.delete_athlete(db, args.athlete_id)
    except sqlite3.Error as exc:
        # Nothing was deleted; the deletion record is written, so the delete is retried (D-108).
        print(
            f"Delete of {args.athlete_id} failed ({type(exc).__name__}); no row was deleted. The deletion record"
            " is kept: fix the cause and run `athletes.py reapply-deletions` (the worker also does at start).",
            file=sys.stderr,
        )
        return 1
    except lifecycle.TokenFolderNotRemoved as exc:
        # The rows are gone but the Garmin token folder is not (D-108, TK-08).
        print(f"Delete of {args.athlete_id} incomplete: {exc}", file=sys.stderr)
        return 1
    print(f"Deleted {args.athlete_id}: {sum(counts.values())} rows.")
    return 0


def cmd_purge_expired(_args: argparse.Namespace, db: DatabaseManager) -> int:
    for athlete_id in lifecycle.purge_expired_athletes(db):
        print(f"Deleted {athlete_id} (30 days after /stop).")
    return 0


def cmd_reapply_deletions(_args: argparse.Namespace, db: DatabaseManager) -> int:
    for athlete_id in lifecycle.reapply_deletions(db):
        print(f"Deleted {athlete_id} again (deletion record).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("new-key", help="write the athletes' Garmin token key to TITAN_TOKEN_KEY_FILE, once").set_defaults(
        func=cmd_new_key
    )
    add = sub.add_parser("add", help="register an athlete: name, profile, private Telegram chat")
    add.add_argument("--name", required=True)
    add.add_argument("--profile", required=True, help="JSON file with every athlete_profiles field")
    add.add_argument("--chat", required=True, help="the athlete's private Telegram chat id")
    add.set_defaults(func=cmd_add)
    relogin = sub.add_parser("relogin", help="the athlete logs in to Garmin here; only the token is kept")
    relogin.add_argument("athlete_id")
    relogin.set_defaults(func=cmd_relogin)
    sub.add_parser("list", help="athletes other than the owner and what each still needs").set_defaults(func=cmd_list)
    export = sub.add_parser("export", help="one JSON document with every row of the athlete")
    export.add_argument("athlete_id")
    export.add_argument("--out", help="file to write (mode 0600); stdout when left out")
    export.set_defaults(func=cmd_export)
    remove = sub.add_parser("remove", help="delete the athlete: record, every row, token")
    remove.add_argument("athlete_id")
    remove.add_argument("--yes", action="store_true", help="skip typing the id to confirm")
    remove.set_defaults(func=cmd_remove)
    sub.add_parser("purge-expired", help="delete athletes 30 days after /stop").set_defaults(func=cmd_purge_expired)
    sub.add_parser("reapply-deletions", help="after a restore, delete recorded athletes again").set_defaults(
        func=cmd_reapply_deletions
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = _db()
    try:
        return args.func(args, db)
    except (ValueError, LookupError, RuntimeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
