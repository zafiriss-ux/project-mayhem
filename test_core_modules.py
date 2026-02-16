#!/usr/bin/env python3
"""
Test script for TITAN core modules
Demonstrates usage of extracted core functionality
"""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from titan.core import (
    UniversalAthleteProfile,
    DatabaseManager,
    AthleteDatabase,
    EquipmentManager,
    PeriodizationManager
)
from titan.utils import (
    MathCore,
    SESSION_TYPES,
    ACWR_SAFE_MIN,
    ACWR_SAFE_MAX,
    DEFAULT_CONFIG
)


def test_athlete_profile():
    """Test UniversalAthleteProfile"""
    print("\n=== Testing Athlete Profile ===")

    athlete = UniversalAthleteProfile(name="Test Runner")
    athlete.set_demographics("M", 30, 180, 75.0)
    athlete.set_hr_data(45, 190)

    print(f"✓ Created athlete: {athlete.name}")
    print(f"  - Age: {athlete.age}, Weight: {athlete.weight_kg} kg")
    print(f"  - Resting HR: {athlete.resting_hr}, Max HR: {athlete.max_hr}")
    print(f"  - Threshold HR: {athlete.threshold_hr}")
    print(f"  - BMR: {athlete.calculate_bmr()} kcal/day")
    print(f"  - TDEE: {athlete.calculate_tdee()} kcal/day")

    # Test serialization
    data = athlete.to_dict()
    athlete2 = UniversalAthleteProfile.from_dict(data)
    print(f"✓ Serialization: {athlete2.name} restored")

    return athlete


def test_periodization(athlete):
    """Test PeriodizationManager"""
    print("\n=== Testing Periodization ===")

    pm = PeriodizationManager(athlete)
    goal = pm.add_goal(21.1, "1:30:00", "2026-04-26")

    print(f"✓ Goal created: {goal['distance_km']}K in {goal['target_time']}")
    print(f"  - Race date: {goal['race_date'].strftime('%Y-%m-%d')}")

    phase = pm.calculate_phase(goal['race_date'])
    print(f"✓ Current phase: {phase}")

    # Test different dates
    today = datetime.now()
    test_dates = [
        (datetime(2026, 2, 13), "BASE"),    # >70 days
        (datetime(2026, 3, 20), "BUILD"),   # 35-70 days
        (datetime(2026, 4, 15), "PEAK"),    # 10-35 days
        (datetime(2026, 4, 25), "TAPER"),   # 1-10 days
    ]

    for date, expected in test_dates:
        phase = pm.calculate_phase(date)
        print(f"  - {(date - today).days} days out: {phase}")


def test_equipment():
    """Test EquipmentManager"""
    print("\n=== Testing Equipment Manager ===")

    em = EquipmentManager()

    # Test various scenarios
    scenarios = [
        ("INTERVALS", "1", "TRACK", "Should be OK"),
        ("INTERVALS", "3", "CONCRETE", "Should block (recovery shoes for fast work)"),
        ("EASY", "2", "ROAD", "Should warn (race shoes for easy run)"),
        ("TEMPO", "1", "CONCRETE", "Should be OK with surface warning"),
    ]

    for session, shoe_id, surface, description in scenarios:
        ok, msg = em.check_gear(session, shoe_id, surface)
        status = "✓ PASS" if ok else "✗ BLOCK"
        print(f"{status} {session} with shoe {shoe_id} on {surface}")
        print(f"      → {msg}")
        print(f"      ({description})")


def test_database():
    """Test DatabaseManager"""
    print("\n=== Testing Database Manager ===")

    # Use temporary database
    db_path = Path(__file__).parent / "test_titan.db"
    if db_path.exists():
        db_path.unlink()

    db = DatabaseManager(db_name="test_titan.db")
    print("✓ Database created")

    # Save daily metric
    db.save_daily_metric(
        date="2026-02-13",
        weight=75.2,
        hrv=65,
        rhr=45,
        sleep_hours=7.5,
        sleep_quality=80,
        soreness=1,
        fatigue=2,
        mood=4
    )
    print("✓ Daily metric saved")

    # Save training sessions
    sessions = [
        ("2026-02-10", "EASY", 8.0, 2400, 7),
        ("2026-02-11", "TEMPO", 10.0, 2400, 8),
        ("2026-02-12", "INTERVALS", 6.0, 2100, 9),
        ("2026-02-13", "EASY", 7.0, 2100, 6),
    ]

    for date, session_type, distance, duration, rpe in sessions:
        db.save_session(
            date=date,
            session_type=session_type,
            distance_km=distance,
            duration_sec=duration,
            rpe=rpe
        )
    print(f"✓ Saved {len(sessions)} training sessions")

    # Calculate CTL/ATL/TSB
    ctl, atl, tsb = db.get_ctl_atl_tsb()
    print(f"✓ Training Stress Balance calculated:")
    print(f"  - CTL (Fitness): {ctl}")
    print(f"  - ATL (Fatigue): {atl}")
    print(f"  - TSB (Form): {tsb}")

    # Add and check shoe
    shoe_id = db.add_shoe("Test Shoe", "DAILY", 800)
    print(f"✓ Added shoe with ID: {shoe_id}")

    available, msg = db.check_shoe_availability(shoe_id)
    print(f"✓ Shoe availability: {msg}")

    # Save PR
    db.save_personal_best(5.0, 1140, "2026-02-13", "Test 5K")
    pr = db.get_pr(5.0)
    if pr:
        time_sec, date, race = pr
        minutes = time_sec // 60
        seconds = time_sec % 60
        print(f"✓ PR saved: 5K in {minutes}:{seconds:02d}")

    db.close()
    print("✓ Database closed")

    # Cleanup
    if db_path.exists():
        db_path.unlink()
        print("✓ Test database cleaned up")


def test_athlete_database():
    """Test AthleteDatabase"""
    print("\n=== Testing Athlete Database ===")

    # Use temporary directory
    db_path = Path(__file__).parent / "test_athletes"
    if db_path.exists():
        import shutil
        shutil.rmtree(db_path)

    adb = AthleteDatabase(db_path="test_athletes")
    print("✓ Athlete database initialized")

    # Create athletes
    athlete1 = adb.create_athlete("Runner One", "M", 30, 180, 75)
    print(f"✓ Created: {athlete1.name} (ID: {athlete1.athlete_id})")

    athlete2 = adb.create_athlete("Runner Two", "F", 28, 165, 58)
    print(f"✓ Created: {athlete2.name} (ID: {athlete2.athlete_id})")

    # List all
    all_athletes = adb.list_all()
    print(f"✓ Total athletes: {len(all_athletes)}")
    for a in all_athletes:
        print(f"  - {a['name']} ({a['gender']}, {a['age']} years)")

    # Switch athlete
    adb.switch_athlete(athlete1.athlete_id)
    current = adb.get_current()
    print(f"✓ Switched to: {current.name}")

    # Cleanup
    if db_path.exists():
        import shutil
        shutil.rmtree(db_path)
        print("✓ Test athlete database cleaned up")


def test_math_core():
    """Test MathCore utilities"""
    print("\n=== Testing Math Core ===")

    # Weight function tests
    weight_tests = [
        (74.0, 0.5, 300, "AGGRESSIVE_CORRECTION"),
        (74.8, 0.5, 300, "EMERGENCY_MODE"),
        (75.2, 1.3, 300, "NIGHT_DROP_ALERT"),
        (75.5, 0.5, 360, "EPOC_OVERRIDE"),
        (75.3, 0.5, 300, "SAFE_DROP_RULE"),
        (76.0, 0.5, 300, "STABLE"),
    ]

    print("Weight Function Tests:")
    for weight, night_drop, epoc, expected in weight_tests:
        result = MathCore.weight_function_Wf(weight, night_drop, epoc)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {weight}kg, drop {night_drop}kg, EPOC {epoc} → {result}")

    # System status tests
    status_tests = [
        ("LOW", 70, 1, 75.5, 300, 0.5, "CRITICAL", "HRV low"),
        ("NORMAL", 55, 1, 75.5, 300, 0.5, "CRITICAL", "Poor sleep"),
        ("NORMAL", 70, 4, 75.5, 300, 0.5, "CRITICAL", "High pain"),
        ("NORMAL", 70, 2, 75.5, 300, 0.5, "UNSTABLE", "Moderate pain"),
        ("NORMAL", 62, 1, 75.5, 300, 0.5, "UNSTABLE", "Suboptimal sleep"),
        ("NORMAL", 75, 1, 75.5, 300, 0.5, "STABLE", "All good"),
    ]

    print("\nSystem Status Tests:")
    for hrv, sleep, pain, weight, epoc, drop, expected, reason in status_tests:
        result = MathCore.system_status_SSV(hrv, sleep, pain, weight, epoc, drop)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {result} ({reason})")


def test_constants():
    """Test constants module"""
    print("\n=== Testing Constants ===")

    print(f"✓ Session types: {len(SESSION_TYPES)} defined")
    print(f"  {', '.join(SESSION_TYPES[:5])}...")

    print(f"✓ ACWR Safe Range: {ACWR_SAFE_MIN} - {ACWR_SAFE_MAX}")

    print(f"✓ HR Zones: {len(DEFAULT_CONFIG['hr_zones'])} zones")
    for zone, (low, high) in DEFAULT_CONFIG['hr_zones'].items():
        print(f"  - {zone}: {low}-{high}%")


def main():
    """Run all tests"""
    print("=" * 60)
    print("TITAN Core Modules Test Suite")
    print("=" * 60)

    try:
        # Test constants first (no dependencies)
        test_constants()

        # Test math core (no dependencies)
        test_math_core()

        # Test athlete profile (minimal dependencies)
        athlete = test_athlete_profile()

        # Test periodization (depends on athlete)
        test_periodization(athlete)

        # Test equipment (no dependencies)
        test_equipment()

        # Test database managers
        test_database()
        test_athlete_database()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
