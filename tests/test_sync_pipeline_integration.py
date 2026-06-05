"""
Sync pipeline contract tests (Pass 3).

Verifies that the orchestration boundary contracts and the biometric
normalization contract uphold their documented TypedDict and dataclass shapes.

3 contract tests:
  S1 — GarminSyncResultContract.to_payload() produces valid GarminSyncResult shape
  S2 — HRVSyncMetricsContract.to_payload() produces valid HRVSyncMetrics shape
  S3 — NormalizedBiometricSample fields satisfy documented type invariants
"""

import pytest

from titan.integrations.garmin_sync import NormalizedBiometricSample
from titan.orchestration.contracts import GarminSyncResultContract, HRVSyncMetricsContract

_GARMIN_REQUIRED_KEYS = {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics"}
_HRV_METRICS_REQUIRED_KEYS = {"days_back", "synced_days", "skipped_days"}


class TestSyncPipelineContracts:

    # S1 — GarminSyncResultContract → GarminSyncResult TypedDict
    @pytest.mark.unit
    def test_s1_garmin_sync_result_contract_produces_required_keys(self) -> None:
        """to_payload() must include all mandatory GarminSyncResult TypedDict keys."""
        hrv_metrics = {"days_back": 7, "synced_days": 5, "skipped_days": 2}
        contract = GarminSyncResultContract(
            activities=[{"date": "2026-03-29", "load": 120.0}],
            weight=[],
            sleep=[{"date": "2026-03-29", "hours": 7.5}],
            hrv=[{"date": "2026-03-29", "rmssd": 42.5}],
            hrv_sync_metrics=hrv_metrics,
            status="ok",
            data_age_hours=1.5,
        )
        payload = contract.to_payload()

        assert _GARMIN_REQUIRED_KEYS.issubset(payload.keys()), (
            f"Missing keys: {_GARMIN_REQUIRED_KEYS - payload.keys()}"
        )
        assert isinstance(payload["activities"], list)
        assert isinstance(payload["hrv"], list)
        assert isinstance(payload["hrv_sync_metrics"], dict)
        # Optional keys present when provided
        assert payload.get("status") == "ok"
        assert payload.get("data_age_hours") == 1.5

    # S2 — HRVSyncMetricsContract → HRVSyncMetrics TypedDict
    @pytest.mark.unit
    def test_s2_hrv_sync_metrics_contract_produces_required_keys(self) -> None:
        """to_payload() must include days_back, synced_days, skipped_days with correct values."""
        contract = HRVSyncMetricsContract(days_back=7, synced_days=5, skipped_days=2)
        payload = contract.to_payload()

        assert _HRV_METRICS_REQUIRED_KEYS.issubset(payload.keys()), (
            f"Missing keys: {_HRV_METRICS_REQUIRED_KEYS - payload.keys()}"
        )
        assert payload["days_back"] == 7
        assert payload["synced_days"] == 5
        assert payload["skipped_days"] == 2
        # Invariant: synced + skipped <= days_back
        assert payload["synced_days"] + payload["skipped_days"] <= payload["days_back"]

    # S3 — NormalizedBiometricSample field-type invariants
    @pytest.mark.unit
    def test_s3_normalized_biometric_sample_field_types(self) -> None:
        """NormalizedBiometricSample must accept numeric values and None for optional fields."""
        full_sample = NormalizedBiometricSample(
            source_name="garmin",
            sampled_at="2026-03-29T07:00:00Z",
            hrv_rmssd=42.5,
            resting_hr=52,
            sleep_hours=7.5,
            provenance="GARMIN_CONNECT_LIVE",
        )
        assert isinstance(full_sample.source_name, str)
        assert len(full_sample.source_name) > 0
        assert isinstance(full_sample.sampled_at, str)
        assert isinstance(full_sample.hrv_rmssd, float)
        assert isinstance(full_sample.resting_hr, int)
        assert isinstance(full_sample.provenance, str)
        assert len(full_sample.provenance) > 0

        # None is valid for all numeric fields (missing sensor reading)
        null_sample = NormalizedBiometricSample(
            source_name="garmin",
            sampled_at="2026-03-29T07:00:00Z",
            hrv_rmssd=None,
            resting_hr=None,
            sleep_hours=None,
            provenance="GARMIN_CONNECT_LIVE",
        )
        assert null_sample.hrv_rmssd is None
        assert null_sample.resting_hr is None
        assert null_sample.sleep_hours is None
        # Non-nullable fields remain set
        assert null_sample.source_name == "garmin"
        assert null_sample.provenance == "GARMIN_CONNECT_LIVE"
