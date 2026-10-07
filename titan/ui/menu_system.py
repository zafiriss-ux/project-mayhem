"""
TITAN Main Menu System

Central navigation hub:
- Daily plan
- Data browser (activities, drift, HRV, sleep)
- Nutrition planner (with exact meal times)
- Training plan browser
- Shoe selector
- Settings
"""

import logging
import sys
from datetime import UTC, datetime

from titan import __version__

# ── Profile-editor constants (importable for tests) ──────────────────────────
VALID_TRAINING_PHASES: frozenset[str] = frozenset({"BASE", "BUILD", "PEAK", "TAPER"})
VALID_TRAINING_GOALS: frozenset[str] = frozenset({"5K", "10K", "HM", "M"})

_log = logging.getLogger(__name__)

ANSI_CLEAR_SCREEN = "\033[2J\033[H"


def _clear():
    """Clear terminal safely without spawning a shell subprocess."""
    print(ANSI_CLEAR_SCREEN, end="", flush=True)

def _header(title: str = f"TITAN v{__version__}"):
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🏃  {title:<52}  ║
╚══════════════════════════════════════════════════════════════╝""")

def _divider():
    print("─" * 66)


# ══════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ══════════════════════════════════════════════════════════════════════════
def main_menu(titan_ctx: dict):
    """Central hub. titan_ctx holds all engine references."""
    while True:
        _clear()
        _header()
        now = datetime.now(UTC).strftime("%a %d %b %Y  %H:%M")
        print(f"  {now}\n")
        print("  1. 🌅  Σημερινό πλάνο (coaching + optimal time)")
        print("  2. 📅  Εβδομαδιαίο πλάνο προπόνησης")
        print("  3. 🍽   Πλάνο διατροφής (με ώρες)")
        print("  4. 📊  Data browser (activities, drift, HRV, sleep)")
        print("  5. 👟  Επιλογή παπουτσιού για σήμερα")
        print("  6. 🔄  Garmin sync τώρα")
        print("  7. ⚖️   Τάση βάρους & TDEE")
        print("  8. 📈  Performance analytics")
        print("  9. ⚙️   Ρυθμίσεις αθλητή")
        print("  0. ❌  Έξοδος")
        _divider()
        choice = input("  Επιλογή: ").strip()

        actions = {
            "1": lambda: menu_daily_plan(titan_ctx),
            "2": lambda: menu_weekly_plan(titan_ctx),
            "3": lambda: menu_nutrition(titan_ctx),
            "4": lambda: menu_data_browser(titan_ctx),
            "5": lambda: menu_shoe_selector(titan_ctx),
            "6": lambda: menu_garmin_sync(titan_ctx),
            "7": lambda: menu_weight_trend(titan_ctx),
            "8": lambda: menu_analytics(titan_ctx),
            "9": lambda: menu_settings(titan_ctx),
            "0": lambda: sys.exit(0),
        }
        action = actions.get(choice)
        if action:
            action()
        else:
            print("  ⚠️  Άγνωστη επιλογή.")
            input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 1. ΣΗΜΕΡΙΝΟ ΠΛΑΝΟ
# ══════════════════════════════════════════════════════════════════════════
def menu_daily_plan(ctx: dict):
    _clear()
    _header("Σημερινό Πλάνο")

    weather = ctx.get("weather")
    hrv_eng = ctx.get("hrv_engine")
    tsb_eng = ctx.get("tsb_engine")
    opt_time = ctx.get("optimal_time_calc")

    # Recovery
    hrv_summary = hrv_eng.get_hrv_summary() if hrv_eng else {}
    tsb_val, tsb_status = tsb_eng.calculate_tsb() if tsb_eng else (None, "N/A")

    print(f"\n  📅 {datetime.now(UTC).strftime('%A %d %B %Y')}\n")

    print("  💊 ΑΝΑΚΑΜΨΗ:")
    print(f"    HRV:  {hrv_summary.get('latest_hrv', 'N/A')} ms  ({hrv_summary.get('trend','N/A')})")
    print(f"    TSB:  {tsb_val}  →  {tsb_status}")

    # Optimal time
    if weather and opt_time:
        session_type = ctx.get("today_session_type", "EASY")
        opt = opt_time.calculate_optimal_time(session_type, day_offset=0, tsb_value=tsb_val)
        print(f"\n  ⏰ ΒΕΛΤΙΣΤΗ ΩΡΑ: {opt.get('recommended_time','N/A')}")
        print(f"    Dew point: {opt.get('dew_point','N/A')}°C   Temp: {opt.get('temperature','N/A')}°C")
        print(f"    Ποιότητα: {opt.get('quality','N/A')}")
        for r in opt.get("reasoning", []):
            print(f"    • {r}")
    else:
        print("\n  ⏰ (weather engine not ready)")

    # Today's session
    plan = ctx.get("last_weekly_plan")
    if plan:
        today_name = datetime.now(UTC).strftime("%A")
        for d in plan.get("daily_sessions", []):
            if d["day"] == today_name:
                print(f"\n  🏃 ΠΡΟΠΟΝΗΣΗ: {d['session_type']} – {d.get('distance_km',0)} km")
                print(f"    {d.get('details','')}")
                break

    _divider()
    input("  [Enter] για επιστροφή ")


# ══════════════════════════════════════════════════════════════════════════
# 2. ΕΒΔΟΜΑΔΙΑΙΟ ΠΛΑΝΟ
# ══════════════════════════════════════════════════════════════════════════
def menu_weekly_plan(ctx: dict):
    _clear()
    _header("Εβδομαδιαίο Πλάνο")
    planner = ctx.get("weekly_planner")
    if not planner:
        print("  ⚠️  Weekly planner not initialized.")
        input("  [Enter] ")
        return

    profile = ctx.get("athlete_profile", {})
    plan = planner.generate_weekly_plan(profile, phase=ctx.get("phase", "BUILD"))
    ctx["last_weekly_plan"] = plan

    print(f"\n  📅 Εβδομάδα: {plan['week_start']}   Φάση: {plan['phase']}")
    print(f"  Σύνολο: {plan['total_km']} km   Quality: {plan['quality_count']}   Easy: {plan['easy_count']}   Rest: {plan['rest_count']}")
    print(f"  TSB: {plan.get('tsb_status','N/A')}   HRV: {plan.get('hrv_baseline','N/A')}")
    _divider()
    for d in plan["daily_sessions"]:
        icon = {"REST": "🛌", "EASY": "🟢", "TEMPO": "🟡", "INTERVALS": "🔴",
                "LONG_RUN": "🔵", "HAMMER": "⚡", "RACE": "🏁"}.get(d["session_type"], "⚪")
        print(f"  {icon} {d['day']:<12} {d['session_type']:<12} {d.get('distance_km',0):>5} km")
        print(f"     └ {d.get('details','')}")
        if d.get("optimal_time"):
            print(f"     └ ⏰ {d['optimal_time']}")
    _divider()
    send = input("  📱 Στείλε στο Telegram; (y/n): ").strip().lower()
    if send == "y":
        tg = ctx.get("telegram")
        if tg:
            tg.send_weekly_plan(plan)
            print("  ✅ Εστάλη!")
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 3. ΠΛΑΝΟ ΔΙΑΤΡΟΦΗΣ
# ══════════════════════════════════════════════════════════════════════════
def menu_nutrition(ctx: dict):
    _clear()
    _header("Πλάνο Διατροφής")
    nutrition = ctx.get("nutrition_optimizer")
    if not nutrition:
        print("  ⚠️  Nutrition engine not ready.")
        input("  [Enter] ")
        return

    profile = ctx.get("athlete_profile", {})
    weight = profile.get("weight_kg", 75.0)

    # Get latest weight from Garmin data if available
    w_trend = nutrition.analyze_weight_trend()
    if w_trend.get("current_weight"):
        weight = w_trend["current_weight"]

    today_session = ctx.get("today_session", {"session_type": "EASY", "duration_min": 60})
    tomorrow_session = ctx.get("tomorrow_session")

    from titan.features.nutrition_optimizer import NutritionPreferences
    db = ctx.get("db")
    nutrition_prefs_dict = db.get_nutrition_preferences("owner") if db else None
    if nutrition_prefs_dict:
        prefs = NutritionPreferences(
            training_time=nutrition_prefs_dict.get('training_time', 'variable'),
            fasted_training=nutrition_prefs_dict.get('fasted_training', 'easy_only'),
            dietary_style=nutrition_prefs_dict.get('dietary_style', 'standard'),
            meal_frequency=nutrition_prefs_dict.get('meal_frequency', 3),
            biological_sex=nutrition_prefs_dict.get('biological_sex', 'male'),
            menstrual_tracking=nutrition_prefs_dict.get('menstrual_tracking', 'no'),
        )
    else:
        prefs = None

    opt_time_str = ctx.get("optimal_time_str", "07:00")
    try:
        opt_h = int(opt_time_str.split(":")[0])
    except (ValueError, AttributeError):
        opt_h = 7

    plan = nutrition.calculate_daily_nutrition(
        weight_kg=weight,
        today_session=today_session,
        tomorrow_session=tomorrow_session,
        training_phase=ctx.get("phase", "BUILD"),
        prefs=prefs,
        optimal_time_hour=opt_h,
    )

    session_type = today_session.get("session_type", "EASY")

    print(f"\n  ⚖️  Βάρος: {weight} kg   (τάση: {w_trend.get('velocity_kg_per_week','N/A')} kg/εβδ)")
    print(f"  🏃 Σήμερα: {session_type}")
    _divider()
    print("  📊 ΣΤΟΧΟΙ ΗΜΕΡΑΣ:")
    print(f"    🔥 Θερμίδες:  {plan['total_calories']} kcal")
    print(f"    🍞 Carbs:      {plan['carbs_range']}  ({plan['carbs_g']} g)")
    print(f"    🥩 Protein:    {plan['protein_g']} g")
    print(f"    🥑 Fat:        {plan['fat_g']} g")
    print(f"    💧 Υδάτωση:   {plan['hydration_ml']} ml")
    _divider()

    # Detailed meal timing
    pre  = plan.get("pre_session", "")
    dur  = plan.get("during_session", "")
    post = plan.get("post_session", "")

    # Assign approximate clock times based on optimal run time
    opt_time_str = ctx.get("optimal_time_str", "07:00")
    try:
        run_h, run_m = map(int, opt_time_str.split(":"))
    except (ValueError, AttributeError) as exc:
        _log.warning("optimal_time_parse_fallback", extra={"raw": opt_time_str, "error": str(exc)})
        print("  (time format unavailable — defaulting to 07:00)")
        run_h, run_m = 7, 0

    from datetime import time as dtime
    pre_time  = dtime((run_h - 2) % 24, run_m)
    post_time = dtime((run_h + 1) % 24, run_m)
    eve_time  = dtime(19, 30)

    print("  🍽  ΠΡΟΓΡΑΜΜΑ ΓΕΥΜΑΤΩΝ:")
    if plan.get("meal_schedule"):
        for meal in plan["meal_schedule"]:
            print(f"    ⏰ {meal['time']}  {meal['label']}")
            print(f"       {meal['description']}")
    else:
        print(f"    ⏰ {pre_time.strftime('%H:%M')}  ΠΡΟ-ΠΡΟΠΟΝΗΤΙΚΟ")
        print(f"       {pre}")
        print("    ⏰ Κατά τη διάρκεια:")
        print(f"       {dur}")
        print(f"    ⏰ {post_time.strftime('%H:%M')}  ΜΕΤΑ-ΠΡΟΠΟΝΗΤΙΚΟ")
        print(f"       {post}")
        print(f"    ⏰ {eve_time.strftime('%H:%M')}  ΒΡΑΔΙΝΟ")
        if tomorrow_session and tomorrow_session.get("session_type") in ["INTERVALS","TEMPO","HAMMER"]:
            print(f"       🔋 Αύριο: {tomorrow_session['session_type']} → Φόρτωσε carbs βράδυ!")
        else:
            print("       Ισορροπημένο γεύμα – lean protein + λαχανικά + σύνθετοι carbs")

    _divider()
    print("  ⚠️  ΕΙΔΙΚΕΣ ΣΗΜΕΙΩΣΕΙΣ:")
    for note in plan.get("special_notes", []):
        print(f"    • {note}")

    _divider()
    send = input("  📱 Στείλε στο Telegram; (y/n): ").strip().lower()
    if send == "y":
        tg = ctx.get("telegram")
        if tg:
            msg = (
                f"🍽 *ΠΛΑΝΟ ΔΙΑΤΡΟΦΗΣ – {datetime.now(UTC).strftime('%d/%m')}*\n\n"
                f"⚖️ Βάρος: {weight} kg\n"
                f"🔥 Θερμίδες: {plan['total_calories']} kcal\n"
                f"🍞 Carbs: {plan['carbs_range']}\n"
                f"🥩 Protein: {plan['protein_g']} g\n"
                f"🥑 Fat: {plan['fat_g']} g\n\n"
                f"⏰ {pre_time.strftime('%H:%M')} – {pre}\n"
                f"⏰ {post_time.strftime('%H:%M')} – {post}\n"
                f"⏰ {eve_time.strftime('%H:%M')} – Βραδινό\n"
            )
            tg.send_message(msg)
            print("  ✅ Εστάλη!")
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 4. DATA BROWSER
# ══════════════════════════════════════════════════════════════════════════
def menu_data_browser(ctx: dict):
    while True:
        _clear()
        _header("Data Browser")
        print("  1. 🏃 Πρόσφατες δραστηριότητες")
        print("  2. 💓 Cardiac Drift ανά προπόνηση")
        print("  3. 📊 HRV timeline")
        print("  4. 😴 Ύπνος")
        print("  5. ⚖️  Ιστορικό βάρους")
        print("  6. 📈 TSB / CTL / ATL")
        print("  0. ← Πίσω")
        _divider()
        c = input("  Επιλογή: ").strip()
        if c == "0":
            break
        if c == "1":
            _browser_activities(ctx)
        elif c == "2":
            _browser_drift(ctx)
        elif c == "3":
            _browser_hrv(ctx)
        elif c == "4":
            _browser_sleep(ctx)
        elif c == "5":
            _browser_weight(ctx)
        elif c == "6":
            _browser_tsb(ctx)


def _browser_activities(ctx: dict):
    _clear()
    _header("Πρόσφατες Δραστηριότητες")
    # Prefer the full training_log from the database (all-time history) so
    # the browser is not limited to the 7-day sync window.  Fall back to the
    # in-memory sync buffer only when no database is available.
    db = ctx.get("db")
    if db is not None:
        activities = db.get_recent_activities(limit=90)
    else:
        activities = ctx.get("recent_activities", [])
    if not activities:
        print("  ℹ️  Κάνε sync πρώτα (Επιλογή 6 στο κεντρικό μενού).")
    else:
        print(f"  {'Ημερομηνία':<12} {'Τύπος':<10} {'km':>5} {'min':>6} {'HR':>5} {'Pace':>8}")
        _divider()
        for a in activities[:15]:
            pace_sec = int(a.get("avg_pace_sec_per_km") or 0)
            if pace_sec > 0:
                mins = pace_sec // 60
                secs = pace_sec % 60
                pace_str = f"{mins}:{secs:02d}/km"
            else:
                pace_str = "N/A"
            dur_min = a.get("duration_sec", 0) // 60
            print(f"  {a.get('date',''):<12} "
                  f"{a.get('activity_type', a.get('session_type', 'run')):<10} "
                  f"{a.get('distance_km',0):>5.1f} "
                  f"{dur_min:>6} "
                  f"{a.get('avg_hr',0):>5} "
                  f"{pace_str:>8}")
    _divider()
    input("  [Enter] ")


def _browser_drift(ctx: dict):
    _clear()
    _header("Cardiac Drift Ανάλυση")
    from titan.science.drift_engine import DriftEngine
    activities = ctx.get("recent_activities", [])
    if not activities:
        print("  ℹ️  Χρειάζεσαι δεδομένα Garmin. Κάνε sync πρώτα.")
    else:
        print(f"  {'Ημερομηνία':<12} {'Session':<12} {'Drift%':>8} {'Status':<20}")
        _divider()
        for a in activities[-10:]:
            # If we have first/second half HR data
            hr1 = a.get("avg_hr_first_half", 0)
            hr2 = a.get("avg_hr_second_half", 0)
            if hr1 and hr2:
                drift = DriftEngine.compute_drift(hr1, hr2)
                cls = DriftEngine.classify_drift(drift)
            else:
                drift = a.get("drift_pct", 0)
                cls = DriftEngine.classify_drift(drift) if drift else "N/A"
            drift_disp = f"{drift:.1f}%" if drift else "N/A"
            print(f"  {a.get('date',''):<12} "
                  f"{a.get('activity_type','run'):<12} "
                  f"{drift_disp:>8} "
                  f"{cls:<20}")
    _divider()
    print("\n  📚 Ερμηνεία Drift:")
    print("    < 2%   → EXCELLENT (αερόβια αποδοτικότητα)")
    print("    2–3.5% → GOOD")
    print("    3.5–5% → ACCEPTABLE")
    print("    > 5%   → POOR (μείωσε ένταση ή ανάκαμψη)")
    input("  [Enter] ")


def _browser_hrv(ctx: dict):
    _clear()
    _header("HRV Timeline")
    hrv_eng = ctx.get("hrv_engine")
    if not hrv_eng or not hrv_eng.hrv_log:
        print("  ℹ️  Χρειάζεσαι HRV δεδομένα από Garmin.")
    else:
        baseline, sd = hrv_eng.calculate_baseline()
        latest = hrv_eng.get_latest_hrv()
        print(f"\n  Baseline (7d avg): {baseline:.1f} ms   SD: {sd:.1f}" if baseline else "")
        print(f"  Latest HRV: {latest} ms")
        print(f"  Trend: {hrv_eng.get_trend_analysis()}\n")
        _divider()
        print(f"  {'Ημερομηνία':<12} {'HRV ms':>8} {'vs Baseline':>12}")
        _divider()
        for date_str, val in hrv_eng.hrv_log[-14:]:
            diff = val - baseline if baseline else 0
            sym = "▲" if diff > 0 else "▼"
            print(f"  {date_str:<12} {val:>8.1f} {sym} {abs(diff):>9.1f}")
    _divider()
    input("  [Enter] ")


def _browser_sleep(ctx: dict):
    _clear()
    _header("Ύπνος")
    sleep_data = ctx.get("recent_sleep", [])
    if not sleep_data:
        print("  ℹ️  Δεν υπάρχουν δεδομένα ύπνου από Garmin.")
    else:
        print(f"  {'Ημερομηνία':<12} {'Σύνολο':>8} {'Deep':>7} {'REM':>7} {'Score':>7}")
        _divider()
        for s in sleep_data[-7:]:
            print(f"  {s.get('date',''):<12} "
                  f"{s.get('total_sleep_hours',0):>7.1f}h "
                  f"{s.get('deep_sleep_hours',0):>6.1f}h "
                  f"{s.get('rem_sleep_hours',0):>6.1f}h "
                  f"{s.get('sleep_score','N/A'):>7}")
    _divider()
    input("  [Enter] ")


def _browser_weight(ctx: dict):
    _clear()
    _header("Ιστορικό Βάρους")
    nutrition = ctx.get("nutrition_optimizer")
    if not nutrition or not nutrition.weight_history:
        print("  ℹ️  Δεν υπάρχουν δεδομένα βάρους από Garmin.")
    else:
        trend = nutrition.analyze_weight_trend()
        print(f"\n  Τρέχον βάρος: {trend.get('current_weight','N/A')} kg")
        print(f"  Τάση (7d):    {trend.get('velocity_kg_per_week','N/A')} kg/εβδ → {trend.get('status','N/A')}")
        print(f"  Σύσταση:      {trend.get('recommendation','N/A')}")
        _divider()
        for dt, w in nutrition.weight_history[-14:]:
            print(f"  {dt:<12} {w:>6.2f} kg")
    _divider()
    input("  [Enter] ")


def _browser_tsb(ctx: dict):
    _clear()
    _header("Training Stress Balance (CTL / ATL / TSB)")
    # Prefer the engine owned by DailyCoach (authoritative post-hydration reference).
    # Fall back to ctx["tsb_engine"] for call-sites that don't include daily_coach
    # (e.g. unit tests, standalone invocations).
    daily_coach = ctx.get("daily_coach")
    tsb_eng = (
        getattr(daily_coach, "tsb", None)
        if daily_coach is not None
        else ctx.get("tsb_engine")
    ) or ctx.get("tsb_engine")
    if not tsb_eng:
        print("  ⚠️  TSB engine not available.")
    else:
        ctl = tsb_eng.calculate_ctl()
        atl = tsb_eng.calculate_atl()
        tsb, status = tsb_eng.calculate_tsb()
        if ctl is None:
            print("\n  ℹ️  Ανεπαρκή δεδομένα προπόνησης.")
            print("     Κάνε Garmin sync (επιλογή 6) για να φορτωθεί ιστορικό.")
        else:
            print(f"\n  💪 CTL (Fitness, 42d):  {ctl}")
            print(f"  😓 ATL (Fatigue,  7d):  {atl}")
            print(f"  🎯 TSB (Form):          {tsb}  →  {status}")
            _divider()
            print("\n  Οδηγός:")
            print("    TSB > +15        ⚠️  Αποπροπόνηση")
            print("    +5 έως +15       ✅  Φρέσκος")
            print("    -10 έως +5       🎯  Race form")
            print("    -30 έως -10      💪  Παραγωγικό overload")
            print("    < -30            ⚠️  Κίνδυνος overreach")
    _divider()
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 5. ΕΠΙΛΟΓΗ ΠΑΠΟΥΤΣΙΟΥ
# ══════════════════════════════════════════════════════════════════════════
def menu_shoe_selector(ctx: dict):
    _clear()
    _header("Επιλογή Παπουτσιού")
    equip = ctx.get("equipment_manager")
    if not equip:
        print("  ⚠️  Equipment manager not initialized.")
        input("  [Enter] ")
        return

    today_session = ctx.get("today_session", {"session_type": "EASY"})
    session_type = today_session.get("session_type", "EASY")

    # Logic for shoe recommendation
    shoe_rules = {
        "INTERVALS":  ("Racing flat / Carbon plate", "Μέγιστη απόδοση, ελάχιστη απόσβεση"),
        "TEMPO":      ("Tempo racer / lightweight trainer", "Γρήγορη αίσθηση + κάποια προστασία"),
        "LONG_RUN":   ("Daily trainer με πολλή απόσβεση", "Προστασία μυοσκελετικού συστήματος"),
        "EASY":       ("Daily trainer / recovery shoe", "Μαξιμάλ άνεση, ελαχιστοποίηση φόρτου"),
        "HAMMER":     ("Racing flat ή carbon", "Short explosive work – χρειάζεσαι ταχύτητα"),
        "RACE":       ("Racing shoe / carbon plate", "Ό,τι καλύτερο έχεις – tested in training"),
        "REST":       ("N/A", "Ημέρα ανάπαυσης"),
    }
    rec, reason = shoe_rules.get(session_type, ("Daily trainer", "Γενική χρήση"))

    print(f"\n  🏃 Σήμερα: {session_type}")
    _divider()
    print(f"  👟 Συνιστώμενο: {rec}")
    print(f"  💡 Λόγος:       {reason}")

    # Show shoe inventory if available
    try:
        shoes = equip.list_shoes() if hasattr(equip, "list_shoes") else []
        if shoes:
            _divider()
            print("  📦 Διαθέσιμα παπούτσια:")
            for s in shoes:
                avail = "✅" if s.get("available") else "❌ Σε αποκατάσταση"
                print(f"    {avail}  {s.get('name',''):<25} {s.get('km',0):>5} km")
    except (TypeError, KeyError, AttributeError) as exc:
        _log.warning("shoe_display_error", extra={"error_class": type(exc).__name__, "error": str(exc)})
        print("  (equipment data unavailable)")

    _divider()
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 6. GARMIN SYNC
# ══════════════════════════════════════════════════════════════════════════
def menu_garmin_sync(ctx: dict):
    _clear()
    _header("Garmin Sync")
    garmin = ctx.get("garmin")
    if not garmin:
        print("  ⚠️  Garmin not initialized.")
        input("  [Enter] ")
        return

    print("\n  🔄 Ξεκινώ sync...\n")
    data = garmin.sync_all()

    # Store in context
    ctx["recent_activities"] = data.get("activities", [])
    ctx["recent_sleep"]      = data.get("sleep", [])

    # Update weight history
    nutrition = ctx.get("nutrition_optimizer")
    if nutrition:
        for e in data.get("weight", []):
            nutrition.add_weight_entry(e["date"], e["weight_kg"])

    # Update HRV
    hrv_eng = ctx.get("hrv_engine")
    if hrv_eng:
        for e in data.get("hrv", []):
            hrv_eng.add_hrv_measurement(e["date"], e["rmssd"])

    _divider()

    sync_status  = data.get("status", "ok")
    acts         = len(data.get("activities", []))
    wts          = len(data.get("weight", []))
    slp          = len(data.get("sleep", []))
    hrv_count    = len(data.get("hrv", []))
    is_connected = getattr(garmin, "is_connected", True)

    if sync_status == "timeout_cancelled":
        print("  ❌ Timeout – η σύνδεση με Garmin ήρθε timeout.")
        print("     Δοκίμασε ξανά σε λίγο ή αύξησε GARMIN_SYNC_TIMEOUT_S στο .env.\n")
    elif not is_connected:
        print("  ❌ Αποτυχία σύνδεσης στο Garmin Connect.")
        last_err = getattr(garmin, "last_connect_error", None)
        if last_err:
            print(f"     Σφάλμα: {last_err}")
        print("     Έλεγξε email/password στο .env ή τρέξε ξανά το setup (διέγραψε .env).\n")

    def _icon(count: int) -> str:
        if count > 0:
            return "✅"
        return "❌" if not is_connected else "⚠️"

    print(f"  {_icon(acts)} Activities:  {acts}")
    print(f"  {_icon(wts)} Weight:      {wts}")
    print(f"  {_icon(slp)} Sleep:       {slp}")
    print(f"  {_icon(hrv_count)} HRV:         {hrv_count}")
    _divider()
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 7. ΤΑΣΕΙΣ ΒΑΡΟΥΣ
# ══════════════════════════════════════════════════════════════════════════
def menu_weight_trend(ctx: dict):
    _clear()
    _header("Τάση Βάρους & TDEE")
    nutrition = ctx.get("nutrition_optimizer")
    if not nutrition:
        print("  ⚠️  Nutrition engine not available.")
        input("  [Enter] ")
        return

    trend = nutrition.analyze_weight_trend()
    profile = ctx.get("athlete_profile", {})
    weight = trend.get("current_weight") or profile.get("weight_kg", 75.0)

    print(f"\n  ⚖️  Τρέχον: {weight} kg")
    print(f"  📈 Αλλαγή 7d: {trend.get('change_kg','N/A')} kg  ({trend.get('change_pct','N/A')}%)")
    print(f"  📊 Ταχύτητα: {trend.get('velocity_kg_per_week','N/A')} kg/εβδ  →  {trend.get('status','N/A')}")
    print(f"  💡 {trend.get('recommendation','N/A')}")

    # RED-S check
    if trend.get("velocity_kg_per_week", 0) < -0.5:
        print("\n  🚨 RED-S ALERT: Γρήγορη απώλεια βάρους – κίνδυνος ενεργειακής ανεπάρκειας!")
        print("     Αύξησε θερμίδες τουλάχιστον 200-300 kcal/ημέρα.")
    _divider()
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 8. ANALYTICS
# ══════════════════════════════════════════════════════════════════════════
def menu_analytics(ctx: dict):
    _clear()
    _header("Performance Analytics")
    db = ctx.get("db")
    activities = db.get_recent_activities(limit=6) if db is not None else ctx.get("recent_activities", [])
    if not activities:
        print("  ℹ️  Δεν υπάρχουν δεδομένα. Κάνε Garmin sync πρώτα.")
    else:
        total_km = sum(a.get("distance_km", 0) for a in activities)
        total_runs = len(activities)
        avg_hr = sum(a.get("avg_hr", 0) for a in activities if a.get("avg_hr")) / max(total_runs, 1)
        print(f"\n  📊 Τελευταίες {total_runs} δραστηριότητες:")
        print(f"    Σύνολο km:   {total_km:.1f}")
        print(f"    Μέσος HR:    {avg_hr:.0f} bpm")

        # ACWR check — read from DB so it works even without a live Garmin sync
        acwr_eng = ctx.get("acwr_engine")
        if acwr_eng and db is not None:
            from datetime import timedelta
            today = datetime.now(UTC).date()
            cutoff_7d = (today - timedelta(days=7)).isoformat()
            load_rows = db.get_training_load_history(days=28)
            if len(load_rows) < 14:
                print("\n  ⚖️  ACWR: —  →  INSUFFICIENT DATA")
                print("    Need at least 14 training days in the last 28d")
            else:
                acute_7d = sum(load for date, load in load_rows if date >= cutoff_7d)
                chronic_daily_avg = sum(load for _, load in load_rows) / 28
                acwr, status, rec = acwr_eng.calculate_acwr(acute_7d, chronic_daily_avg)
                print(f"\n  ⚖️  ACWR: {acwr}  →  {status}")
                print(f"    {rec}")
    _divider()
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 9. ΡΥΘΜΙΣΕΙΣ
# ══════════════════════════════════════════════════════════════════════════

def _read_current_profile() -> dict:
    """Read athlete profile directly from .env — always fresh, never stale."""
    from titan.ui.setup_wizard import ENV_PATH  # local import avoids circular

    vals: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                vals[k.strip()] = v.strip()
    return {
        "name":           vals.get("ATHLETE_NAME", "—"),
        "age":            vals.get("ATHLETE_AGE", "—"),
        "weight_kg":      vals.get("ATHLETE_WEIGHT", "—"),
        "height_cm":      vals.get("ATHLETE_HEIGHT", "—"),
        "max_hr":         vals.get("ATHLETE_MAX_HR", "—"),
        "threshold_hr":   vals.get("ATHLETE_THRESHOLD_HR", "—"),
        "training_phase": vals.get("TRAINING_PHASE", "—"),
        "current_goal":   vals.get("TRAINING_GOAL", "—"),
    }


def _validate_int(value: str, lo: int, hi: int) -> tuple[bool, str]:
    try:
        n = int(value)
    except ValueError:
        return False, "Must be a whole number"
    if not lo <= n <= hi:
        return False, f"Must be between {lo} and {hi}"
    return True, ""


def _validate_float(value: str, lo: float, hi: float) -> tuple[bool, str]:
    try:
        n = float(value)
    except ValueError:
        return False, "Must be a number"
    if not lo <= n <= hi:
        return False, f"Must be between {lo} and {hi}"
    return True, ""


def _validate_field(key: str, value: str) -> tuple[bool, str]:
    """Validate a single athlete-profile env key/value pair."""
    _validators: dict[str, object] = {
        "ATHLETE_NAME":         lambda v: (bool(v.strip()), "Name cannot be empty"),
        "ATHLETE_AGE":          lambda v: _validate_int(v, 10, 100),
        "ATHLETE_WEIGHT":       lambda v: _validate_float(v, 20.0, 300.0),
        "ATHLETE_HEIGHT":       lambda v: _validate_int(v, 100, 250),
        "ATHLETE_MAX_HR":       lambda v: _validate_int(v, 100, 220),
        "ATHLETE_THRESHOLD_HR": lambda v: _validate_int(v, 80, 210),
        "TRAINING_PHASE":       lambda v: (
            v.upper() in VALID_TRAINING_PHASES,
            f"Must be one of: {', '.join(sorted(VALID_TRAINING_PHASES))}",
        ),
        "TRAINING_GOAL":        lambda v: (
            v.upper() in VALID_TRAINING_GOALS,
            f"Must be one of: {', '.join(sorted(VALID_TRAINING_GOALS))}",
        ),
    }
    fn = _validators.get(key)
    if fn is None:
        return True, ""
    return fn(value)  # type: ignore[return-value]


def _prompt_field(label: str, current: str, env_key: str) -> str | None:
    """Prompt the user for a new value; re-prompt once on validation failure.

    Returns the new value string if the user entered a valid value, or None
    to signal "keep current value".
    """
    current_display = current if current else "N/A"
    for attempt in range(2):
        raw = input(
            f"\n  Current {label}: {current_display}. New value (Enter to keep): "
        ).strip()
        if not raw:
            return None
        ok, err = _validate_field(env_key, raw)
        if ok:
            return raw
        print(f"  ⚠️  {err}")
        if attempt == 1:
            print("  Keeping current value.")
            return None
    return None


def _edit_athlete_profile(ctx: dict) -> None:
    """Interactive field-by-field profile editor; persists changes to .env."""
    from titan.ui.setup_wizard import _save_athlete_profile_to_env  # local import avoids circular

    profile = _read_current_profile()

    fields: list[tuple[str, str, str]] = [
        ("ATHLETE_NAME",         "Name",                              str(profile.get("name", ""))),
        ("ATHLETE_AGE",          "Age",                               str(profile.get("age", ""))),
        ("ATHLETE_WEIGHT",       "Weight (kg)",                       str(profile.get("weight_kg", ""))),
        ("ATHLETE_HEIGHT",       "Height (cm)",                       str(profile.get("height_cm", ""))),
        ("ATHLETE_MAX_HR",       "Max HR",                            str(profile.get("max_hr", ""))),
        ("ATHLETE_THRESHOLD_HR", "Threshold HR",                      str(profile.get("threshold_hr", ""))),
        ("TRAINING_PHASE",       "Training phase (BASE/BUILD/PEAK/TAPER)", str(profile.get("training_phase", ""))),
        ("TRAINING_GOAL",        "Training goal (5K/10K/HM/M)",      str(profile.get("current_goal", ""))),
    ]

    _clear()
    _header("✏️  Edit Athlete Profile")
    print()

    changes: dict[str, str] = {}
    for env_key, label, current in fields:
        new_val = _prompt_field(label, current, env_key)
        if new_val is not None:
            # Normalise choice fields to uppercase
            if env_key in ("TRAINING_PHASE", "TRAINING_GOAL"):
                new_val = new_val.upper()
            changes[env_key] = new_val

    if not changes:
        print("\n  No changes made.")
        input("  [Enter] ")
        return

    _clear()
    _header("Επιβεβαίωση Αλλαγών")
    print("\n  Summary of changes:")
    for k, v in changes.items():
        print(f"    {k} = {v}")
    _divider()
    confirm = input("  Save changes? (y/n): ").strip().lower()
    if confirm == "y":
        _save_athlete_profile_to_env(changes)
        print("\n  ✅ Changes saved. Restart TITAN to apply.")
    else:
        print("\n  No changes made.")
    input("  [Enter] ")


def _edit_nutrition_prefs(ctx: dict):
    _clear()
    _header("Ρυθμίσεις Διατροφής")
    db = ctx.get("db")
    existing = db.get_nutrition_preferences("owner") if db else {}
    prefs = existing or {}

    def _cur(key, default):
        return prefs.get(key, default)

    print("\n  Q1. Τι ώρα προπονείσαι;")
    print("    1. Πρωί (6-9)       [morning]")
    print("    2. Μεσημέρι (11-14)  [midday]")
    print("    3. Βράδυ (17-20)    [evening]")
    print("    4. Μεταβλητό        [variable]")
    print(f"  (τρέχον: {_cur('training_time', 'variable')})")
    _map1 = {'1': 'morning', '2': 'midday', '3': 'evening', '4': 'variable'}
    training_time = _map1.get(input("  Επιλογή (Enter=κράτησε): ").strip(), _cur('training_time', 'variable'))

    print("\n  Q2. Τρέχεις νηστικός;")
    print("    1. Πάντα      [always]")
    print("    2. Ποτέ       [never]")
    print("    3. Μόνο EASY  [easy_only]")
    print(f"  (τρέχον: {_cur('fasted_training', 'easy_only')})")
    _map2 = {'1': 'always', '2': 'never', '3': 'easy_only'}
    fasted_training = _map2.get(input("  Επιλογή (Enter=κράτησε): ").strip(), _cur('fasted_training', 'easy_only'))

    print("\n  Q3. Διατροφικό στυλ;")
    print("    1. Τυπικό         [standard]")
    print("    2. Μεσογειακό     [mediterranean]")
    print("    3. Χαμηλοί carbs  [low_carb]")
    print("    4. Χορτοφαγικό    [vegetarian]")
    print(f"  (τρέχον: {_cur('dietary_style', 'standard')})")
    _map3 = {'1': 'standard', '2': 'mediterranean', '3': 'low_carb', '4': 'vegetarian'}
    dietary_style = _map3.get(input("  Επιλογή (Enter=κράτησε): ").strip(), _cur('dietary_style', 'standard'))

    print("\n  Q4. Γεύματα/μέρα;")
    print("    1. 3 γεύματα")
    print("    2. 5 γεύματα (+ σνακ)")
    print(f"  (τρέχον: {_cur('meal_frequency', 3)})")
    _map4 = {'1': 3, '2': 5}
    meal_frequency = _map4.get(input("  Επιλογή (Enter=κράτησε): ").strip(), _cur('meal_frequency', 3))

    print("\n  Q5. Βιολογικό φύλο; (για ενεργειακούς υπολογισμούς)")
    print("    1. Άνδρας")
    print("    2. Γυναίκα")
    print("    3. Προτιμώ να μην απαντήσω")
    print(f"  (τρέχον: {_cur('biological_sex', 'male')})")
    _map5 = {'1': 'male', '2': 'female', '3': 'prefer_not_to_say'}
    biological_sex = _map5.get(input("  Επιλογή (Enter=κράτησε): ").strip(), _cur('biological_sex', 'male'))

    menstrual_tracking = _cur('menstrual_tracking', 'no')
    if biological_sex == 'female':
        print("\n  Q6. Παρακολούθηση κύκλου;")
        print("    1. Ναι")
        print("    2. Όχι")
        print(f"  (τρέχον: {menstrual_tracking})")
        _map6 = {'1': 'yes', '2': 'no'}
        menstrual_tracking = _map6.get(input("  Επιλογή (Enter=κράτησε): ").strip(), menstrual_tracking)

    new_prefs = {
        'training_time': training_time,
        'fasted_training': fasted_training,
        'dietary_style': dietary_style,
        'meal_frequency': meal_frequency,
        'biological_sex': biological_sex,
        'menstrual_tracking': menstrual_tracking,
    }
    if db:
        db.save_nutrition_preferences("owner", new_prefs)
    print("\n  ✅ Ρυθμίσεις αποθηκεύτηκαν!")
    input("  [Enter] ")


def menu_settings(ctx: dict):
    while True:
        _clear()
        _header("Ρυθμίσεις Αθλητή")
        profile = _read_current_profile()
        print(f"\n  Όνομα:        {profile.get('name', 'N/A')}")
        print(f"  Ηλικία:       {profile.get('age', 'N/A')}")
        print(f"  Βάρος:        {profile.get('weight_kg', 'N/A')} kg")
        print(f"  Ύψος:         {profile.get('height_cm', 'N/A')} cm")
        print(f"  Max HR:       {profile.get('max_hr', 'N/A')}")
        print(f"  Threshold HR: {profile.get('threshold_hr', 'N/A')}")
        print(f"  Φάση:         {profile.get('training_phase', 'N/A')}")
        print(f"  Στόχος:       {profile.get('current_goal', 'N/A')}")
        _divider()
        print("  1. ✏️  Edit athlete profile")
        print("  2. 🍽  Ρυθμίσεις Διατροφής")
        print("  0. ← Πίσω")
        _divider()
        choice = input("  Επιλογή: ").strip()
        if choice == "1":
            _edit_athlete_profile(ctx)
        elif choice == "2":
            _edit_nutrition_prefs(ctx)
        else:
            break
