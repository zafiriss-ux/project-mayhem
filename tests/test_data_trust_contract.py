import pytest

from titan.science.data_trust import DataTrustLevel, evaluate_garmin_trust, evaluate_weather_trust


@pytest.mark.unit
def test_data_trust_contract_garmin_fresh_valid_trusted():
    report = evaluate_garmin_trust(data_age_hours=1.0, sync_status="ok")

    assert report.trust_level == DataTrustLevel.TRUSTED


@pytest.mark.unit
def test_data_trust_contract_garmin_over_12h_suspect():
    report = evaluate_garmin_trust(data_age_hours=13.0, sync_status="ok")

    assert report.trust_level == DataTrustLevel.SUSPECT


@pytest.mark.unit
def test_data_trust_contract_garmin_over_26h_invalid():
    report = evaluate_garmin_trust(data_age_hours=27.0, sync_status="ok")

    assert report.trust_level == DataTrustLevel.INVALID


@pytest.mark.unit
def test_data_trust_contract_garmin_bounds_violation_invalid():
    report = evaluate_garmin_trust(
        data_age_hours=1.0,
        sync_status="ok",
        quality_flags=["bounds_violation"],
    )

    assert report.trust_level == DataTrustLevel.INVALID


@pytest.mark.unit
def test_data_trust_contract_garmin_structural_inconsistency_invalid():
    report = evaluate_garmin_trust(
        data_age_hours=1.0,
        sync_status="ok",
        quality_flags=["structural_inconsistency"],
    )

    assert report.trust_level == DataTrustLevel.INVALID


@pytest.mark.unit
def test_data_trust_contract_weather_synthetic_suspect():
    report = evaluate_weather_trust(data_quality="synthetic", data_age_hours=0.0)

    assert report.trust_level == DataTrustLevel.SUSPECT
