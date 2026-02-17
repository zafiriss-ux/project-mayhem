"""
Daily Coach - Main Orchestrator

Runs every morning to:
1. Sync Garmin data
2. Persist data to database (activities + daily metrics)
3. Check real recovery status (HRV, RHR, sleep from Garmin)
4. Fetch today's session from weekly plan
5. Calculate optimal running time
6. Generate nutrition plan
7. Send morning message via Telegram
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
from titan.core.database import DatabaseManager


def _safe_float(value, default: float = 0.0) -> float:
    """Convert value to float safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """Convert value to int safely."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class DailyCoach:
    """Daily coaching orchestrator with real data persistence."""

    def __init__(
        self,
        garmin_sync,
        weather_api,
        telegram_bot,
        hrv_engine,
        tsb_engine,
        readiness_engine,
        optimal_time_calc,
        nutrition_optimizer,
        weekly_planner,
        db: Optional[DatabaseManager] = None,
    ):
        self.garmin         = garmin_sync
        self.weather        = weather_api
        self.telegram       = telegram_bot
        self.hrv            = hrv_engine
        self.tsb            = tsb_engine
        self.readiness      = readiness_engine
        self.optimal_time   = optimal_time_calc
        self.nutrition      = nutrition_optimizer
        self.weekly_planner = weekly_planner
        # Database for persistent memory (CTL/ATL/TSB, RHR baselines, etc.)
        self.db = db or DatabaseManager()
        # Restore in-memory state of science engines from DB on startup
        self._hydrate_engines_from_db()

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════════

    def run_morning_routine(self) -> bool:
        """Execute complete morning coaching routine."""
        print(f"\n🌅 Running morning routine: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        # ── Step 1: Sync Garmin ──────────────────────────────────────────────
        print("📥 Syncing Garmin data...")
        garmin_data = self.garmin.sync_all()

        # ── Step 2: Persist to DB ────────────────────────────────────────────
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_rhr, today_sleep_score, today_sleep_hours = self._persist_garmin_data(
            garmin_data, today_str
        )

        # ── Step 3: Feed live HRV into engine ───────────────────────────────
        if garmin_data.get('hrv'):
            for entry in garmin_data['hrv']:
                self.hrv.add_hrv_measurement(entry['date'], entry['rmssd'])

        # ── Step 4: Real recovery analysis ──────────────────────────────────
        print("💊 Analyzing recovery status...")
        hrv_summary   = self.hrv.get_hrv_summary()
        tsb_value, tsb_status = self.tsb.calculate_tsb()

        latest_hrv   = _safe_float(hrv_summary.get('latest_hrv'), 0.0)
        baseline_hrv = _safe_float(hrv_summary.get('baseline'), 50.0)
        baseline_rhr = self._get_baseline_rhr(days=7)

        readiness = self.readiness.analyze_readiness(
            today_hrv    = latest_hrv,
            baseline_hrv = baseline_hrv,
            today_rhr    = today_rhr or 50,
            baseline_rhr = baseline_rhr,
            sleep_score  = today_sleep_score,   # real Garmin score 0-100
            soreness     = 3,                   # TODO: add morning check-in prompt
        )

        # ── Step 5: Today's planned session (from weekly plan) ───────────────
        print("📋 Fetching today's session from weekly plan...")
        today_session = self.weekly_planner.get_today_session()

        # ── Step 6: Feed activities into load engines ───────────────────────
        self._feed_load_engines(garmin_data.get('activities', []))

        # ── Step 7: Optimal time ─────────────────────────────────────────────
        print("⏰ Calculating optimal running time...")
        optimal_time = self.optimal_time.calculate_optimal_time(
            session_type  = today_session.get('session_type', 'EASY'),
            duration_hours= today_session.get('duration_min', 45) / 60.0,
            day_offset    = 0,
            tsb_value     = tsb_value,
        )

        # ── Step 8: Nutrition ────────────────────────────────────────────────
        print("🍽 Generating nutrition plan...")
        weight_trend   = self.nutrition.analyze_weight_trend()
        current_weight = weight_trend.get('current_weight', 75.0)

        # Push latest weight into nutrition optimizer if Garmin provided it
        if garmin_data.get('weight'):
            latest_w = garmin_data['weight'][-1]
            self.nutrition.add_weight_entry(latest_w['date'], latest_w['weight_kg'])
            current_weight = latest_w['weight_kg']

        nutrition_plan = self.nutrition.calculate_daily_nutrition(
            weight_kg    = current_weight,
            today_session= today_session,
        )

        # ── Step 9: Send Telegram message ────────────────────────────────────
        print("📱 Sending coaching message...")
        coaching_data = {
            'session_type'   : today_session.get('session_type', 'EASY'),
            'duration'       : f"{today_session.get('distance_km', '?')} km",
            'details'        : today_session.get('details', ''),
            'optimal_time'   : optimal_time.get('recommended_time', 'N/A'),
            'dew_point'      : optimal_time.get('dew_point', 'N/A'),
            'conditions'     : optimal_time.get('quality', 'N/A'),
            'hrv_status'     : hrv_summary.get('trend', 'N/A'),
            'hrv_value'      : round(latest_hrv, 1),
            'hrv_baseline'   : round(baseline_hrv, 1),
            'sleep_quality'  : today_sleep_score,
            'sleep_hours'    : round(today_sleep_hours, 1),
            'readiness_score': readiness.get('score', 'N/A'),
            'tsb'            : round(tsb_value, 1) if tsb_value else 0,
            'tsb_status'     : tsb_status,
            'nutrition_plan' : (
                f"{nutrition_plan.get('carbs_g', '?')}g carbs, "
                f"{nutrition_plan.get('protein_g', '?')}g protein"
            ),
        }

        success = self.telegram.send_daily_coaching(coaching_data)
        print(f"\n{'✅' if success else '❌'} Morning routine completed\n")
        return success

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _persist_garmin_data(
        self, garmin_data: Dict, today_str: str
    ):
        """
        Persist all synced Garmin data to the database.

        Returns:
            (today_rhr, today_sleep_score, today_sleep_hours)
        """
        today_rhr         = 0
        today_sleep_score = 75        # conservative default
        today_sleep_hours = 7.5

        # ── Activities → training_log ─────────────────────────────────────
        activities = garmin_data.get('activities', [])
        saved_count = 0
        for act in activities:
            try:
                self.db.save_session(
                    date        = act.get('date', today_str),
                    session_type= act.get('session_type', 'EASY'),
                    distance_km = _safe_float(act.get('distance_km', 0)),
                    duration_sec= _safe_int(act.get('duration_sec', 0)),
                    avg_hr      = _safe_int(act.get('avg_hr')) or None,
                    max_hr      = _safe_int(act.get('max_hr')) or None,
                    rpe         = act.get('rpe'),
                    notes       = act.get('name', ''),
                )
                saved_count += 1
            except Exception as e:
                print(f"  ⚠️  Could not save activity {act.get('date')}: {e}")
        if saved_count:
            print(f"  💾 Saved {saved_count} activities to database")

        # ── Sleep → extract RHR + sleep score ─────────────────────────────
        sleep_entries = garmin_data.get('sleep', [])
        for entry in sleep_entries:
            if not entry:
                continue
            # Garmin API returns nested dict; extract what we need safely
            rhr   = entry.get('restingHeartRate') or entry.get('rhr') or 0
            score = entry.get('sleepScores', {})
            if isinstance(score, dict):
                overall = score.get('overall', {})
                if isinstance(overall, dict):
                    s_val = overall.get('value', 0)
                else:
                    s_val = _safe_float(overall, 0)
            else:
                s_val = _safe_float(score, 0)

            dur_sec = entry.get('sleepTimeSeconds') or entry.get('duration_sec', 0)

            if rhr:
                today_rhr = _safe_int(rhr)
            if s_val:
                today_sleep_score = _safe_int(s_val)
            if dur_sec:
                today_sleep_hours = _safe_float(dur_sec) / 3600.0

        # ── HRV → daily_metrics ───────────────────────────────────────────
        hrv_entries = garmin_data.get('hrv', [])
        latest_rmssd = None
        for entry in hrv_entries:
            if entry.get('date') == today_str:
                latest_rmssd = _safe_float(entry.get('rmssd', 0)) or None
                break

        # ── Weight → daily_metrics ────────────────────────────────────────
        weight_entries = garmin_data.get('weight', [])
        latest_weight = None
        for entry in weight_entries:
            if entry.get('date') == today_str:
                latest_weight = _safe_float(entry.get('weight_kg', 0)) or None
                break

        # ── Persist today's metrics row ───────────────────────────────────
        try:
            self.db.save_daily_metric(
                date         = today_str,
                weight       = latest_weight,
                hrv          = latest_rmssd,
                rhr          = today_rhr or None,
                sleep_hours  = today_sleep_hours if today_sleep_hours > 0 else None,
                sleep_quality= today_sleep_score if today_sleep_score > 0 else None,
            )
            print(f"  💾 Daily metrics saved for {today_str}")
        except Exception as e:
            print(f"  ⚠️  Could not save daily metrics: {e}")

        return today_rhr, today_sleep_score, today_sleep_hours

    def _get_baseline_rhr(self, days: int = 7) -> float:
        """
        Calculate rolling N-day average resting HR from database.
        Falls back to 50 bpm if no history.
        """
        try:
            cursor = self.db.conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            cursor.execute(
                """
                SELECT AVG(resting_hr) FROM daily_metrics
                WHERE date >= ? AND resting_hr IS NOT NULL AND resting_hr > 0
                """,
                (cutoff,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return round(float(row[0]), 1)
        except Exception:
            pass
        return 50.0  # safe default

    def run_morning_routine_async(self) -> None:
        """
        Schedule `run_morning_routine` in a daemon thread so the Telegram
        polling thread is never blocked waiting for Garmin sync + calculations.
        """
        t = threading.Thread(
            target=self.run_morning_routine,
            name="DailyCoachRoutine",
            daemon=True,
        )
        t.start()

    def _feed_load_engines(self, activities: List[Dict]) -> None:
        """
        Feed synced activities into TSB / ACWR engines so CTL/ATL are live.
        Uses training_load from DB for the full 42-day window.
        """
        try:
            loads = self.db.get_training_load_history(days=42)
            if loads:
                self.tsb.load_history = loads  # expose for re-calc on next call
        except Exception as e:
            print(f"  ⚠️  Could not feed load engines: {e}")

    def _hydrate_engines_from_db(self) -> None:
        """
        Restore in-memory science engine state from the database on startup.

        Prevents 'Digital Amnesia' after restarts:
        - HRVGuidedEngine needs 7-14 days of rMSSD history for baseline
        - NutritionOptimizer needs weight history for trend analysis
        - TSBEngine needs 42-day load history for correct CTL/ATL

        Called automatically at end of __init__.
        """
        print("🧠 Hydrating AI memory from database...")
        cursor = self.db.conn.cursor()

        # 1. HRV history (last 14 days, oldest first so baseline builds correctly)
        try:
            cursor.execute(
                """SELECT date, hrv_rmssd FROM daily_metrics
                   WHERE hrv_rmssd IS NOT NULL AND hrv_rmssd > 0
                   ORDER BY date DESC LIMIT 14"""
            )
            rows = cursor.fetchall()
            for date_str, rmssd in reversed(rows):
                self.hrv.add_hrv_measurement(date_str, rmssd)
            print(f"  ↳ HRV: {len(rows)} records loaded")
        except Exception as e:
            print(f"  ⚠️  HRV hydration failed: {e}")

        # 2. Weight history (last 30 days, oldest first)
        try:
            cursor.execute(
                """SELECT date, weight_kg FROM daily_metrics
                   WHERE weight_kg IS NOT NULL AND weight_kg > 0
                   ORDER BY date DESC LIMIT 30"""
            )
            rows = cursor.fetchall()
            for date_str, weight in reversed(rows):
                self.nutrition.add_weight_entry(date_str, weight)
            print(f"  ↳ Weight: {len(rows)} records loaded")
        except Exception as e:
            print(f"  ⚠️  Weight hydration failed: {e}")

        # 3. Training load history → TSB engine (42-day window for CTL)
        try:
            loads = self.db.get_training_load_history(days=42)
            if loads:
                self.tsb.load_history = loads
            print(f"  ↳ Training load: {len(loads)} sessions loaded for CTL")
        except Exception as e:
            print(f"  ⚠️  TSB hydration failed: {e}")
