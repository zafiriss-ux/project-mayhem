"""Biometric source adapter boundary contracts per ADR-0050 D4.

Concrete provider implementations (Polar, Whoop, COROS) are Phase 9+ scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceCapabilities:
    """Capability declaration per biometric source."""

    source_name: str
    supports_hrv: bool
    supports_resting_hr: bool
    supports_sleep: bool
    supports_activity_load: bool


@dataclass
class NormalizedBiometricSample:
    """Normalized biometric snapshot — source-agnostic.

    All numeric fields are ``None`` when the source did not provide a reading.
    ``provenance`` must be an ADR-0041 provenance label.
    """

    source_name: str
    sampled_at: str          # ISO-8601 UTC
    hrv_rmssd: float | None
    resting_hr: int | None
    sleep_hours: float | None
    provenance: str


@dataclass
class BiometricSourceSyncResult:
    """Result of a single sync attempt from any biometric source.

    ``sync_status`` is one of ``"ok"``, ``"degraded"``, or ``"failed"``.
    ``data_trust_report`` follows the ADR-0041 DataTrustReport payload schema.
    """

    samples: list[NormalizedBiometricSample] = field(default_factory=list)
    sync_status: str = "ok"          # "ok" | "degraded" | "failed"
    failure_class: str | None = None
    data_trust_report: dict = field(default_factory=dict)  # ADR-0041 DataTrustReport
