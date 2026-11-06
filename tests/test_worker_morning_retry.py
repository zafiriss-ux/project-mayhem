"""Phase 4 step 12η: a retried morning is safe and sent once (D-109; SG-04, DW-01, DW-03, DW-06, DW-07, DW-09).

- A retry resends the stored decision only while that day's inputs are the ones it was
  computed on, with its distance, duration and caps. Newer inputs: the day is computed
  again through the gated pipeline and replaces the stored decision in place. When that
  is not possible, the stored decision is sent at most EASY.
- A briefing that reached Telegram is never sent again because recording it failed, and
  Zaf is not told it was "not delivered".
- One date, the claimed one, flows from the claim to the recorded decision; no new day
  starts after 12:00 UTC with several athletes.
- Attempts are at least 15 minutes apart; the athlete gets "TITAN system error" at most
  once a day; a left day gives Zaf one message even when closing it keeps failing.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from titan import worker
from titan.core.athlete import CONSENT_TEXT_VERSION
from titan.core.database import DatabaseManager
from titan.science.outcome_tracker import OutcomeTracker

pytestmark = pytest.mark.integration

_A = "a-0000000a"
_CHAT = 2000
_MORNING = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
_TODAY = "2026-10-15"
_GAP = timedelta(seconds=worker.ROUTINE_RETRY_DELAY_S)
_RUN_ATTEMPT = worker._run_attempt  # the real one; the fixture runs attempts in-process
_PROFILE = {
    "birth_date": "1988-07-02", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
    "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Volos", "location_country": "GR",
}
_TEMPO = {"session_type": "TEMPO", "distance_km": 10.0, "duration_min": 50, "max_duration_min": 60, "max_zone": 3}


class _Bot:
    """Stands in for TitanTelegramBot: records (chat, text) of what would reach Telegram."""

    sent: list[tuple[object, str]] = []

    def __init__(self, *_args, **kwargs) -> None:
        self.chat_id = kwargs.get("chat_id") or "OWNER"

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        type(self).sent.append((self.chat_id, text))
        return True

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        type(self).sent.append((self.chat_id, f"{title}: {message}"))
        return True

    def send_daily_coaching(self, data: dict) -> bool:
        type(self).sent.append((self.chat_id, f"BRIEFING {data['session']}"))
        return True


class _Coach:
    """Stands in for DailyCoach: stores the day's inputs, records the decision, then sends.

    It reads what the worker gives a real DailyCoach (the claimed day, the replace flag,
    the decision hook), each with the default a coach without them has.
    """

    runs: list[str] = []
    session: dict = dict(_TEMPO)
    delivers = False
    raises = False
    hrv = 62.0
    clock_during_run: datetime | None = None

    def __init__(self, db: DatabaseManager, athlete_id: str = "owner") -> None:
        self.db = db
        self.athlete_id = athlete_id
        self.telegram = _Bot(chat_id=_CHAT)

    def run_morning_routine(self) -> bool:
        cls = type(self)
        cls.runs.append(self.athlete_id)
        if cls.raises:
            raise RuntimeError("Garmin down")
        if cls.clock_during_run is not None:  # the run reaches its decision after midnight
            _set_clock(cls.clock_during_run)
        # A coach without the claimed day dates the routine by the clock, as DailyCoach did.
        day = getattr(self, "routine_date", None) or worker._utc_now().date().isoformat()
        self.db.save_daily_metric(day, hrv=cls.hrv, rhr=50, athlete_id=self.athlete_id)
        extra = {"replace_same_day": True} if getattr(self, "replace_decision", False) else {}
        OutcomeTracker(db=self.db, athlete_id=self.athlete_id).record_decision(
            session_planned="TEMPO", session_post_governance=cls.session["session_type"], locks_applied=[],
            governance_clean=True, phase="BASE", vlg_color="GREEN", apl_result={}, acwr=1.0,
            tsb_value=0.0, readiness_score=60.0, glycogen_debt=0.0, athlete_profile_id=self.athlete_id,
            date=day, **extra,
        )
        hook = getattr(self, "on_decision_recorded", None)
        if hook is not None:
            hook(dict(cls.session))
        if not cls.delivers:
            return False
        # As DailyCoach's send step: mark "sending", send, clear the mark if Telegram refused (MA-F5).
        before = getattr(self, "before_briefing_send", None)
        if before is not None:
            before()
        ok = self.telegram.send_daily_coaching({"session": cls.session["session_type"]})
        after = getattr(self, "after_briefing_send", None)
        if after is not None:
            after(bool(ok))
        return ok


_CLOCK = [_MORNING]


def _set_clock(when: datetime) -> None:
    _CLOCK[0] = when


@pytest.fixture
def db(tmp_path, monkeypatch):
    import titan.integrations.telegram_bot as telegram_bot

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("TITAN_DATA_DIR", str(data))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1000")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(telegram_bot, "TitanTelegramBot", _Bot)
    _set_clock(_MORNING)
    monkeypatch.setattr(worker, "_utc_now", lambda: _CLOCK[0])
    monkeypatch.setattr(worker, "_build_daily_coach", _Coach)
    monkeypatch.setattr(worker, "_prepare_weekly_plan", lambda *a: None)
    monkeypatch.setattr(worker, "_plan_next_week_on_sunday", lambda *a: None)
    monkeypatch.setattr(worker, "_run_attempt", worker._attempt_morning)  # in-process
    monkeypatch.setattr(worker, "_MARK_RETRY_DELAYS_S", (0.0, 0.0), raising=False)
    _Bot.sent = []
    _Coach.runs, _Coach.session, _Coach.delivers, _Coach.raises = [], dict(_TEMPO), False, False
    _Coach.hrv, _Coach.clock_during_run = 62.0, None
    manager = DatabaseManager(db_dir=data)
    manager.record_owner_garmin_display_name("owner-garmin-name")  # the owner's sync ran once (ADR-0076)
    manager.conn.execute("INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, ?)",
                         (_A, _A, "2026-10-01"))
    manager.conn.commit()
    manager.save_athlete_profile(_A, _PROFILE)
    manager.bind_garmin_account(_A, f"garmin-{_A}")
    manager.set_garmin_token_state(_A, "ok")
    from titan.integrations.garmin_sync import (
        athlete_token_path,  # a ready athlete has the token file (MA-F2)
    )
    athlete_token_path(_A).parent.mkdir(parents=True, exist_ok=True)
    athlete_token_path(_A).write_bytes(b"synthetic-token")
    manager.bind_telegram_chat(_A, _CHAT)
    manager.grant_consent(_A, CONSENT_TEXT_VERSION, now=_MORNING - timedelta(days=5))
    yield manager
    manager.close()
    get_settings.cache_clear()


def _to_athlete() -> list[str]:
    return [text for chat, text in _Bot.sent if str(chat) == str(_CHAT)]


def _to_zaf() -> list[str]:
    return [text for chat, text in _Bot.sent if chat == "OWNER"]


def _decisions(db: DatabaseManager) -> list[tuple]:
    return db.conn.execute(
        "SELECT date, session_post_governance FROM governance_outcomes WHERE athlete_id = ?", (_A,)
    ).fetchall()


def _attempt(db: DatabaseManager, n: int) -> bool:
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    return worker._attempt_morning(db, _A, _TODAY, n)


def _row(db: DatabaseManager) -> tuple:
    return db.conn.execute(
        "SELECT attempts, delivered_at IS NOT NULL, completed_at IS NOT NULL FROM worker_routine_executions "
        "WHERE athlete_id = ? AND routine_type = 'morning'", (_A,)
    ).fetchone()


# ── SG-04: the resend is checked against the day's inputs ────────────────────

def test_sg04_new_inputs_after_the_decision_are_computed_again_through_the_gates(db) -> None:
    assert _attempt(db, 1) is False  # TEMPO decided and recorded, Telegram failed
    db.save_daily_metric(_TODAY, hrv=30.0, rhr=68, athlete_id=_A)  # then today's HRV collapses
    _Coach.session, _Coach.delivers, _Coach.hrv = {"session_type": "EASY", "duration_min": 40}, True, 30.0

    assert _attempt(db, 2) is True

    assert _Coach.runs == [_A, _A]  # the gated routine ran again
    assert not any("Today's session: TEMPO" in text for text in _to_athlete())
    assert _decisions(db) == [(_TODAY, "EASY")]  # replaced in place: one row (D-098)


def test_sg04_unchanged_inputs_resend_the_decision_with_its_caps_and_say_it_may_repeat(db) -> None:
    assert _attempt(db, 1) is False

    assert _attempt(db, 2) is True

    assert _Coach.runs == [_A]  # not computed again
    [text] = _to_athlete()
    assert "Today's session: TEMPO" in text
    assert "10 km" in text and "50 min" in text and "at most 60 min" in text and "zone 3 at most" in text
    assert "repeats" in text  # DW-06: a send whose delivery was not recorded may come twice
    assert _decisions(db) == [(_TODAY, "TEMPO")]


def test_sg04_when_the_day_cannot_be_computed_again_the_resend_is_at_most_easy(db) -> None:
    assert _attempt(db, 1) is False
    db.save_daily_metric(_TODAY, hrv=30.0, rhr=68, athlete_id=_A)
    _Coach.raises = True

    assert _attempt(db, 2) is True

    [text] = _to_athlete()
    assert "Today's session: EASY" in text and "at most 45 min" in text
    assert "TEMPO" not in text
    assert _decisions(db) == [(_TODAY, "TEMPO")]  # the stored row is not touched


def test_sg04_the_resend_probe_new_hrv_and_rhr_are_not_sent_as_tempo(db, monkeypatch) -> None:
    """The audit's resend_stored.py: TEMPO stored, then HRV 30 / RHR 68 saved for today."""
    db.save_governance_decision({"athlete_profile_id": _A, "date": _TODAY, "session_planned": "TEMPO",
                                 "session_post_governance": "TEMPO", "locks_applied": []})
    db.save_daily_metric(_TODAY, hrv=30.0, rhr=68, athlete_id=_A)
    called: list[str] = []
    monkeypatch.setattr(worker, "_run_morning", lambda _db, aid, **_kw: called.append(aid) or True)

    # The day's first claimed attempt: the attempt number is the claim's (M0-01 fencing).
    assert _attempt(db, 1) is True

    assert called == [_A]
    assert not any("TEMPO" in text for text in _to_athlete())



# ── #1247 (CR-NEW-01): an injury opened after the decision ───────────────────

def _open_injury(db: DatabaseManager, athlete_id: str = _A) -> None:
    assert db.open_injury(athlete_id=athlete_id, description="synthetic calf", opened_at=_MORNING.isoformat())


def test_1247_an_injury_opened_after_the_decision_makes_the_retry_compute_the_day_again(db) -> None:
    assert _attempt(db, 1) is False  # TEMPO decided and recorded, Telegram failed
    _open_injury(db)  # nothing else changed: same metrics, same training log
    _Coach.session, _Coach.delivers = {"session_type": "REST"}, True  # H1 makes the day REST

    assert _attempt(db, 2) is True

    assert _Coach.runs == [_A, _A]  # the gated routine ran again
    assert not any("TEMPO" in text for text in _to_athlete())
    assert _decisions(db) == [(_TODAY, "REST")]  # replaced in place: one row


def test_1247_when_the_day_cannot_be_computed_again_an_open_injury_sends_rest_not_easy(db) -> None:
    assert _attempt(db, 1) is False
    _open_injury(db)
    _Coach.raises = True

    assert _attempt(db, 2) is True

    [text] = _to_athlete()
    assert "Today's session: REST" in text and "/injury off" in text
    assert "TEMPO" not in text and "EASY" not in text and "min" not in text


def test_1247_an_unreadable_injury_state_sends_rest_on_the_resend(db, monkeypatch) -> None:
    assert _attempt(db, 1) is False

    def _broken(**_kw):
        raise sqlite3.OperationalError("synthetic: injuries unreadable")

    monkeypatch.setattr(db, "get_open_injury", _broken)
    assert _attempt(db, 2) is True

    assert _Coach.runs == [_A]  # the inputs hash did not change: the stored decision is resent
    [text] = _to_athlete()
    assert "Today's session: REST" in text and "TEMPO" not in text
    assert "could not check for an open injury" in text


def test_1247_without_an_injury_the_resend_is_unchanged(db) -> None:
    _open_injury(db, "owner")  # another athlete's injury is not this athlete's
    assert _attempt(db, 1) is False

    assert _attempt(db, 2) is True

    assert _Coach.runs == [_A]
    [text] = _to_athlete()
    assert "Today's session: TEMPO" in text and "10 km" in text


def test_1247_the_inputs_hash_follows_the_open_injury_only(db) -> None:
    db.save_daily_metric(_TODAY, hrv=62.0, rhr=50, athlete_id=_A)
    before = db.routine_inputs_fingerprint(_A, _TODAY)
    _open_injury(db, "owner")
    assert db.routine_inputs_fingerprint(_A, _TODAY) == before  # another athlete's injury
    _open_injury(db)
    opened = db.routine_inputs_fingerprint(_A, _TODAY)
    assert opened not in (before, None)
    assert db.close_injury(athlete_id=_A, closed_at=_MORNING.isoformat())
    assert db.routine_inputs_fingerprint(_A, _TODAY) == before  # closed: the earlier hash again
    assert db.routine_inputs_fingerprint(_A, "2026-10-14") is None  # no day inputs: still None


@pytest.mark.unit
def test_sg04_a_replaced_decision_keeps_one_row(tmp_path) -> None:
    db = DatabaseManager(db_dir=tmp_path)
    try:
        tracker = OutcomeTracker(db=db, athlete_id=_A)
        common = {"session_planned": "TEMPO", "locks_applied": [], "governance_clean": True, "phase": "BASE",
                  "vlg_color": "GREEN", "apl_result": {}, "acwr": 1.0, "tsb_value": 0.0,
                  "readiness_score": 60.0, "glycogen_debt": 0.0, "athlete_profile_id": _A, "date": _TODAY}
        tracker.record_decision(session_post_governance="TEMPO", **common)
        tracker.record_decision(session_post_governance="EASY", replace_same_day=True, **common)
        assert _decisions(db) == [(_TODAY, "EASY")]
    finally:
        db.close()


# ── DW-01: recording the delivery fails after Telegram delivered ──────────────

def _flaky_mark(db: DatabaseManager, monkeypatch, failures: int) -> None:
    real = db.mark_routine_delivered
    left = [failures]

    def mark(**kw):
        if kw.get("athlete_id") == _A and left[0] > 0:
            left[0] -= 1
            raise sqlite3.OperationalError("database is locked")
        return real(**kw)

    monkeypatch.setattr(db, "mark_routine_delivered", mark)


def _delivering_run_morning(db_: DatabaseManager, athlete_id: str = "owner", **_kw) -> bool:
    db_.save_governance_decision({"athlete_profile_id": athlete_id, "date": _TODAY, "session_planned": "EASY",
                                  "session_post_governance": "EASY", "locks_applied": []})
    _Bot.sent.append((_CHAT, "FULL_BRIEFING"))
    return True


def test_dw01_a_delivery_that_cannot_be_recorded_is_not_sent_again_nor_reported_lost(db, monkeypatch) -> None:
    """The audit's s1_mark_fails.py: the mark fails 3 times, five polls of the day follow."""
    monkeypatch.setattr(worker, "_run_morning", _delivering_run_morning)
    _flaky_mark(db, monkeypatch, failures=3)

    for poll in range(5):
        _set_clock(_MORNING + poll * (_GAP + timedelta(minutes=5)))
        worker._scheduled_morning(db, _A)

    assert _to_athlete() == ["FULL_BRIEFING"]
    assert not [text for text in _to_zaf() if "not delivered" in text]
    assert _row(db) == (1, 1, 1)  # recorded on a later poll


def test_dw01_a_failed_record_is_tried_again_at_once(db, monkeypatch) -> None:
    monkeypatch.setattr(worker, "_run_morning", _delivering_run_morning)
    _flaky_mark(db, monkeypatch, failures=2)

    worker._scheduled_morning(db, _A)

    assert _row(db) == (1, 1, 1)


def _child_sends_but_cannot_record(db_path: str, athlete_id: str, execution_date: str, attempt: int) -> None:
    """Child process: the briefing goes out, every write of the delivery fails."""
    from titan import worker as child_worker
    from titan.core import database

    def _locked(self, **_kw):
        raise sqlite3.OperationalError("database is locked")

    def _sent(db_, athlete_id_="owner", **_kw) -> bool:
        with open(os.environ["TITAN_TEST_SEND_LOG"], "a", encoding="utf-8") as fh:
            fh.write(f"briefing {athlete_id_} {attempt}\n")
        return True

    database.DatabaseManager.mark_routine_delivered = _locked
    child_worker._MARK_RETRY_DELAYS_S = (0.0, 0.0)
    child_worker._run_morning = _sent
    child_worker._child_morning(db_path, athlete_id, execution_date, attempt)


@pytest.mark.slow
def test_dw01_a_child_that_sent_but_could_not_record_hands_the_record_to_the_parent(
    db, monkeypatch, tmp_path
) -> None:
    send_log = tmp_path / "sends.log"
    monkeypatch.setenv("TITAN_TEST_SEND_LOG", str(send_log))
    monkeypatch.setattr(worker, "_run_attempt", _RUN_ATTEMPT)  # a real child process
    monkeypatch.setattr(worker, "_CHILD_ENTRY", _child_sends_but_cannot_record)

    for poll in range(3):
        _set_clock(_MORNING + poll * (_GAP + timedelta(minutes=5)))
        worker._scheduled_morning(db, _A)

    assert send_log.read_text(encoding="utf-8").splitlines() == [f"briefing {_A} 1"]
    assert _row(db) == (1, 1, 1)
    assert not [text for text in _to_zaf() if "not delivered" in text]


# ── DW-06: a child that dies after Telegram accepted the briefing ────────────

def _child_dies_after_sending(db_path: str, athlete_id: str, execution_date: str, attempt: int) -> None:
    """The audit's s2_child_dies_after_send.py: attempt 1 sends, then the process dies."""
    import titan.integrations.telegram_bot as child_telegram
    from titan import worker as child_worker

    log = os.environ["TITAN_TEST_SEND_LOG"]

    class _FileBot:
        def __init__(self, *_a, **_k) -> None:
            pass

        def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(text.replace("\n", " | ") + "\n")
            return True

    def _sent_then_killed(db_, athlete_id_="owner", **_kw) -> bool:
        db_.save_governance_decision({"athlete_profile_id": athlete_id_, "date": execution_date,
                                      "session_planned": "EASY", "session_post_governance": "EASY",
                                      "locks_applied": []})
        child_worker._mark_briefing_sending(db_, athlete_id_, execution_date)  # as the coach does (MA-F5)
        _FileBot().send_message("FULL_BRIEFING")
        os._exit(9)

    child_telegram.TitanTelegramBot = _FileBot
    child_worker._run_morning = _sent_then_killed
    child_worker._child_morning(db_path, athlete_id, execution_date, attempt)


@pytest.mark.slow
def test_dw06_after_a_crash_mid_send_the_athlete_gets_one_reminder_line(db, monkeypatch, tmp_path) -> None:
    """MA-F5 (ADR-0069 §8): the briefing is not sent a second time; one short line instead."""
    send_log = tmp_path / "sends.log"
    monkeypatch.setenv("TITAN_TEST_SEND_LOG", str(send_log))
    monkeypatch.setattr(worker, "_run_attempt", _RUN_ATTEMPT)
    monkeypatch.setattr(worker, "_CHILD_ENTRY", _child_dies_after_sending)

    for poll in range(3):
        _set_clock(_MORNING + poll * (_GAP + timedelta(minutes=5)))
        worker._scheduled_morning(db, _A)

    first, second = send_log.read_text(encoding="utf-8").splitlines()
    assert first == "FULL_BRIEFING"
    assert "Today's session" not in second
    assert second == worker._crash_reminder_text(_A)
    assert _row(db) == (2, 1, 1)


# ── CR-NEW-02 (#1248): a superseded attempt never overwrites the newer decision ──

def _decision(session: str) -> dict:
    return {"athlete_profile_id": _A, "date": _TODAY, "session_planned": "TEMPO",
            "session_post_governance": session, "locks_applied": []}


def _stored(db: DatabaseManager) -> list[str]:
    return [row[1] for row in _decisions(db)]


def _stale_coach(db: DatabaseManager, takeover, *, replace: bool = False):
    """Attempt 1's real DailyCoach effects, bound as the worker binds them.

    Its ownership check passes, and ``takeover`` then runs: a later attempt in another
    connection (as another process) takes the day over before attempt 1 writes.
    """
    from titan.orchestration.daily_coach import DailyCoach

    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    coach = DailyCoach.__new__(DailyCoach)
    coach.athlete_id = _A
    coach.db = db
    coach.telegram = _Bot(chat_id=_CHAT)
    coach.outcome_tracker = OutcomeTracker(db=db, athlete_id=_A)
    worker._bind_day(coach, db, _A, worker._MorningDay(execution_date=_TODAY, attempt=1, replace_decision=replace))
    real_check, checks = coach.attempt_is_current, []

    def _check() -> bool:
        owns = real_check()
        if not checks:  # attempt 1 passed the check; attempt 2 runs before its write
            takeover()
        checks.append(owns)
        return owns

    coach.attempt_is_current = _check
    return coach


def _result(session: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        decision_trace={"session_planned_pre_governance": "TEMPO", "session_post_governance": session,
                        "locks_applied": [], "phase": "BASE"},
        session_plan={"session_type": session, "distance_km": 10.0},
        coaching_payload={"session": session},
    )


def _newer_attempt_delivers_rest(data_dir: Path):
    def _takeover() -> None:
        other = DatabaseManager(db_dir=data_dir)
        try:
            state = other.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                                started_at=_MORNING, max_attempts=3)
            assert state == ("run", 2)
            other.save_governance_decision(_decision("REST"))
            other.update_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                        fields={"session": {"session_type": "REST"}})
            other.mark_routine_delivered(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                         delivered_at=_MORNING)
        finally:
            other.close()
    return _takeover


def _data_dir() -> Path:
    return Path(os.environ["TITAN_DATA_DIR"])


@pytest.mark.parametrize("replace", [False, True], ids=["first decision", "recomputed decision"])
def test_1248_a_superseded_attempt_does_not_overwrite_the_newer_rest(db, replace) -> None:
    if replace:  # attempt 1 is itself a recompute that replaces an earlier TEMPO in place
        db.save_governance_decision(_decision("TEMPO"))
    coach = _stale_coach(db, _newer_attempt_delivers_rest(_data_dir()), replace=replace)

    coach._make_record_outcome_handler()(None, _result("TEMPO"))
    sent = coach._make_send_telegram_handler()(None, _result("TEMPO"))

    assert _stored(db) == ["REST"]  # the durable row is attempt 2's REST
    resume = db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning")
    assert resume.get("session") == {"session_type": "REST"} and "inputs" not in resume
    assert coach.attempt_lost is True
    assert sent is False and _to_athlete() == []  # attempt 1 sends nothing
    assert _row(db) == (2, 1, 1)


def test_1248_the_attempt_that_owns_the_day_records_its_decision(db) -> None:
    coach = _stale_coach(db, lambda: None)

    coach._make_record_outcome_handler()(None, _result("TEMPO"))

    assert _stored(db) == ["TEMPO"]
    resume = db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning")
    assert resume["session"]["session_type"] == "TEMPO" and "inputs" in resume
    assert coach.attempt_lost is False


@pytest.mark.parametrize("closed", ["delivered", "left"])
def test_1248_the_fence_refuses_a_closed_or_superseded_day_at_the_database(db, closed) -> None:
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    assert db.save_governance_decision(_decision("REST"), fence=("morning", 1)) is True
    assert db.save_governance_decision(_decision("TEMPO"), fence=("morning", 2)) is False  # not its attempt
    assert db.replace_governance_decision_on(_decision("TEMPO"), fence=("morning", 2)) is False
    with pytest.raises(LookupError):
        db.update_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                 fields={"session": "TEMPO"}, attempt=2)
    if closed == "delivered":
        db.mark_routine_delivered(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                  delivered_at=_MORNING)
    else:
        db.conn.execute("UPDATE worker_routine_executions SET completed_at = ? WHERE athlete_id = ?",
                        (_MORNING.isoformat(), _A))
        db.conn.commit()
    assert db.save_governance_decision(_decision("TEMPO"), fence=("morning", 1)) is False
    assert db.replace_governance_decision_on(_decision("TEMPO"), fence=("morning", 1)) is False
    with pytest.raises(LookupError):
        db.update_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                 fields={"session": "TEMPO"}, attempt=1)
    assert _stored(db) == ["REST"]
    assert "session" not in db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning")


def test_1248_a_superseded_attempt_does_not_touch_the_newer_attempts_sending_mark(db) -> None:
    coach = _stale_coach(db, lambda: None)
    coach._make_record_outcome_handler()(None, _result("TEMPO"))  # attempt 1 still owns the day here
    _newer_attempt_delivers_rest(_data_dir())()  # attempt 2 takes over before attempt 1 marks its send

    coach.before_briefing_send()
    coach.after_briefing_send(False)

    resume = db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning")
    assert "sending" not in resume and resume["session"] == {"session_type": "REST"}


def test_1248_a_failed_fenced_write_leaves_no_transaction_open(db) -> None:
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    broken = {**_decision("TEMPO"), "session_planned": None}  # NOT NULL: the statement fails
    with pytest.raises(sqlite3.IntegrityError):
        db.save_governance_decision(broken, fence=("morning", 1))
    assert db.conn.in_transaction is False
    db.save_governance_decision(_decision("REST"))
    with pytest.raises(sqlite3.IntegrityError):
        db.replace_governance_decision_on(broken, fence=("morning", 1))
    assert db.conn.in_transaction is False
    assert _stored(db) == ["REST"]


@pytest.mark.unit
def test_1248_a_fenced_decision_without_a_database_is_refused() -> None:
    from titan.science.outcome_tracker import DecisionNotRecorded

    tracker = OutcomeTracker(db=None, athlete_id=_A)
    with pytest.raises(DecisionNotRecorded):
        tracker.record_decision(
            session_planned="TEMPO", session_post_governance="TEMPO", locks_applied=[], governance_clean=True,
            phase="BASE", vlg_color="GREEN", apl_result={}, acwr=1.0, tsb_value=0.0, readiness_score=60.0,
            glycogen_debt=0.0, date=_TODAY, fence=("morning", 1),
        )
    assert tracker._decisions == []


# ── DEL-NEW-01 (#1444): a late delivery of a superseded attempt is not the newer day's ──

def _late_ack_then(db: DatabaseManager, monkeypatch, *, newer_send_ok: bool) -> dict:
    """The issue's interleaving, attempts 2 and 3 in their own connections and threads.

    Attempt 1 stored TEMPO (Telegram failed). Attempt 2 resends it; while Telegram holds its
    acknowledgement, new inputs arrive and attempt 3 takes the day over, records REST and
    marks its send. Attempt 2's acknowledgement then returns; only after that does Telegram
    answer attempt 3 (``newer_send_ok``).
    """
    import threading

    assert _attempt(db, 1) is False  # TEMPO decided and recorded, Telegram failed
    newer_sending, older_acked = threading.Event(), threading.Event()
    seen: dict = {}
    _Coach.session, _Coach.delivers, _Coach.hrv = {"session_type": "REST"}, True, 30.0

    def _newer_attempt() -> None:
        other = DatabaseManager(db_dir=_data_dir())
        try:
            seen["newer"] = _attempt(other, 3)
        finally:
            other.close()

    def _held_rest(self, data: dict) -> bool:  # attempt 3's briefing
        _Bot.sent.append((self.chat_id, f"BRIEFING {data['session']}"))
        newer_sending.set()
        assert older_acked.wait(10)
        return newer_send_ok

    newer = threading.Thread(target=_newer_attempt)
    real_send = _Bot.send_message

    def _held_ack(self, text: str, parse_mode: str = "Markdown") -> bool:  # attempt 2's resend
        if "Today's session: TEMPO" in text:
            db.save_daily_metric(_TODAY, hrv=30.0, rhr=68, athlete_id=_A)  # new inputs meanwhile
            newer.start()
            assert newer_sending.wait(10)  # attempt 3 recorded REST and marked its send
            seen["before_ack"] = (_stored(db), db.get_routine_resume(
                athlete_id=_A, execution_date=_TODAY, routine_type="morning").get("sending"))
        return real_send(self, text, parse_mode)

    monkeypatch.setattr(_Bot, "send_message", _held_ack)
    monkeypatch.setattr(_Bot, "send_daily_coaching", _held_rest)
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    seen["older"] = worker._attempt_morning(db, _A, _TODAY, 2)
    seen["after_ack"] = _row(db), db.get_routine_resume(
        athlete_id=_A, execution_date=_TODAY, routine_type="morning").get("sending")
    older_acked.set()
    newer.join(10)
    return seen


def test_1444_a_late_ack_does_not_close_the_newer_day_and_its_failure_is_reported(db, monkeypatch) -> None:
    seen = _late_ack_then(db, monkeypatch, newer_send_ok=False)

    stored, sending = seen["before_ack"]
    assert stored == ["REST"] and sending
    assert seen["older"] is True  # attempt 2's TEMPO did reach Telegram
    assert seen["after_ack"] == ((3, 0, 0), sending)  # the newer day stays open, its mark stays
    assert seen["newer"] is False
    assert _row(db) == (3, 0, 1)  # attempt 3 was the last: the day is left, not delivered
    assert _stored(db) == ["REST"]
    assert any("Morning briefing not delivered" in text for text in _to_zaf())  # the failure is told


def test_1444_a_late_ack_then_the_newer_rest_delivers(db, monkeypatch) -> None:
    seen = _late_ack_then(db, monkeypatch, newer_send_ok=True)

    assert seen["after_ack"][0] == (3, 0, 0)
    assert seen["newer"] is True
    assert _row(db) == (3, 1, 1)  # delivered by attempt 3's own briefing
    assert "BRIEFING REST" in _to_athlete()
    assert not any("not delivered" in text for text in _to_zaf())


def test_1444_the_delivery_fence_at_the_database(db) -> None:
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    worker._mark_briefing_sending(db, _A, _TODAY, 2)

    assert worker._mark_delivered(db, _A, _TODAY, 1) is True  # nothing left for attempt 1 to record
    assert _row(db) == (2, 0, 0)
    assert db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning").get("sending")
    assert worker._day_key(db, _A, _TODAY) not in worker._UNRECORDED_SENDS

    assert worker._mark_delivered(db, _A, _TODAY, 2) is True  # the owning attempt records
    assert _row(db) == (2, 1, 1)
    assert not db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning").get("sending")
    assert db.mark_routine_delivered(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                     delivered_at=_MORNING, attempt=2) is False  # closed: not twice


# ── MA-F5: the "sending" mark (ADR-0069 §8) ───────────────────────────────────

def test_maf5_a_refused_send_clears_the_mark_and_the_retry_resends_the_decision(db, monkeypatch) -> None:
    _Coach.delivers = True
    with monkeypatch.context() as patch:
        patch.setattr(_Bot, "send_daily_coaching", lambda self, data: False)  # Telegram refuses it
        assert _attempt(db, 1) is False
    assert not db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning").get("sending")

    assert _attempt(db, 2) is True
    [text] = _to_athlete()
    assert "Today's session: TEMPO" in text and "repeats" in text


def test_maf5_a_mark_left_by_a_crash_sends_one_line_and_closes_the_day(db) -> None:
    _Coach.delivers = True
    # Attempt 1 claimed the day, wrote the mark and died in the middle of the send.
    db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                             started_at=_MORNING, max_attempts=3)
    worker._mark_briefing_sending(db, _A, _TODAY)
    db.save_governance_decision({"athlete_profile_id": _A, "date": _TODAY, "session_planned": "TEMPO",
                                 "session_post_governance": "TEMPO", "locks_applied": []})

    assert _attempt(db, 2) is True

    assert _Coach.runs == []  # nothing computed or sent again
    assert _to_athlete() == [worker._crash_reminder_text(_A)]
    assert _row(db)[1:] == (1, 1)


def test_maf5_a_delivered_briefing_leaves_no_mark(db) -> None:
    _Coach.delivers = True
    assert _attempt(db, 1) is True
    assert not db.get_routine_resume(athlete_id=_A, execution_date=_TODAY, routine_type="morning").get("sending")


@pytest.mark.unit
def test_maf5_the_owner_is_told_to_send_today() -> None:
    assert "/today" in worker._crash_reminder_text("owner")
    assert "/today" not in worker._crash_reminder_text(_A)  # athletes have no /today (ADR-0067 D10.3)


@pytest.mark.unit
def test_maf5_daily_coach_marks_before_sending_and_reports_after() -> None:
    from titan.orchestration.daily_coach import DailyCoach

    calls: list[object] = []

    class _Telegram:
        def send_daily_coaching(self, payload) -> bool:
            calls.append("send")
            return False

    class _Result:
        coaching_payload: dict = {}

    coach = DailyCoach.__new__(DailyCoach)
    coach.telegram = _Telegram()
    coach.routine_date = _TODAY
    coach.before_briefing_send = lambda: calls.append("before")
    coach.after_briefing_send = lambda ok: calls.append(("after", ok))

    assert coach._make_send_telegram_handler()(None, _Result()) is False
    assert calls == ["before", "send", ("after", False)]


# ── DW-03: one date from the claim to the recorded decision ──────────────────

def test_dw03_a_morning_that_crosses_midnight_records_the_day_it_was_claimed_for(db) -> None:
    """The audit's s3_midnight.py: claimed at 23:59, the decision is recorded after midnight."""
    late = datetime(2026, 10, 14, 23, 59, tzinfo=UTC)
    _set_clock(late)
    _Coach.delivers, _Coach.clock_during_run = True, late + timedelta(minutes=2)
    db.begin_routine_attempt(athlete_id=_A, execution_date="2026-10-14", routine_type="morning",
                             started_at=late, max_attempts=3)

    assert worker._attempt_morning(db, _A, "2026-10-14", 1) is True

    assert _decisions(db) == [("2026-10-14", "TEMPO")]
    assert db.conn.execute(
        "SELECT COUNT(*) FROM daily_metrics WHERE athlete_id = ? AND date = '2026-10-14'", (_A,)
    ).fetchone() == (1,)


@pytest.mark.unit
def test_dw03_daily_coach_records_the_decision_on_the_claimed_day() -> None:
    from titan.orchestration.daily_coach import DailyCoach

    recorded: list[dict] = []

    class _Tracker:
        def record_decision(self, **kwargs) -> None:
            recorded.append(kwargs)

    class _Result:
        decision_trace: dict = {}
        session_plan: dict = {"session_type": "EASY"}

    coach = DailyCoach.__new__(DailyCoach)
    coach.outcome_tracker = _Tracker()
    coach.athlete_id = _A
    coach.routine_date = "2026-10-14"

    coach._make_record_outcome_handler()(None, _Result())

    assert recorded[0]["date"] == "2026-10-14"


def test_dw03_no_new_morning_starts_after_the_cut_off(db) -> None:
    _Coach.delivers = True
    _set_clock(_MORNING.replace(hour=getattr(worker, "ROUTINE_LAST_START_HOUR_UTC", 12), minute=30))

    worker._scheduled_morning(db, _A)

    assert _Coach.runs == [] and _to_athlete() == []
    assert _row(db) is None  # nothing written for the day


def test_dw03_a_day_started_before_the_cut_off_still_gets_its_retries(db) -> None:
    _set_clock(_MORNING.replace(hour=11, minute=55))
    worker._scheduled_morning(db, _A)  # attempt 1, not delivered
    _Coach.delivers = True
    _set_clock(_MORNING.replace(hour=12, minute=15))

    worker._scheduled_morning(db, _A)

    assert _row(db) == (2, 1, 1)


# ── DW-07: attempts are spaced; the athlete hears of an error once ───────────

def test_dw07_polls_a_minute_apart_take_one_attempt(db) -> None:
    for poll in range(5):  # five 60 s polls
        _set_clock(_MORNING + timedelta(minutes=poll))
        worker._scheduled_morning(db, _A)

    assert _Coach.runs == [_A] and _row(db)[0] == 1
    _set_clock(_MORNING + _GAP)
    worker._scheduled_morning(db, _A)  # 15 minutes after the first: the second attempt
    assert _row(db)[0] == 2


class _PipelineFailsCoach(_Coach):
    """Runs the real coaching pipeline, whose decision step raises."""

    def _decision_pipeline(self, **_kw):
        raise RuntimeError("governance exploded")

    def _effect_runner(self, _result) -> bool:
        return True

    def run_morning_routine(self) -> bool:
        from titan.orchestration.coaching_pipeline import AthleteCoachingContext, coaching_pipeline

        type(self).runs.append(self.athlete_id)
        return coaching_pipeline(AthleteCoachingContext(
            athlete_id=self.athlete_id, coach=self, garmin_data={}, soreness=3, subjective_fatigue_score=3,
            today_rhr=50, today_sleep_score=80, today_sleep_hours=7.5, baseline_rhr_for_comparison=50.0,
            persistence_degraded=False, garmin_data_stale=False, latest_hrv=60.0, baseline_hrv=60.0,
            hrv_summary={}, afi_final=0.0, afi_constraints={}, tsb_value=0.0, tsb_status="", cs_thermal=None,
            garmin_trust=None, garmin_report_payload={}, startup_hydration_confidence={},
            startup_confidence_applies=False,
        ))


def test_dw07_the_athlete_is_told_of_a_system_error_once_a_day(db, monkeypatch) -> None:
    monkeypatch.setattr(worker, "_build_daily_coach", _PipelineFailsCoach)

    for attempt in range(3):
        _set_clock(_MORNING + attempt * (_GAP + timedelta(minutes=5)))
        worker._scheduled_morning(db, _A)

    assert _Coach.runs == [_A] * 3
    assert len([text for text in _to_athlete() if text.startswith("TITAN system error")]) == 1
    assert len([text for text in _to_zaf() if "not delivered" in text]) == 1


# ── DW-09: a left day that cannot be closed tells Zaf once ───────────────────

def test_dw09_a_left_day_that_cannot_be_closed_tells_zaf_once(db, monkeypatch) -> None:
    for _ in range(3):
        db.begin_routine_attempt(athlete_id=_A, execution_date=_TODAY, routine_type="morning",
                                 started_at=_MORNING, max_attempts=3)

    def _locked(**_kw):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "complete_routine_execution", _locked)

    for poll in range(4):
        _set_clock(_MORNING + timedelta(minutes=poll))
        worker._scheduled_morning(db, _A)

    assert len([text for text in _to_zaf() if "not delivered" in text]) == 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__]))
