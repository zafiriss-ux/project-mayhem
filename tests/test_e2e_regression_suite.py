"""E2E-style gold-path regression tests for planning workflows."""

from titan.features.weekly_planner import WeeklyPlanGenerator
from titan.science.acwr_engine import ACWREngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.tsb_engine import TSBEngine


def _planner(*, hrv_baseline: float, hrv_latest: float, tsb_value: float, tsb_status: str):
    hrv = HRVGuidedEngine()
    tsb = TSBEngine()
    acwr = ACWREngine()

    hrv.get_hrv_summary = lambda: {'baseline': hrv_baseline, 'latest_hrv': hrv_latest}
    tsb.calculate_tsb = lambda: (tsb_value, tsb_status)
    return WeeklyPlanGenerator(hrv_engine=hrv, tsb_engine=tsb, acwr_engine=acwr)


def test_gold_path_new_athlete_onboarding_to_weekly_plan_generation(athlete_profile_factory):
    athlete = athlete_profile_factory(
        name='New Athlete',
        demographics={'gender': 'F', 'age': 31, 'height_cm': 168, 'weight_kg': 61.5},
        hr_data={'resting_hr': 48, 'max_hr': 186},
    )

    planner = _planner(hrv_baseline=52.0, hrv_latest=53.0, tsb_value=-8.0, tsb_status='NEUTRAL')
    plan = planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD')

    assert plan['phase'] == 'BUILD'
    assert len(plan['daily_sessions']) == 7
    assert plan['quality_count'] >= 2
    assert plan['total_km'] > 0


def test_gold_path_new_athlete_snapshot_is_stable_for_same_inputs(athlete_profile_factory):
    athlete = athlete_profile_factory(
        name='New Athlete Snapshot',
        demographics={'gender': 'F', 'age': 31, 'height_cm': 168, 'weight_kg': 61.5},
        hr_data={'resting_hr': 48, 'max_hr': 186},
    )

    planner = _planner(hrv_baseline=52.0, hrv_latest=53.0, tsb_value=-8.0, tsb_status='NEUTRAL')

    def snapshot(plan):
        return {
            'phase': plan['phase'],
            'total_km': plan['total_km'],
            'quality_count': plan['quality_count'],
            'sessions': [
                (s['day'], s['session_type'], s['distance_km'], s['details'])
                for s in plan['daily_sessions']
            ],
        }

    snap1 = snapshot(planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD'))
    snap2 = snapshot(planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD'))

    assert snap1 == snap2


def test_gold_path_weekly_plan_snapshot_is_deterministic_for_same_inputs(athlete_profile_factory):
    athlete = athlete_profile_factory(name='Determinism Check')
    planner = _planner(hrv_baseline=50.0, hrv_latest=50.0, tsb_value=-5.0, tsb_status='NEUTRAL')

    def snapshot(plan):
        return {
            'phase': plan['phase'],
            'total_km': plan['total_km'],
            'quality_count': plan['quality_count'],
            'sessions': [
                (s['day'], s['session_type'], s['distance_km'])
                for s in plan['daily_sessions']
            ],
        }

    snap1 = snapshot(planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD'))
    snap2 = snapshot(planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD'))

    assert snap1 == snap2


def test_gold_path_recovery_adaptation_downgrades_intensity_when_hrv_is_suppressed(athlete_profile_factory):
    athlete = athlete_profile_factory(name='Recovery Adaptation')
    planner = _planner(hrv_baseline=52.0, hrv_latest=38.0, tsb_value=-18.0, tsb_status='FATIGUED')

    plan = planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD')
    session_types = [s['session_type'] for s in plan['daily_sessions']]
    details = ' '.join(s['details'] for s in plan['daily_sessions'])

    assert 'INTERVALS' not in session_types
    assert details.count('downgraded') >= 1


def test_gold_path_recovery_adaptation_snapshot_is_stable_for_same_inputs(athlete_profile_factory):
    athlete = athlete_profile_factory(name='Recovery Snapshot')
    planner = _planner(hrv_baseline=52.0, hrv_latest=38.0, tsb_value=-18.0, tsb_status='FATIGUED')

    def snapshot(plan):
        return {
            'phase': plan['phase'],
            'total_km': plan['total_km'],
            'quality_count': plan['quality_count'],
            'session_types': [s['session_type'] for s in plan['daily_sessions']],
            'details': [s['details'] for s in plan['daily_sessions']],
        }

    snap1 = snapshot(planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD'))
    snap2 = snapshot(planner.generate_weekly_plan(athlete_profile=athlete.to_dict(), phase='BUILD'))

    assert snap1 == snap2


def test_smoke_today_session_fallback_without_generated_plan():
    planner = _planner(hrv_baseline=50.0, hrv_latest=50.0, tsb_value=0.0, tsb_status='FRESH')

    session = planner.get_today_session()

    assert session['session_type'] == 'EASY'
    assert session['duration_min'] == 45
