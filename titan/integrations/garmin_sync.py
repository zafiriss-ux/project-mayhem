"""
Garmin Connect Live API Integration

REAL implementation using garminconnect library (not mock).
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

from titan.utils.secrets import SecretStr

_log = logging.getLogger(__name__)


class GarminSync:
    """
    Live Garmin Connect API integration.
    Uses the 'garminconnect' library for real data.
    """

    def __init__(self, email: str = None, password: str = None):
        self._email_secret = SecretStr(email or os.getenv('GARMIN_EMAIL', ''))
        self._password_secret = SecretStr(password or os.getenv('GARMIN_PASSWORD', ''))
        self.client = None
        self.is_connected = False
        self.last_sync: Optional[str] = None
        self.sync_history: List = []
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_sync = False

    # ------------------------------------------------------------------ #
    # CONNECTION
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        email = self._email_secret.get_secret_value()
        password = self._password_secret.get_secret_value()
        if not email or not password:
            print("⚠️  Garmin credentials missing – run setup first.")
            return False
        try:
            from garminconnect import Garmin
            self.client = Garmin(email, password)
            self.client.login()
            self.is_connected = True
            print("✅ Connected to Garmin Connect")
            return True
        except Exception as e:
            _log.debug("Garmin connection failed", exc_info=True)
            err = str(e)
            if any(k in err for k in ("OAuth", "token", "401", "403", "Unauthorized")):
                print(
                    "❌ Garmin token expired. Clear cached tokens and retry:\n"
                    "   rm -rf ~/.garth"
                )
            else:
                print("❌ Garmin connection failed (check logs for details)")
            self.is_connected = False
            return False

    def _ensure_connected(self) -> bool:
        if not self.is_connected or self.client is None:
            return self.connect()
        return True

    # ------------------------------------------------------------------ #
    # ACTIVITIES
    # ------------------------------------------------------------------ #
    def sync_activities(self, days_back: int = 7) -> List[Dict]:
        if not self._ensure_connected():
            return []
        activities = []
        skipped_records = 0
        try:
            start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")
            raw = self.client.get_activities_by_date(start, end, "running")
            for a in raw:
                try:
                    dur_sec = int(a.get("duration", 0))
                    dist_m  = float(a.get("distance", 0))
                    avg_hr  = a.get("averageHR") or a.get("averageHeartRate", 0)
                    max_hr  = a.get("maxHR") or a.get("maxHeartRate", 0)
                    pace_sec = int(dur_sec / (dist_m / 1000)) if dist_m > 0 else 0
                    activities.append({
                        "date":            a.get("startTimeLocal", "")[:10],
                        "activity_type":   a.get("activityType", {}).get("typeKey", "running"),
                        "distance_km":     round(dist_m / 1000, 2),
                        "duration_sec":    dur_sec,
                        "avg_hr":          int(avg_hr) if avg_hr else 0,
                        "max_hr":          int(max_hr) if max_hr else 0,
                        "avg_pace_sec_per_km": pace_sec,
                        "calories":        int(a.get("calories", 0)),
                        "elevation_gain_m": int(a.get("elevationGain", 0)),
                        "activity_id":     a.get("activityId"),
                    })
                except Exception as e:
                    skipped_records += 1
                    activity_id = a.get("activityId", "unknown")
                    print(f"⚠️  Skipping malformed activity ({activity_id}): {e}")
                    continue
            print(f"📥 Synced {len(activities)} activities")
            if skipped_records:
                print(f"⚠️  Skipped {skipped_records} malformed activity record(s)")
            self._log_sync("activities", len(activities))
        except Exception as e:
            print(f"❌ Activity sync failed: {e}")
        return activities

    # ------------------------------------------------------------------ #
    # WEIGHT
    # ------------------------------------------------------------------ #
    def sync_weight(self, days_back: int = 30) -> List[Dict]:
        if not self._ensure_connected():
            return []
        entries = []
        try:
            start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")
            raw = self.client.get_weigh_ins(start, end)
            daily = raw.get("dailyWeightSummaries", [])
            for d in daily:
                summ = d.get("allDayWeightSummaries", [{}])[0]
                w_g = summ.get("latestWeight", summ.get("minWeight", 0))
                if w_g and w_g > 0:
                    entries.append({
                        "date":       d.get("calendarDate", ""),
                        "weight_kg":  round(w_g / 1000, 2),  # grams → kg
                        "bmi":        summ.get("bmi"),
                        "source":     "garmin",
                    })
            print(f"⚖️  Synced {len(entries)} weight entries")
            self._log_sync("weight", len(entries))
        except Exception as e:
            print(f"❌ Weight sync failed: {e}")
        return entries

    # ------------------------------------------------------------------ #
    # SLEEP
    # ------------------------------------------------------------------ #
    def sync_sleep(self, days_back: int = 7) -> List[Dict]:
        if not self._ensure_connected():
            return []
        sessions = []
        try:
            for i in range(days_back):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                raw = self.client.get_sleep_data(d)
                summary = raw.get("dailySleepDTO", {})
                if summary.get("sleepTimeSeconds"):
                    total_h = summary["sleepTimeSeconds"] / 3600
                    deep_h  = summary.get("deepSleepSeconds", 0) / 3600
                    rem_h   = summary.get("remSleepSeconds", 0) / 3600
                    sessions.append({
                        "date":               d,
                        "total_sleep_hours":  round(total_h, 2),
                        "deep_sleep_hours":   round(deep_h, 2),
                        "rem_sleep_hours":    round(rem_h, 2),
                        "sleep_score":        summary.get("sleepScores", {}).get("overall", {}).get("value"),
                    })
        except Exception as e:
            print(f"❌ Sleep sync failed: {e}")
        print(f"😴 Synced {len(sessions)} sleep sessions")
        self._log_sync("sleep", len(sessions))
        return sessions

    # ------------------------------------------------------------------ #
    # HRV
    # ------------------------------------------------------------------ #
    def sync_hrv(self, days_back: int = 7) -> List[Dict]:
        if not self._ensure_connected():
            return []
        hrv_data = []
        try:
            for i in range(days_back):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    raw = self.client.get_hrv_data(d)
                    summary = raw.get("hrvSummary", {})
                    rmssd = summary.get("lastNight5MinHigh") or summary.get("weeklyAvg")
                    if rmssd:
                        hrv_data.append({
                            "date":   d,
                            "rmssd":  round(float(rmssd), 1),
                            "status": summary.get("status", ""),
                            "source": "garmin",
                        })
                except Exception:
                    pass
        except Exception as e:
            print(f"❌ HRV sync failed: {e}")
        print(f"💓 Synced {len(hrv_data)} HRV measurements")
        self._log_sync("hrv", len(hrv_data))
        return hrv_data

    # ------------------------------------------------------------------ #
    # FULL SYNC
    # ------------------------------------------------------------------ #
    def sync_all(self, days_back: int = 7) -> Dict[str, List]:
        print("🔄 Full Garmin sync starting...")
        self.last_sync = datetime.now().isoformat()
        return {
            "activities": self.sync_activities(days_back),
            "weight":     self.sync_weight(max(days_back, 14)),
            "sleep":      self.sync_sleep(days_back),
            "hrv":        self.sync_hrv(days_back),
        }

    # ------------------------------------------------------------------ #
    # BACKGROUND THREAD
    # ------------------------------------------------------------------ #
    def start_background_sync(self, interval_hours: int = 6):
        if self._sync_thread and self._sync_thread.is_alive():
            return
        self._stop_sync = False
        self._sync_thread = threading.Thread(
            target=self._bg_worker, args=(interval_hours,), daemon=True, name="GarminSync"
        )
        self._sync_thread.start()
        print(f"✅ Garmin background sync started (every {interval_hours}h)")

    def stop_background_sync(self):
        self._stop_sync = True

    def _bg_worker(self, interval_hours: int):
        while not self._stop_sync:
            try:
                self.sync_all()
            except Exception as e:
                print(f"❌ BG sync error: {e}")
            for _ in range(interval_hours * 3600):
                if self._stop_sync:
                    return
                time.sleep(1)

    def _log_sync(self, data_type: str, count: int):
        self.sync_history.append((data_type, datetime.now().isoformat(), count))
        if len(self.sync_history) > 100:
            self.sync_history = self.sync_history[-100:]

    def get_sync_summary(self) -> Dict:
        return {
            "last_sync":      self.last_sync,
            "total_syncs":    len(self.sync_history),
            "is_connected":   self.is_connected,
            "recent_syncs":   self.sync_history[-5:],
        }
