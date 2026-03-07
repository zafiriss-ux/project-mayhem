"""Unified data trust contract and minimal trust evaluators."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from titan.config.thresholds import (
    GARMIN_DATA_MAX_AGE_HOURS,
    GARMIN_DATA_SUSPECT_AGE_HOURS,
    WEATHER_DATA_SUSPECT_AGE_HOURS,
)

MODULE_VERSION = "1.0.0"


class DataTrustLevel(Enum):
    TRUSTED = "TRUSTED"
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"


@dataclass(frozen=True)
class DataTrustReport:
    source: str
    trust_level: DataTrustLevel
    reasons: list[str]
    checked_at: str
    data_age_hours: float

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source,
            "trust_level": self.trust_level.value,
            "reasons": self.reasons,
            "checked_at": self.checked_at,
            "data_age_hours": self.data_age_hours,
        }


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def evaluate_garmin_trust(
    *,
    data_age_hours: float,
    sync_status: str | None = None,
    quality_flags: list[str] | None = None,
) -> DataTrustReport:
    reasons: list[str] = []
    flags = quality_flags or []

    if any(flag in {"bounds_violation", "structural_inconsistency"} for flag in flags):
        reasons.extend(sorted({flag for flag in flags if flag in {"bounds_violation", "structural_inconsistency"}}))
        trust_level = DataTrustLevel.INVALID
    elif sync_status == "timeout_cancelled":
        reasons.append("sync_timeout_cancelled")
        trust_level = DataTrustLevel.INVALID
    elif data_age_hours > GARMIN_DATA_MAX_AGE_HOURS:
        reasons.append("garmin_data_too_old")
        trust_level = DataTrustLevel.INVALID
    elif data_age_hours > GARMIN_DATA_SUSPECT_AGE_HOURS:
        reasons.append("garmin_data_stale")
        trust_level = DataTrustLevel.SUSPECT
    else:
        trust_level = DataTrustLevel.TRUSTED

    return DataTrustReport(
        source="garmin",
        trust_level=trust_level,
        reasons=reasons,
        checked_at=_now_iso(),
        data_age_hours=round(float(data_age_hours), 3),
    )


def evaluate_weather_trust(
    *,
    data_quality: str,
    data_age_hours: float = 0.0,
) -> DataTrustReport:
    reasons: list[str] = []

    if data_quality == "synthetic":
        trust_level = DataTrustLevel.SUSPECT
        reasons.append("weather_synthetic_fallback")
    elif data_age_hours > WEATHER_DATA_SUSPECT_AGE_HOURS:
        trust_level = DataTrustLevel.SUSPECT
        reasons.append("weather_cache_stale")
    else:
        trust_level = DataTrustLevel.TRUSTED

    return DataTrustReport(
        source="weather",
        trust_level=trust_level,
        reasons=reasons,
        checked_at=_now_iso(),
        data_age_hours=round(float(data_age_hours), 3),
    )


def combine_trust_reports(reports: list[DataTrustReport]) -> DataTrustLevel:
    if any(r.trust_level == DataTrustLevel.INVALID for r in reports):
        return DataTrustLevel.INVALID
    if any(r.trust_level == DataTrustLevel.SUSPECT for r in reports):
        return DataTrustLevel.SUSPECT
    return DataTrustLevel.TRUSTED
