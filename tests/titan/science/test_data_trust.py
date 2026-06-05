import pytest

from titan.science.data_trust import (
    DataTrustLevel,
    combine_trust_reports,
    evaluate_garmin_trust,
    evaluate_weather_trust,
)


@pytest.mark.unit
def test_evaluate_garmin_trust_happy_path_trusted():
    report = evaluate_garmin_trust(data_age_hours=2.0, sync_status="ok")

    assert report.trust_level == DataTrustLevel.TRUSTED
    assert report.reasons == []


@pytest.mark.unit
def test_evaluate_garmin_trust_boundary_invalid_when_too_old():
    report = evaluate_garmin_trust(data_age_hours=30.0, sync_status="ok")

    assert report.trust_level == DataTrustLevel.INVALID
    assert "garmin_data_too_old" in report.reasons


@pytest.mark.unit
def test_evaluate_weather_trust_happy_path_trusted_live():
    report = evaluate_weather_trust(data_quality="live", data_age_hours=0.0)

    assert report.trust_level == DataTrustLevel.TRUSTED


@pytest.mark.unit
def test_combine_trust_reports_boundary_invalid_precedence():
    reports = [
        evaluate_weather_trust(data_quality="live", data_age_hours=0.0),
        evaluate_garmin_trust(data_age_hours=30.0),
    ]

    assert combine_trust_reports(reports) == DataTrustLevel.INVALID
