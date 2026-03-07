import json
import logging

from titan.science.outcome_tracker import OutcomeTracker


def _apl_result():
    return {
        'priority_vector': {'PARASYMPATHETIC_GUARD': 1},
        'lock_thresholds': {'acwr_ceiling': 1.15},
    }


def test_outcome_tracker_persists_decision_and_restores(db_manager_factory):
    db = db_manager_factory(db_name='test.db')

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
    assert decisions[0].decision_was_followed is True
    assert decisions[0].override_outcome_exclusion is False
    assert decisions[0].outcome_independence_ok is True

    db.close()


def test_outcome_tracker_persists_post_session_outcome(db_manager_factory):
    db = db_manager_factory(db_name='test.db')

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
        outcome_date='2026-03-06',
    )

    reloaded = OutcomeTracker(db=db)
    decisions = reloaded.get_decisions(date='2026-03-03')

    assert len(decisions) == 1
    assert decisions[0].outcome_rpe == 7
    assert decisions[0].outcome_completed is True
    assert decisions[0].outcome_session_type_actual == 'TEMPO'
    assert decisions[0].outcome_notes == 'completed at reduced pace'
    assert decisions[0].decision_was_followed is True
    assert decisions[0].override_outcome_exclusion is False
    assert decisions[0].outcome_independence_ok is True
    assert decisions[0].algorithm_version_snapshot is not None

    db.close()


def test_get_governance_decisions_safe_json_fallback_and_warning(db_manager_factory, caplog):
    db = db_manager_factory(db_name='test.db')

    db.save_governance_decision(
        {
            'date': '2026-03-04',
            'session_planned': 'EASY',
            'session_post_governance': 'EASY',
            'locks_applied': ['FUELING_LOCK'],
            'governance_clean': False,
            'phase': 'BUILD',
            'vlg_color': 'YELLOW',
            'apl_priority_vector': {'FUELING_LOCK': 1},
            'lock_thresholds_active': {'glycogen_debt': 6.0},
            'acwr': 1.0,
            'tsb_value': -8.0,
            'readiness_score': 63.0,
            'glycogen_debt': 5.7,
        }
    )

    db.conn.execute(
        """UPDATE governance_outcomes
           SET locks_applied_json = '{broken',
               apl_priority_vector_json = '[oops',
               lock_thresholds_active_json = '{oops'
           WHERE date = ?""",
        ('2026-03-04',),
    )
    db.conn.commit()

    caplog.set_level(logging.WARNING, logger='titan.core.database')
    decisions = db.get_governance_decisions()

    assert len(decisions) == 1
    assert decisions[0]['locks_applied'] == []
    assert decisions[0]['apl_priority_vector'] == {}
    assert decisions[0]['lock_thresholds_active'] == {}

    events = [
        json.loads(record.message)
        for record in caplog.records
        if 'governance_row_json_malformed' in record.message
    ]
    assert len(events) == 3
    assert {event['column'] for event in events} == {
        'locks_applied_json',
        'apl_priority_vector_json',
        'lock_thresholds_active_json',
    }

    assert all(len(event['raw_preview']) <= 120 for event in events)

    db.close()


def test_get_governance_decisions_parses_valid_json_columns(db_manager_factory):
    db = db_manager_factory(db_name='test.db')

    db.save_governance_decision(
        {
            'date': '2026-03-05',
            'session_planned': 'EASY',
            'session_post_governance': 'TEMPO',
            'locks_applied': ['FATIGUE_LOCK'],
            'governance_clean': True,
            'phase': 'BASE',
            'vlg_color': 'GREEN',
            'apl_priority_vector': {'FATIGUE_LOCK': 2},
            'lock_thresholds_active': {'acwr_ceiling': 1.2},
            'acwr': 0.94,
            'tsb_value': -5.0,
            'readiness_score': 70.0,
            'glycogen_debt': 3.0,
        }
    )

    decisions = db.get_governance_decisions()

    assert len(decisions) == 1
    assert decisions[0]['locks_applied'] == ['FATIGUE_LOCK']
    assert decisions[0]['apl_priority_vector'] == {'FATIGUE_LOCK': 2}
    assert decisions[0]['lock_thresholds_active'] == {'acwr_ceiling': 1.2}

    db.close()
