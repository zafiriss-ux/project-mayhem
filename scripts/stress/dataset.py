"""Deterministic synthetic dataset for the TITAN OS DB stress test.

Everything here is synthetic: athlete ids are ``athNNNNN``, names are tags, and all
values come from ``random.Random`` seeded with ``f"{seed}:{athlete_index}"`` (string
seeds are hashed deterministically by CPython, so the same seed gives the same data on
every run and machine).

Shape (per athlete):
  * 50-100 activities on distinct days inside the 364 days before ``anchor``;
  * one Garmin-style weekly sync payload per 7-day window (52 windows), shaped like the
    dict ``persist_garmin_data`` receives: ``activities``, ``sleep``, ``hrv``, ``weight``;
  * anomalies are injected PER RECORD: each activity record is anomalous with
    probability ``ACTIVITY_ANOMALY_RATE`` (one anomaly class per anomalous record), and
    each sync's "today" daily-metrics record with probability ``DAILY_ANOMALY_RATE``.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

ACTIVITY_ANOMALY_RATE = 0.01
DAILY_ANOMALY_RATE = 0.01
WINDOWS = 52  # weekly syncs covering 364 days
ACTIVITY_ID_BASE = 7_000_000_000

ACTIVITY_TYPES = ("running", "running", "running", "interval_training", "tempo_run", "long_run")

# class -> (what the ADRs / implemented policy say should happen, reference)
ACTIVITY_ANOMALY_CLASSES: dict[str, tuple[str, str]] = {
    "hr_missing": ("store, avg_hr/max_hr NULL, no substitute value", "ADR-0051, ADR-0023 §4"),
    "distance_zero": ("ADR-0026 names 0 km + 1 h as corruption; no rule in Table 1", "ADR-0026 Context §1"),
    "distance_negative": ("no explicit rule; physically impossible -> reject or flag expected", "ADR-0026 intent"),
    "duration_zero_with_distance": ("reject (record skipped)", "ADR-0026 Table 1"),
    "duration_negative": ("no explicit rule; physically impossible -> reject or flag expected", "ADR-0026 intent"),
    "pace_absurd": ("warn -> stored with quality_flag='degraded'", "data_sanity SV-17"),
    "hr_extreme": ("no write-time HR bound for activities; stored", "ADR-0023 (no activity HR bound)"),
    "max_hr_lt_avg_hr": ("reject (record skipped)", "ADR-0026 Table 1"),
    "load_extreme": ("stored; nulled on read (>2x span) by validate_single", "ADR-0023 §3"),
    "load_negative": ("stored; excluded on read (SQL training_load > 0)", "ADR-0023 §3"),
    "wrong_type_distance": ("application validation should reject the record", "ADR-0026 intent"),
    "wrong_type_hr": ("application validation should reject or null the field", "ADR-0026 intent"),
    "date_missing": ("mandatory field -> reject", "ADR-0026 Layer 3 (date mandatory)"),
    "date_null": ("mandatory field -> reject (NOT NULL)", "ADR-0026 Layer 3"),
    "date_unparseable": ("warn -> stored with quality_flag='degraded'", "data_sanity timestamp_unparseable"),
    "date_future": ("reject (record skipped)", "ADR-0026 Table 1"),
    "dup_in_payload": ("second copy rejected", "data_sanity duplicate_activity_id_in_payload"),
    "dup_resync": ("re-sent in next sync -> ignored (INSERT OR IGNORE + unique index)", "T5-69 / T1-14"),
    "extid_collision_other_athlete": ("stored for its own athlete (isolation)", "ADR-0040"),
    "manual_duplicate": ("no rule for manual sessions without Garmin id", "ADR-0026 (duplicate rule is Garmin-only)"),
}

DAILY_ANOMALY_CLASSES: dict[str, tuple[str, str]] = {
    "hrv_zero": ("HRV nulled (sensor failure), rest of row stored", "ADR-0023 §3, ADR-0026"),
    "hrv_extreme": ("HRV nulled (>2x span)", "ADR-0023 §3"),
    "rhr_absurd": ("RHR nulled (>2x span)", "ADR-0023 §3"),
    "weight_negative": ("ADR-0023: within one span of bound -> clamp to bound", "ADR-0023 §3"),
    "weight_zero": ("treated as missing -> NULL", "ADR-0023 §3 / ADR-0051"),
    "sleep_minutes_as_hours": ("sleep nulled (>2x span)", "ADR-0023 §3"),
    "sleep_tiny": ("warn -> quality_flag='degraded', value kept", "data_sanity SV-17"),
    "all_optional_missing": ("row stored with NULLs, no substitute (no 7.5 h sleep)", "ADR-0051"),
}


def athlete_id(i: int) -> str:
    return f"ath{i:05d}"


def activity_ext_id(i: int, k: int) -> str:
    return str(ACTIVITY_ID_BASE + i * 1000 + k)


@dataclass
class AthleteData:
    index: int
    athlete_id: str
    activities: list[dict]                       # clean activity records (ground truth)
    syncs: list[tuple[str, dict]]                # (today_str, garmin_data) oldest first
    activity_anomalies: dict[int, str]           # k -> anomaly class
    daily_anomalies: dict[str, str]              # today_str -> anomaly class
    expected_hrv: dict[str, float]               # date -> clean HRV expected in DB
    manual_entries: list[dict] = field(default_factory=list)  # for manual_duplicate
    profile: dict = field(default_factory=dict)


def _activity(rng: random.Random, i: int, k: int, day: date, prof: dict) -> dict:
    atype = rng.choice(ACTIVITY_TYPES)
    if atype == "long_run":
        dist = rng.uniform(16, 32)
        pace = prof["pace"] * rng.uniform(1.02, 1.10)
    elif atype == "interval_training":
        dist = rng.uniform(6, 12)
        pace = prof["pace"] * rng.uniform(0.80, 0.92)
    elif atype == "tempo_run":
        dist = rng.uniform(8, 14)
        pace = prof["pace"] * rng.uniform(0.86, 0.95)
    else:
        dist = rng.uniform(4, 14)
        pace = prof["pace"] * rng.uniform(0.97, 1.08)
    dist = round(dist, 3)
    dur = int(dist * pace)
    avg_hr = int(prof["hr_max"] * rng.uniform(0.68, 0.88))
    max_hr = min(prof["hr_max"], avg_hr + rng.randint(5, 25))
    load = int(dur / 60 * rng.uniform(0.8, 2.2))
    return {
        "activity_id": activity_ext_id(i, k),
        "date": day.isoformat(),
        "activity_type": atype,
        "distance_km": dist,
        "duration_sec": dur,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "estimated_training_load": load,
        "avg_pace_sec_per_km": int(pace),
        "name": f"{athlete_id(i)}:{k}",
    }


def _inject_activity(act: dict, cls: str, i: int, anchor: date) -> dict:
    a = dict(act)
    if cls == "hr_missing":
        a.pop("avg_hr"); a.pop("max_hr")  # noqa: E702
    elif cls == "distance_zero":
        a["distance_km"] = 0.0
    elif cls == "distance_negative":
        a["distance_km"] = -abs(a["distance_km"])
    elif cls == "duration_zero_with_distance":
        a["duration_sec"] = 0
    elif cls == "duration_negative":
        a["duration_sec"] = -abs(a["duration_sec"])
    elif cls == "pace_absurd":
        a["duration_sec"] = max(1, a["duration_sec"] // 60)  # minutes read as seconds
    elif cls == "hr_extreme":
        a["avg_hr"], a["max_hr"] = 255, 299
    elif cls == "max_hr_lt_avg_hr":
        a["max_hr"] = a["avg_hr"] - 20
    elif cls == "load_extreme":
        a["estimated_training_load"] = 25_000
    elif cls == "load_negative":
        a["estimated_training_load"] = -50
    elif cls == "wrong_type_distance":
        a["distance_km"] = f"{a['distance_km']:.1f}".replace(".", ",") + "km"
    elif cls == "wrong_type_hr":
        a["avg_hr"] = "n/a"
    elif cls == "date_missing":
        a.pop("date")
    elif cls == "date_null":
        a["date"] = None
    elif cls == "date_unparseable":
        a["date"] = f"{a['date'][:4]}-02-30"
    elif cls == "date_future":
        a["date"] = (anchor + timedelta(days=400)).isoformat()
    elif cls == "extid_collision_other_athlete":
        a["activity_id"] = activity_ext_id(i - 1, 0)
    # dup_in_payload / dup_resync / manual_duplicate keep the record valid;
    # the anomaly is in how often / through which path it is sent.
    return a


def _inject_daily(cls: str, sleep: dict, hrv_today: dict, weight: dict) -> None:
    if cls == "hrv_zero":
        hrv_today["rmssd"] = 0.0
    elif cls == "hrv_extreme":
        hrv_today["rmssd"] = 900.0
    elif cls == "rhr_absurd":
        sleep["resting_hr"] = 250
    elif cls == "weight_negative":
        weight["weight_kg"] = -70.0
    elif cls == "weight_zero":
        weight["weight_kg"] = 0.0
    elif cls == "sleep_minutes_as_hours":
        sleep["total_sleep_hours"] = 450.0
    elif cls == "sleep_tiny":
        sleep["total_sleep_hours"] = 0.5


def generate_athlete(seed: int, i: int, anchor: date) -> AthleteData:
    rng = random.Random(f"{seed}:{i}")
    aid = athlete_id(i)
    prof = {
        "pace": rng.uniform(255, 420),          # easy pace s/km
        "hr_max": rng.randint(172, 202),
        "rhr": rng.randint(40, 68),
        "weight": round(rng.uniform(48, 95), 1),
        "hrv": rng.uniform(30, 110),
        "sex": rng.choice(("male", "female")),
    }
    n = rng.randint(50, 100)
    offsets = sorted(rng.sample(range(0, WINDOWS * 7), n), reverse=True)  # oldest first
    acts = [_activity(rng, i, k, anchor - timedelta(days=off), prof) for k, off in enumerate(offsets)]

    anomalies: dict[int, str] = {}
    classes = list(ACTIVITY_ANOMALY_CLASSES)
    for k in range(n):
        if rng.random() < ACTIVITY_ANOMALY_RATE:
            cls = rng.choice(classes)
            if cls == "extid_collision_other_athlete" and i == 0:
                cls = "hr_missing"
            if cls == "dup_resync" and offsets[k] < 7:  # no later sync to re-send in
                cls = "dup_in_payload"
            anomalies[k] = cls

    # Group into weekly windows. Window w covers offsets [7w, 7w+6]; sync day = anchor - 7w.
    by_window: dict[int, list[int]] = {}
    for k, off in enumerate(offsets):
        by_window.setdefault(off // 7, []).append(k)

    syncs: list[tuple[str, dict]] = []
    daily_anoms: dict[str, str] = {}
    expected_hrv: dict[str, float] = {}
    manual: list[dict] = []
    pending_resend: list[dict] = []
    for w in range(WINDOWS - 1, -1, -1):  # oldest window first
        today = anchor - timedelta(days=7 * w)
        today_s = today.isoformat()
        payload_acts: list[dict] = list(pending_resend)
        pending_resend = []
        hrv_entries: list[dict] = []
        for k in by_window.get(w, []):
            act = acts[k]
            cls = anomalies.get(k)
            rec = _inject_activity(act, cls, i, anchor) if cls else dict(act)
            payload_acts.append(rec)
            if cls == "dup_in_payload":
                payload_acts.append(dict(rec))
            elif cls == "dup_resync":
                pending_resend.append(dict(rec))
            elif cls == "manual_duplicate":
                manual.append(act)
            if act["date"] != today_s:
                v = round(prof["hrv"] * rng.uniform(0.8, 1.2), 1)
                hrv_entries.append({"date": act["date"], "rmssd": v})
        sleep = {
            "date": today_s,
            "resting_hr": prof["rhr"] + rng.randint(-3, 6),
            "sleep_score": rng.randint(45, 95),
            "total_sleep_hours": round(rng.uniform(5.0, 9.5), 2),
        }
        hrv_today = {"date": today_s, "rmssd": round(prof["hrv"] * rng.uniform(0.8, 1.2), 1)}
        weight = {"date": today_s, "weight_kg": round(prof["weight"] + rng.uniform(-1.5, 1.5), 1)}
        dcls = None
        if rng.random() < DAILY_ANOMALY_RATE:
            dcls = rng.choice(list(DAILY_ANOMALY_CLASSES))
            daily_anoms[today_s] = dcls
            _inject_daily(dcls, sleep, hrv_today, weight)
        if dcls is None or dcls not in ("hrv_zero", "hrv_extreme", "all_optional_missing"):
            expected_hrv[today_s] = hrv_today["rmssd"]
        for e in hrv_entries:
            expected_hrv[e["date"]] = e["rmssd"]
        payload = {
            "activities": payload_acts,
            "sleep": [] if dcls == "all_optional_missing" else [sleep],
            "hrv": hrv_entries + ([] if dcls == "all_optional_missing" else [hrv_today]),
            "weight": [] if dcls == "all_optional_missing" else [weight],
        }
        syncs.append((today_s, payload))
    return AthleteData(
        index=i, athlete_id=aid, activities=acts, syncs=syncs,
        activity_anomalies=anomalies, daily_anomalies=daily_anoms,
        expected_hrv=expected_hrv, manual_entries=manual, profile=prof,
    )


def raw_training_rows(seed: int, i: int, anchor: date) -> list[tuple]:
    """Clean training_log rows for the raw bulk-insert phases (no anomalies, no syncs)."""
    a = generate_athlete(seed, i, anchor)
    return [
        (a.athlete_id, r["date"], "EASY", r["distance_km"], r["duration_sec"], r["avg_hr"],
         r["max_hr"], None, r["estimated_training_load"], None, None, None, r["name"],
         "raw-" + r["activity_id"], None, float(r["avg_pace_sec_per_km"]))
        for r in a.activities
    ]


TRAINING_INSERT_SQL = (
    "INSERT OR IGNORE INTO training_log (athlete_id, date, session_type, distance_km, "
    "duration_sec, avg_hr, max_hr, rpe, training_load, shoe_id, surface, temperature_c, notes, "
    "garmin_activity_id, quality_flag, avg_pace_sec_per_km) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
