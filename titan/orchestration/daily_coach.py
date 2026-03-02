"""
Daily Coach - Main Orchestrator (v5.7 Closed-Loop Sovereign)

Orchestration order:
1.  Sync Garmin data
2.  Persist data to database (activities + daily metrics)
3.  HRV + HRR live update
4.  AFI computation (autonomic fusion)
5.  CS thermal adjustment (kinetic layer)
6.  Glycogen debt update (metabolic layer)
7.  Composite readiness (AFI + TSB + glycogen)
8.  Today's planned session (weekly plan)
9.  Governance hard gates  ← LAST before Telegram
10. Optimal running time
11. Nutrition plan
12. Send morning message via Telegram (LLM explains, kernel decides)

Architectural Boundary:
  The LLM (Telegram message) receives ONLY processed results.
  It never computes readiness, intensity zones, or session type.
  governance.apply_constraints() is the final, non-bypassable gate.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
import threading
from titan.core.database import DatabaseManager
from titan.science.autonomic_engine import AutonomicFusionEngine
from titan.science.critical_speed import CriticalSpeedTracker
from titan.science.glycogen_model import GlycogenDebtAccumulator
from titan.science.governance_engine import GovernanceEngine
from titan.science.intensity_governor import IntensityGovernor

from titan.science.fatigue_engine import FatigueEngine





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
        # v5.7 Closed-Loop engines (optional — auto-instantiated if None)
        autonomic_engine: Optional[AutonomicFusionEngine] = None,
        cs_tracker:       Optional[CriticalSpeedTracker]  = None,
        glycogen_accum:   Optional[GlycogenDebtAccumulator] = None,
        governance:       Optional[GovernanceEngine]      = None,
        fatigue_engine:    Optional[FatigueEngine]         = None,
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
        # v5.7: Closed-Loop science engines
        self.autonomic  = autonomic_engine or AutonomicFusionEngine()
        self.cs_tracker = cs_tracker       or CriticalSpeedTracker()
        self.glycogen   = glycogen_accum   or GlycogenDebtAccumulator()
        self.governance = governance       or GovernanceEngine()
        self.fatigue    = fatigue_engine    or FatigueEngine()
        # Restore in-memory state of science engines from DB on startup
        self._hydrate_engines_from_db()

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════════

    def run_morning_routine(
        self,
        soreness: Optional[int] = None,
        subjective_fatigue_score: Optional[int] = None,
    ) -> bool:
        """Execute complete morning coaching routine."""
        # Morning check-in: collect subjective soreness/fatigue (0-10 scale)
        if soreness is None:
            try:
                raw = input("Morning check-in — Soreness / fatigue (0-10, Enter=5): ").strip()
                soreness = int(raw) if raw else 5
                soreness = max(0, min(10, soreness))
            except (EOFError, ValueError):
                soreness = 5  # neutral default for non-interactive runs

        if subjective_fatigue_score is None:
            if soreness is not None:
                subjective_fatigue_score = int(soreness)
            else:
                try:
                    raw_subj = input("Morning check-in — Subjective fatigue (0-10, Enter=5): ").strip()
                    subjective_fatigue_score = int(raw_subj) if raw_subj else 5
                except (EOFError, ValueError):
                    subjective_fatigue_score = 5
        subjective_fatigue_score = max(0, min(10, int(subjective_fatigue_score)))

        print(f"\n🌅 Running morning routine: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        # ── Step 1: Sync Garmin ──────────────────────────────────────────────
        print("📥 Syncing Garmin data...")
        garmin_data = self.garmin.sync_all()

        # ── Step 2: Persist to DB ────────────────────────────────────────────
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_rhr, today_sleep_score, today_sleep_hours = self._persist_garmin_data(
            garmin_data, today_str
        )

        # ── Step 3: Feed live HRV + HRR into engines ────────────────────────
        if garmin_data.get('hrv'):
            for entry in garmin_data['hrv']:
                self.hrv.add_hrv_measurement(entry['date'], entry['rmssd'])
        if garmin_data.get('hrr'):
            for entry in garmin_data['hrr']:
                hrr60  = _safe_int(entry.get('hrr_60', 0)) or None
                hrr120 = _safe_int(entry.get('hrr_120', 0))
                if hrr60:
                    self.autonomic.add_hrr(entry['date'], hrr60, hrr120)
                    self.db.save_hrr(entry['date'], hrr60, hrr120)

        # ── Step 4: AFI — Autonomic Fusion Index ────────────────────────────
        print("🧬 Computing Autonomic Fusion Index...")
        ln_dev   = self.hrv.calculate_ln_rmssd_deviation(short_days=7, long_days=28)
        hrv_summary   = self.hrv.get_hrv_summary()
        latest_hrv   = _safe_float(hrv_summary.get('latest_hrv'), 0.0)
        baseline_hrv = _safe_float(hrv_summary.get('baseline'), 50.0)
        hrv_pct_above = ((latest_hrv - baseline_hrv) / baseline_hrv * 100) if baseline_hrv else 0.0
        today_hrr60  = (self.autonomic.hrr_log[-1][1] if self.autonomic.hrr_log else None)

        # Sleep depth delta: map Garmin sleep score to -1..+1 (70 = baseline)
        sleep_delta = max(-1.0, min(1.0, (today_sleep_score - 70) / 30))
        afi_raw  = self.autonomic.calculate_afi(
            ln_rmssd_deviation = ln_dev,
            hrr_60_today       = today_hrr60,
            sleep_depth_delta  = sleep_delta,
        )
        afi_final = self.autonomic.apply_48h_buffer(afi_raw)
        afi_constraints = self.autonomic.get_readiness_constraints(
            afi_final, hrv_pct_above, today_hrr60
        )
        print(f"  ↳ AFI: {afi_final:+.3f} | archetype: {self.cs_tracker.archetype}")

        # ── Step 5: TSB + kinetic state ──────────────────────────────────────
        tsb_value, tsb_status = self.tsb.calculate_tsb()
        today_temp = garmin_data.get('temperature_c') or 20.0
        cs_thermal = self.cs_tracker.apply_thermal(today_temp)

        # ── Step 6: Glycogen debt update ─────────────────────────────────────
        recent_trimp = self._get_recent_trimp(garmin_data.get('activities', []))
        if recent_trimp > 0:
            self.glycogen.update(
                date               = today_str,
                trimp              = recent_trimp,
                time_above_lt2_min = garmin_data.get('time_above_lt2_min', 0),
                dprime_fraction    = garmin_data.get('dprime_fraction', 0.0),
                intra_carb_g       = garmin_data.get('intra_carb_g', 0.0),
                weight_kg          = garmin_data.get('weight_kg', 70.0),
            )
        self.glycogen.overnight_resynthesis(
            sleep_hours       = today_sleep_hours,
            carb_availability = 'MODERATE',
        )
        self.db.update_glycogen_debt(today_str, self.glycogen.daily_debt)

        # ── Step 7: Composite readiness ──────────────────────────────────────
        print("💊 Analyzing recovery status...")
        baseline_rhr = self._get_baseline_rhr(days=7)
        readiness = self.readiness.analyze_readiness(
            today_hrv    = latest_hrv,
            baseline_hrv = baseline_hrv,
            today_rhr    = today_rhr or 50,
            baseline_rhr = baseline_rhr,
            sleep_score  = today_sleep_score,
            soreness     = soreness,
        )
        # Apply AFI modifier to readiness score
        readiness['score'] = max(0, min(100,
            readiness.get('score', 50) + afi_constraints.get('afi_modifier', 0)
        ))
        # Apply clamp if parasympathetic guard triggered
        readiness['score'] = min(readiness['score'], afi_constraints.get('readiness_clamp', 100))




        fatigue_level, fatigue_tags = self.fatigue.classify_fatigue(
            hr_suppression=bool(garmin_data.get('hr_suppression', False)),
            rpe_mismatch=bool(garmin_data.get('rpe_mismatch', False)),
            pace_hr_divergence=bool(garmin_data.get('pace_hr_divergence', False)),
            soreness=subjective_fatigue_score,
        )




        # ── Step 7.5: Intensity governor (graduated YELLOW/RED gate) ─────────
        ig = IntensityGovernor()

        # ── Step 8: Today's planned session (from weekly plan) ───────────────
        print("📋 Fetching today's session from weekly plan...")
        today_session = self.weekly_planner.get_today_session()

        intensity_gate = ig.evaluate({
            'drift_pct': garmin_data.get('drift_pct', 0.0),
            'glycogen_debt': self.glycogen.daily_debt,

            'fatigue_level': fatigue_level,

            'acwr': garmin_data.get('acwr', 1.0),
            'readiness_score': readiness.get('score', 50),
            'planned_session': today_session.get('session_type', 'EASY'),
            'planned_volume_pct': today_session.get('volume_pct', 1.0),
        })

        # ── Step 9: Feed activities into load engines ─────────────────────
        self._feed_load_engines(garmin_data.get('activities', []))

        # ── Step 9b: Governance hard gates ──────────────────────────────────
        print("🔒 Applying governance constraints...")
        today_session = self.governance.apply_constraints(
            session_plan = today_session,
            context      = {
                'db':                  self.db,
                'cs_tracker':          self.cs_tracker,
                'afi_constraints':     afi_constraints,
                'intensity_gate_result': intensity_gate,
                'readiness_score':     readiness.get('score', 50),
                'glycogen_debt':       self.glycogen.daily_debt,

                'fatigue_level':       fatigue_level,

                'acwr':                garmin_data.get('acwr', 1.0),
                'days_since_last_vo2': garmin_data.get('days_since_last_vo2'),
                'fueling_confirmed':   bool(garmin_data.get('fueling_confirmed', False)),
                'planned_duration_min': today_session.get('duration_min', 45),



                'today_hrv':          latest_hrv,
                'baseline_hrv':       baseline_hrv,
                'hrv_std_dev':        _safe_float(hrv_summary.get('std_dev'), 0.0),
                'today_rhr':          today_rhr or 50,
                'baseline_rhr':       baseline_rhr,
                'sleep_score':        today_sleep_score,
                'subjective_fatigue_score': subjective_fatigue_score,
                'tsb_value':          tsb_value,
                'injury_flag':        bool(garmin_data.get('injury_flag', False)),



            },
        )
        if today_session.get('governance_locks_applied'):
            print(f"  ↳ Locks: {', '.join(today_session['governance_locks_applied'])}")

        self._ensure_vo2_eligibility_contract(today_session)

        # ── Step 10: Optimal time ────────────────────────────────────────────
        print("⏰ Calculating optimal running time...")
        optimal_time = self.optimal_time.calculate_optimal_time(
            session_type  = today_session.get('session_type', 'EASY'),
            duration_hours= today_session.get('duration_min', 45) / 60.0,
            day_offset    = 0,
            tsb_value     = tsb_value,
        )

        # ── Step 11: Nutrition ───────────────────────────────────────────────
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

        # ── Step 12: Send Telegram message (LLM explains, kernel decided) ────
        print("📱 Sending coaching message...")
        # Glycogen / electrolyte advisory
        glycogen_protocol   = self.glycogen.norwegian_protocol(current_weight)
        electrolyte_alert   = GlycogenDebtAccumulator.electrolyte_guard(
            dew_point_c  = _safe_float(optimal_time.get('dew_point'), 15.0),
            duration_min = today_session.get('duration_min', 45),
            session_type = today_session.get('session_type', 'EASY'),
        )
        governance_report = self.governance.get_governance_report(
            db=self.db, cs_tracker=self.cs_tracker, afi_constraints=afi_constraints
        )

        coaching_data = {
            # Session (post-governance)
            'session_type'      : today_session.get('session_type', 'EASY'),
            'duration'          : f"{today_session.get('distance_km', '?')} km",
            'details'           : today_session.get('details', ''),
            'governance_locks'  : today_session.get('governance_locks_applied', []),
            # Timing
            'optimal_time'      : optimal_time.get('recommended_time', 'N/A'),
            'dew_point'         : optimal_time.get('dew_point', 'N/A'),
            'conditions'        : optimal_time.get('quality', 'N/A'),
            # Autonomic / HRV
            'hrv_status'        : hrv_summary.get('trend', 'N/A'),
            'hrv_value'         : round(latest_hrv, 1),
            'hrv_baseline'      : round(baseline_hrv, 1),
            'afi'               : afi_final,
            # Sleep
            'sleep_quality'     : today_sleep_score,
            'sleep_hours'       : round(today_sleep_hours, 1),
            # Readiness (AFI-adjusted)
            'readiness_score'   : readiness.get('score', 'N/A'),
            'subjective_fatigue_score': subjective_fatigue_score,
            'fatigue_level': fatigue_level,
            'fatigue_tags': fatigue_tags,
            # TSB / kinetic
            'tsb'               : round(tsb_value, 1) if tsb_value is not None else 0,
            'tsb_status'        : tsb_status,
            'cs_smoothed'       : round(self.cs_tracker.cs_smoothed, 3) if self.cs_tracker.cs_smoothed else None,
            'cs_thermal'        : round(cs_thermal, 3) if cs_thermal else None,
            'archetype'         : self.cs_tracker.archetype,
            # Metabolic
            'glycogen_debt'     : round(self.glycogen.daily_debt, 1),
            'glycogen_status'   : self.glycogen.status,
            'glycogen_protocol' : glycogen_protocol,
            'electrolyte_alert' : electrolyte_alert,
            # Nutrition
            'nutrition_plan'    : (
                f"{nutrition_plan.get('carbs_g', '?')}g carbs, "
                f"{nutrition_plan.get('protein_g', '?')}g protein"
            ),
            # Governance report (for LLM narrative only)
            'governance_report' : governance_report,
            'intensity_gate_result': today_session.get('intensity_gate_result'),
            'fueling_gate': today_session.get('fueling_gate'),
            'vo2_eligibility': today_session.get('vo2_eligibility'),
        }

        success = self.telegram.send_daily_coaching(coaching_data)
        print(f"\n{'✅' if success else '❌'} Morning routine completed\n")
        return success

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ensure_vo2_eligibility_contract(session_plan: Dict) -> None:
        """Normalize VO2 gate payload shape for downstream consumers."""
        vo2 = session_plan.get('vo2_eligibility')
        if not isinstance(vo2, dict):
            return

        failed = vo2.get('failed_conditions', [])
        if not isinstance(failed, list):
            failed = [str(failed)] if failed else []
        vo2['failed_conditions'] = [str(code) for code in failed]

        details = vo2.get('detailed_failed_conditions', [])
        if not isinstance(details, list):
            details = []
        normalized = [d for d in details if isinstance(d, dict) and 'code' in d]
        vo2['detailed_failed_conditions'] = normalized

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

    def _prompt_soreness(self, default: int = 3) -> int:
        """
        Prompt the user for their current muscle soreness level.

        Accepts a value from 1 (none) to 10 (extreme).  Falls back to
        *default* if the session is non-interactive or the input is invalid.

        Non-blocking in automated contexts (background threads, Telegram
        callbacks): when stdin is not a TTY the default is returned immediately
        without calling input(), so the morning routine is never blocked.
        """
        if not sys.stdin.isatty():
            return default
        try:
            raw = input("🤸 Morning check-in — Muscle soreness (1–10, Enter to skip): ").strip()
            if not raw:
                return default
            value = int(raw)
            if 1 <= value <= 10:
                return value
            print(f"  ⚠️  Soreness must be 1–10; using default ({default})")
        except (EOFError, ValueError):
            pass
        return default

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

    def _get_recent_trimp(self, activities: List[Dict]) -> float:
        """
        Extract TRIMP from synced activities for glycogen debt update.
        Falls back to sRPE-based estimate if no Garmin TRIMP available.
        """
        total = 0.0
        for act in activities:
            trimp = _safe_float(act.get('trimp', 0))
            if trimp > 0:
                total += trimp
            else:
                # Fallback: use training_load (sRPE proxy)
                total += _safe_float(act.get('training_load', 0)) * 0.6
        return round(total, 1)

    def _feed_load_engines(self, activities: List[Dict]) -> None:
        """
        Refresh TSBEngine from DB after Garmin sync. Clears and reloads 42-day window.
        Uses training_load from DB so CTL/ATL are always current.
        """
        try:
            loads = self.db.get_training_load_history(days=42)
            self.tsb.daily_loads.clear()
            for date_str, load in reversed(loads):  # oldest-first for correct EMA
                self.tsb.add_daily_load(date_str, float(load))
            print(f"  ↳ Load engines refreshed: {len(loads)} sessions")
        except Exception as e:
            print(f"  ⚠️  Could not refresh load engines: {e}")

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
            self.hrv.hrv_log.clear()
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
            self.tsb.daily_loads.clear()
            # DB returns DESC; add oldest-first so EMA builds chronologically
            for date_str, load in reversed(loads):
                self.tsb.add_daily_load(date_str, float(load))
            print(f"  ↳ Training load: {len(loads)} sessions loaded for CTL")
        except Exception as e:
            print(f"  ⚠️  TSB hydration failed: {e}")

        # 4. HRR history → Autonomic engine (28-day rolling baseline)
        try:
            hrr_rows = self.db.get_hrr_history(days=28)
            for date_str, hrr_60, hrr_120 in reversed(hrr_rows):
                self.autonomic.add_hrr(date_str, hrr_60, hrr_120 or 0)
            print(f"  ↳ HRR: {len(hrr_rows)} records loaded for AFI baseline")
        except Exception as e:
            print(f"  ⚠️  HRR hydration failed: {e}")

        # 5. CS performances → CriticalSpeedTracker
        try:
            from titan.science.critical_speed import CriticalSpeedEngine
            perfs = self.db.get_cs_performances(limit=10)
            if len(perfs) >= 2:
                dist_time = [(dist, t) for _, dist, t in perfs]
                cs_raw, d_prime = CriticalSpeedEngine.estimate_cs_and_dprime(dist_time)
                if cs_raw and d_prime:
                    latest_date = perfs[0][0]
                    self.cs_tracker.update(latest_date, cs_raw, d_prime)
            print(f"  ↳ CS model: {len(perfs)} performances | "
                  f"confidence={self.cs_tracker.confidence:.0%} | "
                  f"archetype={self.cs_tracker.archetype}")
        except Exception as e:
            print(f"  ⚠️  CS hydration failed: {e}")
