from titan.science.injury_risk_model import InjuryRiskEnsembleModel


def test_injury_risk_returns_explainable_output():
    assessment = InjuryRiskEnsembleModel().assess_injury_risk(
        {
            'hrv_delta': -10.0,
            'tsb': -24.0,
            'sleep_hours': 5.8,
            'soreness': 8.0,
            'acute_load_ratio': 1.5,
            'monotony': 1.9,
            'garmin_data_stale': False,
            'data_trust_overall': 'TRUSTED',
        }
    )

    explainability = assessment.explainability
    assert explainability is not None
    assert explainability.data_freshness_ok is True
    assert len(explainability.top_feature_contributions) == 3
    assert explainability.confidence_range[0] <= assessment.risk_score <= explainability.confidence_range[1]


def test_injury_risk_stale_data_discarded():
    assessment = InjuryRiskEnsembleModel().assess_injury_risk(
        {
            'hrv_delta': -9.0,
            'tsb': -20.0,
            'garmin_data_stale': True,
            'data_trust_overall': 'SUSPECT',
        }
    )

    assert assessment.explainability is not None
    assert assessment.explainability.data_freshness_ok is False
    assert InjuryRiskEnsembleModel.should_discard_advisory(assessment) is True


def test_plain_text_reason_nonempty():
    model = InjuryRiskEnsembleModel()
    assessments = [
        model.assess_injury_risk({'hrv_delta': 0.0, 'tsb': -2.0}),
        model.assess_injury_risk({'hrv_delta': -6.0, 'tsb': -12.0, 'sleep_hours': 6.2}),
        model.assess_injury_risk({'hrv_delta': -12.0, 'tsb': -28.0, 'sleep_hours': 5.4, 'acute_load_ratio': 1.7}),
    ]

    for assessment in assessments:
        assert assessment.explainability is not None
        assert assessment.explainability.plain_text_reason.strip()
