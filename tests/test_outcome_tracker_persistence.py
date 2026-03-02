from titan.core.database import DatabaseManager
from titan.science.outcome_tracker import OutcomeTracker


def _apl_result():
    return {
        'priority_vector': {'PARASYMPATHETIC_GUARD': 1},
        'lock_thresholds': {'acwr_ceiling': 1.15},
    }


def test_outcome_tracker_persists_decision_and_restores(tmp_path):
    db = DatabaseManager(db_name='test.db', db_dir=tmp_path)

    tracker = OutcomeTracker(db=db)
    tracker.record_decision(
        session_planned='TEMPO',
        session_post_governance='EASY',
        locks_applied=['HARD_STOP_ACWR'],
        governance_clean=False,
        phase='BUILD',
        vlg_color='YELLOW',
        apl_result=_apl_result(),
        acwr=1.4,
        tsb_value=-22.0,
        readiness_score=48.0,
        glycogen_debt=6.0,
        afi_value=-0.2,
        date='2026-03-02',
    )

    reloaded = OutcomeTracker(db=db)
    decisions = reloaded.get_decisions(date='2026-03-02')

    assert len(decisions) == 1
    assert decisions[0].session_planned == 'TEMPO'
    assert decisions[0].session_post_governance == 'EASY'
    assert decisions[0].locks_applied == ['HARD_STOP_ACWR']

    db.close()


def test_outcome_tracker_persists_post_session_outcome(tmp_path):
    db = DatabaseManager(db_name='test.db', db_dir=tmp_path)

    tracker = OutcomeTracker(db=db)
    tracker.record_decision(
        session_planned='INTERVALS',
        session_post_governance='TEMPO',
        locks_applied=['VO2_BLOCK'],
        governance_clean=False,
        phase='PEAK',
        vlg_color='RED',
        apl_result=_apl_result(),
        acwr=1.2,
        tsb_value=-28.0,
        readiness_score=52.0,
        glycogen_debt=7.5,
        date='2026-03-03',
    )

    assert tracker.record_outcome(
        date='2026-03-03',
        rpe=7,
        completed=True,
        actual_session_type='TEMPO',
        notes='completed at reduced pace',
    )

    reloaded = OutcomeTracker(db=db)
    decisions = reloaded.get_decisions(date='2026-03-03')

    assert len(decisions) == 1
    assert decisions[0].outcome_rpe == 7
    assert decisions[0].outcome_completed is True
    assert decisions[0].outcome_session_type_actual == 'TEMPO'
    assert decisions[0].outcome_notes == 'completed at reduced pace'

    db.close()
