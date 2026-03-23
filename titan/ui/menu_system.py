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
from datetime import datetime

_log = logging.getLogger(__name__)

ANSI_CLEAR_SCREEN = "\033[2J\033[H"


def _clear():
    """Clear terminal safely without spawning a shell subprocess."""
    print(ANSI_CLEAR_SCREEN, end="", flush=True)

def _header(title: str = "TITAN v51"):
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
        now = datetime.now().strftime("%a %d %b %Y  %H:%M")
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

    print(f"\n  📅 {datetime.now().strftime('%A %d %B %Y')}\n")

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
        today_name = datetime.now().strftime("%A")
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

    plan = nutrition.calculate_daily_nutrition(
        weight_kg=weight,
        today_session=today_session,
        tomorrow_session=tomorrow_session,
        training_phase=ctx.get("phase", "BUILD"),
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
                f"🍽 *ΠΛΑΝΟ ΔΙΑΤΡΟΦΗΣ – {datetime.now().strftime('%d/%m')}*\n\n"
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
        elif c == "1":
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
    activities = ctx.get("recent_activities", [])
    if not activities:
        print("  ℹ️  Κάνε sync πρώτα (Επιλογή 6 στο κεντρικό μενού).")
    else:
        print(f"  {'Ημερομηνία':<12} {'Τύπος':<10} {'km':>5} {'min':>6} {'HR':>5} {'Pace':>8}")
        _divider()
        for a in activities[-15:]:
            pace_s = a.get("avg_pace_sec_per_km", 0)
            pace_str = f"{pace_s//60}:{pace_s%60:02d}" if pace_s else "N/A"
            dur_min = a.get("duration_sec", 0) // 60
            print(f"  {a.get('date',''):<12} "
                  f"{a.get('activity_type','run'):<10} "
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
            print(f"  {a.get('date',''):<12} "
                  f"{a.get('activity_type','run'):<12} "
                  f"{drift:>7.1f}% "
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
    tsb_eng = ctx.get("tsb_engine")
    if not tsb_eng:
        print("  ⚠️  TSB engine not available.")
    else:
        ctl = tsb_eng.calculate_ctl()
        atl = tsb_eng.calculate_atl()
        tsb, status = tsb_eng.calculate_tsb()
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
    activities = ctx.get("recent_activities", [])
    if not activities:
        print("  ℹ️  Δεν υπάρχουν δεδομένα. Κάνε Garmin sync πρώτα.")
    else:
        total_km = sum(a.get("distance_km", 0) for a in activities)
        total_runs = len(activities)
        avg_hr = sum(a.get("avg_hr", 0) for a in activities if a.get("avg_hr")) / max(total_runs, 1)
        print(f"\n  📊 Τελευταίες {total_runs} δραστηριότητες:")
        print(f"    Σύνολο km:   {total_km:.1f}")
        print(f"    Μέσος HR:    {avg_hr:.0f} bpm")

        # ACWR check
        acwr_eng = ctx.get("acwr_engine")
        if acwr_eng and total_runs >= 3:
            recent_7d = sum(a.get("distance_km", 0) for a in activities[-7:])
            chronic_avg = total_km / max(len(activities), 1)
            acwr, status, rec = acwr_eng.calculate_acwr(recent_7d, chronic_avg)
            print(f"\n  ⚖️  ACWR: {acwr}  →  {status}")
            print(f"    {rec}")
    _divider()
    input("  [Enter] ")


# ══════════════════════════════════════════════════════════════════════════
# 9. ΡΥΘΜΙΣΕΙΣ
# ══════════════════════════════════════════════════════════════════════════
def menu_settings(ctx: dict):
    _clear()
    _header("Ρυθμίσεις Αθλητή")
    profile = ctx.get("athlete_profile", {})
    print(f"\n  Όνομα:     {profile.get('name','N/A')}")
    print(f"  Βάρος:     {profile.get('weight_kg','N/A')} kg")
    print(f"  Ηλικία:    {profile.get('age','N/A')}")
    print(f"  Max HR:    {profile.get('max_hr','N/A')}")
    print(f"  Threshold HR: {profile.get('threshold_hr','N/A')}")
    print(f"  Στόχος:    {profile.get('current_goal','N/A')}")
    _divider()
    print("  (Επεξεργασία profile: ανοίξε config.yaml ή titan/core/athlete.py)")
    input("  [Enter] ")
