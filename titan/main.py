#!/usr/bin/env python3
"""
TITAN v51 – AI Training Intelligence System
Main Application Entry Point

Flow:
  1. Setup wizard (first run) – collects credentials
  2. Initialize all engines
  3. Register Telegram command callbacks
  4. Start background threads (Garmin, Weather, Telegram)
  5. Schedule automated tasks (morning coaching, weekly plan)
  6. Launch interactive main menu
"""

import logging
import os
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

# Add project root to path so `titan` package resolves correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Credentials (must happen before anything reads env vars) ────────────────
# ── Core (database) ───────────────────────────────────────────────────────────
from titan.core.database import DatabaseManager
from titan.features.nutrition_optimizer import NutritionOptimizer
from titan.features.optimal_time_calculator import OptimalTimeCalculator

# ── Feature modules ──────────────────────────────────────────────────────────
from titan.features.weekly_planner import WeeklyPlanGenerator

# ── Core integrations ────────────────────────────────────────────────────────
from titan.integrations.garmin_sync import GarminSync
from titan.integrations.telegram_bot import TitanTelegramBot
from titan.orchestration.contracts import AthleteProfile, TitanContext, TitanContextContract

# ── Orchestration ────────────────────────────────────────────────────────────
from titan.orchestration.daily_coach import DailyCoach
from titan.science.acwr_engine import ACWREngine
from titan.science.adaptive_memory import AdaptiveMemory
from titan.science.biomechanics import BiomechanicsAnalysis
from titan.science.critical_speed import CriticalSpeedEngine
from titan.science.drift_engine import DriftEngine
from titan.science.durability_engine import DurabilityEngine
from titan.science.efficiency_engine import EfficiencyEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.glycogen_model import GlycogenModel

# ── Science engines ──────────────────────────────────────────────────────────
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.lactate_logic import LactateLogic
from titan.science.rcp_engine import RCPEngine
from titan.science.readiness_engine import ReadinessEngine
from titan.science.trimp_engine import TRIMPEngine
from titan.science.tsb_engine import TSBEngine

# ── UI ───────────────────────────────────────────────────────────────────────
from titan.ui.menu_system import main_menu
from titan.ui.setup_wizard import ensure_credentials

log = logging.getLogger(__name__)

LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def _configure_rotating_logging() -> None:
    """Attach a rotating file handler to the TITAN logger tree."""
    root = logging.getLogger()
    log_path = os.getenv("TITAN_LOG_PATH", "titan.log")
    if any(isinstance(h, RotatingFileHandler) and h.baseFilename.endswith(log_path) for h in root.handlers):
        return
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)



# ════════════════════════════════════════════════════════════════════════════
# BANNER
# ════════════════════════════════════════════════════════════════════════════
def _print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                       TITAN v51.0                            ║
║           AI-Powered Training Intelligence System            ║
║                                                              ║
║  🏃 Weekly Planning   |  ⏰ Optimal Timing                   ║
║  💊 Recovery (HRV/TSB)|  🍽  Nutrition (Burke/Jeukendrup)   ║
║  📱 Telegram Coaching |  📊 Live Garmin Sync                 ║
║  👟 Shoe Selector     |  📈 Cardiac Drift Analysis           ║
╚══════════════════════════════════════════════════════════════╝
    """)


# ════════════════════════════════════════════════════════════════════════════
# TELEGRAM COMMAND CALLBACKS
# ════════════════════════════════════════════════════════════════════════════
def _register_telegram_callbacks(telegram: TitanTelegramBot, ctx: TitanContext):
    """Wire engine methods to Telegram slash commands."""

    def _format_calibration_summary(summary: dict) -> str:
        status = summary.get("status", "UNKNOWN")
        if status == "NO_OUTCOMES_YET":
            return (
                "🧪 *CALIBRATION*\n"
                f"• Decisions logged: {summary.get('n_decisions', 0)}\n"
                "• Outcomes paired: 0\n"
                "• Status: NO_OUTCOMES_YET\n"
                f"• Note: {summary.get('note', 'No calibration data yet.')}"
            )

        phase_rates = summary.get("lock_rate_by_phase", {})
        if phase_rates:
            phase_lines = "\n".join(
                f"  • {phase}: {round(rate * 100, 1)}%"
                for phase, rate in sorted(phase_rates.items())
            )
        else:
            phase_lines = "  • N/A"

        lock_corr = summary.get("lock_outcome_correlation", {})
        if lock_corr:
            corr_lines = "\n".join(
                f"  • {lock}: Δcompletion {metrics.get('completion_delta_pp', 0)}pp "
                f"({metrics.get('n_with_lock', 0)} vs {metrics.get('n_without_lock', 0)} sessions)"
                for lock, metrics in sorted(lock_corr.items())
            )
        else:
            corr_lines = "  • N/A (need >=3 with-lock and >=3 without-lock samples per trigger)"

        promotion_candidates = summary.get("heuristic_promotion_candidates", [])
        if promotion_candidates:
            candidate_lines = "\n".join(
                f"  • {c.get('parameter')}: {c.get('completion_delta_pp')}pp "
                f"({c.get('n_with_lock')} vs {c.get('n_without_lock')} sessions, via {c.get('trigger_lock')})"
                for c in promotion_candidates
            )
        else:
            candidate_lines = "  • None yet (need confirmed lock/outcome signal on HEURISTIC thresholds)"

        moderate_candidates = summary.get("moderate_promotion_candidates", [])
        if moderate_candidates:
            moderate_lines = "\n".join(
                f"  • {c.get('parameter')}: {c.get('completion_delta_pp')}pp "
                f"({c.get('n_with_lock')} vs {c.get('n_without_lock')} sessions, "
                f"{c.get('phase_replication_count')} phases / {c.get('profile_replication_count', 1)} profiles, via {c.get('trigger_lock')})"
                for c in moderate_candidates
            )
        else:
            moderate_lines = (
                "  • None yet (need replicated lock/outcome signal across profiles and phases for MODERATE thresholds)"
            )

        return (
            "🧪 *CALIBRATION*\n"
            f"• Status: {status}\n"
            f"• Decisions logged: {summary.get('n_decisions', 0)}\n"
            f"• Outcomes paired: {summary.get('n_with_outcome', 0)}\n"
            f"• Completion rate: {round(summary.get('completion_rate', 0) * 100, 1)}%\n"
            f"• Governance lock rate: {round(summary.get('governance_lock_rate', 0) * 100, 1)}%\n"
            f"• Athlete override rate: {round(summary.get('athlete_override_rate', 0) * 100, 1)}%\n"
            f"• Avg RPE (completed): {summary.get('avg_rpe_when_completed', 'N/A')}\n"
            "• Lock rate by phase:\n"
            f"{phase_lines}\n"
            "• Lock/outcome correlation:\n"
            f"{corr_lines}\n"
            "• HEURISTIC→MODERATE candidates:\n"
            f"{candidate_lines}\n"
            "• MODERATE→STRONG candidates:\n"
            f"{moderate_lines}\n"
            f"• Note: {summary.get('calibration_note', 'No calibration note available.')}"
        )

    def cb_today():
        coach: DailyCoach = ctx["daily_coach"]
        try:
            coach.run_morning_routine()
            return "✅ Σημερινό coaching στάλθηκε!"
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_week():
        planner: WeeklyPlanGenerator = ctx["weekly_planner"]
        athlete = ctx.get("athlete_profile", {})
        try:
            plan = planner.generate_weekly_plan(
                athlete_profile=athlete,
                phase=athlete.get("phase", "BUILD")
            )
            ctx["last_weekly_plan"] = plan
            telegram.send_weekly_plan(plan)
            return "✅ Εβδομαδιαίο πλάνο στάλθηκε!"
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_stats():
        hrv: HRVGuidedEngine = ctx["hrv_engine"]
        tsb: TSBEngine = ctx["tsb_engine"]
        try:
            hrv_s = hrv.get_hrv_summary()
            tsb_val, tsb_status = tsb.calculate_tsb()
            return (
                f"📊 *STATS*\n"
                f"• HRV baseline: {hrv_s.get('baseline', 'N/A')}\n"
                f"• HRV trend: {hrv_s.get('trend', 'N/A')}\n"
                f"• TSB: {round(tsb_val, 1)} ({tsb_status})\n"
                f"• CTL (fitness): {round(tsb.ctl, 1)}\n"
                f"• ATL (fatigue): {round(tsb.atl, 1)}"
            )
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_recovery():
        hrv: HRVGuidedEngine = ctx["hrv_engine"]
        readiness: ReadinessEngine = ctx["readiness_engine"]
        try:
            hrv_s = hrv.get_hrv_summary()
            latest = hrv_s.get("latest_hrv", 0)
            baseline = hrv_s.get("baseline", 50)
            rec = readiness.analyze_readiness(
                today_hrv=latest, baseline_hrv=baseline,
                today_rhr=50, baseline_rhr=48,
                sleep_score=8, soreness=3
            )
            return (
                f"💊 *RECOVERY*\n"
                f"• Readiness score: {rec.get('score', 'N/A')}/100\n"
                f"• Status: {rec.get('status', 'N/A')}\n"
                f"• HRV: {latest} (baseline {baseline})\n"
                f"• Recommendation: {rec.get('recommendation', 'N/A')}"
            )
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_nutrition():
        nutrition: NutritionOptimizer = ctx["nutrition_optimizer"]
        opt_calc: OptimalTimeCalculator = ctx["optimal_time_calc"]
        try:
            trend = nutrition.analyze_weight_trend()
            weight = trend.get("current_weight", 75.0)
            optimal = opt_calc.calculate_optimal_time(
                session_type="EASY", duration_hours=1.0, day_offset=0
            )
            run_time = optimal.get("recommended_time", "07:00")
            plan = nutrition.calculate_daily_nutrition(
                weight_kg=weight,
                today_session={"session_type": "EASY", "distance_km": 10}
            )
            return (
                f"🍽 *NUTRITION ({weight} kg)*\n"
                f"• Carbs: {plan.get('carbs_g', 'N/A')} g\n"
                f"• Protein: {plan.get('protein_g', 'N/A')} g\n"
                f"• Fat: {plan.get('fat_g', 'N/A')} g\n"
                f"• Total: {plan.get('total_calories', 'N/A')} kcal\n"
                f"• Optimal run time: {run_time}"
            )
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_sync():
        garmin: GarminSync = ctx["garmin"]
        try:
            data = garmin.sync_all()
            acts = len(data.get("activities", []))
            wts = len(data.get("weight", []))
            hrv_c = len(data.get("hrv", []))
            slp = len(data.get("sleep", []))
            ctx["last_garmin_data"] = data
            return (
                f"🔄 *SYNC COMPLETE*\n"
                f"• Activities: {acts}\n"
                f"• Weight entries: {wts}\n"
                f"• HRV readings: {hrv_c}\n"
                f"• Sleep sessions: {slp}"
            )
        except Exception as e:
            return f"❌ Garmin sync failed: {e}"

    def cb_activities():
        garmin: GarminSync = ctx["garmin"]
        try:
            acts = garmin.sync_activities(days_back=7)
            if not acts:
                return "Δεν βρέθηκαν activities τελευταίες 7 μέρες."
            lines = ["🏃 *RECENT ACTIVITIES*\n"]
            for a in acts[:5]:
                lines.append(
                    f"• {a['date']}: {a['distance_km']} km "
                    f"@ {a['avg_hr']} bpm"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_drift():
        drift_eng: DriftEngine = ctx["drift_engine"]
        garmin: GarminSync = ctx["garmin"]
        try:
            acts = ctx.get("last_garmin_data", {}).get("activities", [])
            if not acts:
                acts = garmin.sync_activities(days_back=14)
            if not acts:
                return "Δεν υπάρχουν activities για drift analysis."
            # Use most recent activity
            latest = acts[0]
            result = drift_eng.analyze_cardiac_drift(
                hr_data=[latest.get("avg_hr", 150)],
                duration_min=latest.get("duration_sec", 3600) // 60
            )
            return (
                f"📉 *CARDIAC DRIFT*\n"
                f"• Drift: {result.get('drift_percent', 'N/A')}%\n"
                f"• Assessment: {result.get('assessment', 'N/A')}\n"
                f"• LT zone: {result.get('lt_zone', 'N/A')}"
            )
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_shoes():
        equipment = ctx.get("equipment")
        if equipment is None:
            return "⏳ Equipment manager not configured."
        try:
            # Get today's session type from context if available
            session_type = ctx.get("today_session_type", "EASY")
            rec = equipment.recommend_shoe(session_type)
            return f"👟 *SHOE RECOMMENDATION*\n• Session: {session_type}\n• Shoe: {rec}"
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    def cb_calibration():
        coach: DailyCoach = ctx["daily_coach"]
        try:
            summary = coach.outcome_tracker.get_calibration_summary()
            return _format_calibration_summary(summary)
        except Exception as e:
            return f"❌ Σφάλμα: {e}"

    # Register all callbacks
    telegram.register_command("today",      cb_today)
    telegram.register_command("week",       cb_week)
    telegram.register_command("stats",      cb_stats)
    telegram.register_command("recovery",   cb_recovery)
    telegram.register_command("nutrition",  cb_nutrition)
    telegram.register_command("sync",       cb_sync)
    telegram.register_command("activities", cb_activities)
    telegram.register_command("drift",      cb_drift)
    telegram.register_command("shoes",      cb_shoes)
    telegram.register_command("calibration", cb_calibration)

    log.info(
        "telegram_callbacks_registered",
        extra={"command_count": 10},
    )




def _parse_env_number(name: str, default: str, caster):
    """Parse numeric env var and exit safely with a clear message on invalid input."""
    raw = os.getenv(name, default)
    try:
        return caster(raw)
    except (TypeError, ValueError) as exc:
        log.error(
            "startup_failure",
            extra={
                "component": "launcher",
                "error_class": exc.__class__.__name__,
                "detail": f"Invalid environment variable {name}={raw!r}. Expected {caster.__name__}.",
            },
        )
        print(f"❌ Invalid environment variable {name}={raw!r}. Expected {caster.__name__}.")
        sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
def main():
    from titan.integrations.weather_api import WeatherAPI

    _configure_rotating_logging()
    _print_banner()

    # ── Step 1: Credentials ──────────────────────────────────────────────────
    if not ensure_credentials():
        log.error(
            "startup_failure",
            extra={
                "component": "launcher",
                "error_class": "CredentialsUnavailable",
                "detail": "ensure_credentials() returned False",
            },
        )
        sys.exit(1)

    log.info("startup_initializing_engines")

    # ── Step 2: Integrations ─────────────────────────────────────────────────
    garmin   = GarminSync()
    weather  = WeatherAPI()
    telegram = TitanTelegramBot()

    # ── Step 3: Science engines ──────────────────────────────────────────────
    hrv_engine       = HRVGuidedEngine()
    tsb_engine       = TSBEngine()
    acwr_engine      = ACWREngine()
    readiness_engine = ReadinessEngine()
    glycogen_model   = GlycogenModel()
    drift_engine     = DriftEngine()
    lactate_logic    = LactateLogic()
    trimp_engine     = TRIMPEngine()
    fatigue_engine   = FatigueEngine()
    adaptive_memory  = AdaptiveMemory()
    biomechanics     = BiomechanicsAnalysis()
    efficiency_eng   = EfficiencyEngine()
    durability_eng   = DurabilityEngine()
    critical_speed   = CriticalSpeedEngine()
    rcp_engine       = RCPEngine()

    # ── Step 4: Feature modules ──────────────────────────────────────────────
    weekly_planner    = WeeklyPlanGenerator(hrv_engine, tsb_engine, acwr_engine)
    optimal_time_calc = OptimalTimeCalculator(weather)
    nutrition_optimizer = NutritionOptimizer(glycogen_model)

    # ── Step 4b: Persistent database ─────────────────────────────────────────
    db = DatabaseManager()
    log.info(
        "database_initialized",
        extra={"database": "titan_core.db"},
    )

    # ── Step 5: Orchestration ────────────────────────────────────────────────
    daily_coach = DailyCoach(
        garmin_sync=garmin,
        weather_api=weather,
        telegram_bot=telegram,
        hrv_engine=hrv_engine,
        tsb_engine=tsb_engine,
        readiness_engine=readiness_engine,
        optimal_time_calc=optimal_time_calc,
        nutrition_optimizer=nutrition_optimizer,
        weekly_planner=weekly_planner,
        db=db,
    )

    # ── Step 6: Build context dict (passed to menu system & callbacks) ────────
    athlete_profile: AthleteProfile = {
        "name":           os.getenv("ATHLETE_NAME", "Athlete"),

        "age":            _parse_env_number("ATHLETE_AGE", "35", int),
        "weight_kg":      _parse_env_number("ATHLETE_WEIGHT", "75", float),
        "height_cm":      _parse_env_number("ATHLETE_HEIGHT", "175", float),
        "max_hr":         _parse_env_number("ATHLETE_MAX_HR", "190", int),
        "threshold_hr":   _parse_env_number("ATHLETE_THRESHOLD_HR", "168", int),

        "phase":          os.getenv("TRAINING_PHASE", "BUILD"),
        "goal":           os.getenv("TRAINING_GOAL", "5K"),
    }

    titan_ctx: TitanContext = TitanContextContract(
        garmin=garmin,
        weather=weather,
        telegram=telegram,
        hrv_engine=hrv_engine,
        tsb_engine=tsb_engine,
        acwr_engine=acwr_engine,
        readiness_engine=readiness_engine,
        glycogen_model=glycogen_model,
        drift_engine=drift_engine,
        lactate_logic=lactate_logic,
        trimp_engine=trimp_engine,
        fatigue_engine=fatigue_engine,
        adaptive_memory=adaptive_memory,
        biomechanics=biomechanics,
        efficiency_engine=efficiency_eng,
        durability_engine=durability_eng,
        critical_speed=critical_speed,
        rcp_engine=rcp_engine,
        weekly_planner=weekly_planner,
        optimal_time_calc=optimal_time_calc,
        nutrition_optimizer=nutrition_optimizer,
        daily_coach=daily_coach,
        db=db,
        athlete_profile=athlete_profile,
        last_garmin_data={},
        last_weekly_plan=None,
        today_session_type="EASY",
    ).to_payload()

    # ── Step 7: Register Telegram callbacks ──────────────────────────────────
    _register_telegram_callbacks(telegram, titan_ctx)

    # ── Step 8: Start background threads ─────────────────────────────────────
    log.info("background_threads_starting")

    garmin.start_background_sync(interval_hours=6)
    weather.start_background_updates(interval_hours=1)
    telegram.start_bot()

    # ── Step 9: Schedule automated tasks ─────────────────────────────────────
    # Use async wrapper so Telegram polling isn't blocked during morning routine
    telegram.schedule_task(
        name="Morning Coaching",
        time_str="07:00",
        callback=daily_coach.run_morning_routine_async,
    )

    def _send_weekly_plan():
        plan = weekly_planner.generate_weekly_plan(
            athlete_profile=athlete_profile,
            phase=athlete_profile.get("phase", "BUILD")
        )
        titan_ctx["last_weekly_plan"] = plan
        telegram.send_weekly_plan(plan)

    telegram.schedule_task(
        name="Weekly Plan",
        time_str="20:00",
        callback=_send_weekly_plan,
        days=["Sunday"],
    )

    log.info(
        "scheduled_tasks_configured",
        extra={
            "tasks": [
                "Morning coaching: Daily @ 07:00",
                "Weekly plan: Sunday @ 20:00",
                "Garmin sync: Every 6 hours (background)",
                "Weather updates: Every 1 hour (background)",
                "Telegram polling: Continuous (background)",
            ]
        },
    )

    # ── Step 10: Interactive menu ─────────────────────────────────────────────
    try:
        main_menu(titan_ctx)
    except KeyboardInterrupt:
        log.info(
            "shutdown_requested",
            extra={
                "reason": "keyboard_interrupt",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    finally:
        # ── Shutdown ──────────────────────────────────────────────────────────
        log.info("shutdown_started")
        garmin.stop_background_sync()
        weather.stop_background_updates()
        telegram.stop_bot()
        routine_thread = getattr(daily_coach, "_routine_thread", None)
        if routine_thread is not None and routine_thread.is_alive():
            timeout_seconds = 30
            routine_thread.join(timeout=timeout_seconds)
            still_alive = routine_thread.is_alive()
            if still_alive:
                log.error(
                    "worker_shutdown_timeout",
                    extra={
                        "worker_name": "DailyCoachRoutine",
                        "timeout_seconds": timeout_seconds,
                        "still_alive": still_alive,
                    },
                )
        db.close()
        log.info("shutdown_completed")


if __name__ == "__main__":
    main()
