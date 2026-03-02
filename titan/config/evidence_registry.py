"""
Parameter Provenance Registry — source evidence for all governance thresholds.

Every constant in titan/config/thresholds.py has a corresponding entry here.
This registry is the mandatory prerequisite before any science-tuning of those
values. Without provenance, changes are noise; with provenance, they are
evidence-based decisions.

Evidence levels:
  STRONG    — replicated RCT or large cohort (n > 200), directly applicable to
              the target population. The principle AND the specific value are
              supported.
  MODERATE  — single strong study, meta-analysis with limited population match,
              or well-supported principle with an internally-chosen specific value.
  HEURISTIC — expert consensus, clinical rule-of-thumb, policy decision, or
              internal model artifact without external validation.

Population codes:
  ELITE        — national / international competitive athletes
  RECREATIONAL — regular runners, non-elite, aged 25–50
  MASTER       — runners aged 45+, where HRV variability and recovery differ
  MIXED        — population not specified or results pooled across levels

Calibration opportunity codes (policy_note field):
  These identify what outcome data would allow a parameter to be promoted
  from HEURISTIC → MODERATE → STRONG. The OutcomeTracker module provides
  the infrastructure to collect that data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ThresholdEvidence:
    """
    Provenance record for a single governance threshold constant.

    The `value` field mirrors the live constant in thresholds.py.
    It is stored here for reference only — thresholds.py remains the
    single source of truth at runtime. Do not import from here to drive logic.
    """
    parameter: str          # Exact name as in thresholds.py
    value: float            # Mirror of the current live value (informational)
    evidence_level: str     # STRONG / MODERATE / HEURISTIC
    population: str         # ELITE / RECREATIONAL / MASTER / MIXED
    source: str             # Author (year). Journal. Citation details.
    rationale: str          # Why this specific value was chosen
    policy_note: Optional[str] = None   # Deviations, caveats, calibration path
    promoted_from_level: Optional[str] = None  # Prior evidence level, if promoted
    promotion_evidence_count: Optional[int] = None  # Paired outcomes backing promotion
    promotion_date: Optional[str] = None  # YYYY-MM-DD date promotion was approved


# ──────────────────────────────────────────────────────────────────────────────
# Registry — one entry per constant in thresholds.py
# ──────────────────────────────────────────────────────────────────────────────

EVIDENCE_REGISTRY: dict[str, ThresholdEvidence] = {

    # ── Hard-stop gate H1: dual HRV/RHR collapse ─────────────────────────────
    'HARD_STOP_HRV_DELTA': ThresholdEvidence(
        parameter='HARD_STOP_HRV_DELTA',
        value=15.0,
        evidence_level='MODERATE',
        population='MIXED',
        source=(
            'Kiviniemi et al. (2007) Eur J Appl Physiol 101(6):743–751; '
            'Plews et al. (2013) Int J Sports Physiol Perform 8(5):512–521; '
            'Flatt & Esco (2016) J Strength Cond Res 30(4):995–1003'
        ),
        rationale=(
            'A 15% drop in HRV relative to the 7-day rolling baseline, combined '
            'with an RHR rise (H2), indicates acute ANS stress sufficient to '
            'contraindicate quality sessions. Single-metric HRV drops carry high '
            'day-to-day noise; requiring the dual trigger reduces false positives. '
            'The 15% value sits between the aggressive 10% threshold used by some '
            'HRV4Training protocols and the 20% threshold used in older clinical '
            'overtraining screening.'
        ),
        policy_note=(
            'MODERATE: the dual-trigger (HRV + RHR simultaneously) is sound '
            'scientific practice. The specific 15% value is a policy choice within '
            'a validated range. '
            'Calibration path: correlate H1 trigger events with athlete-reported '
            'recovery outcome (RPE next session, completion rate). '
            'Not validated specifically for master athletes where HRV variability '
            'is structurally higher.'
        ),
    ),

    # ── Hard-stop gate H1: dual HRV/RHR collapse — RHR component ─────────────
    'HARD_STOP_RHR_DELTA': ThresholdEvidence(
        parameter='HARD_STOP_RHR_DELTA',
        value=8.0,
        evidence_level='MODERATE',
        population='RECREATIONAL',
        source=(
            'Kenttä & Hassmén (1998) Sports Med 26(1):1–16; '
            'Meeusen et al. (2013) Med Sci Sports Exerc 45(1):186–205 '
            '(ECSS/ACSM joint consensus on overtraining)'
        ),
        rationale=(
            'RHR elevation of 5–10 bpm above rolling baseline is consistently '
            'cited across overtraining literature as a clinical indicator requiring '
            'load reduction. 8 bpm balances sensitivity against measurement noise: '
            'wearable RHR has 3–5 bpm inter-day variability depending on '
            'measurement conditions, so 8 bpm represents a clear signal above noise.'
        ),
        policy_note=(
            'MODERATE: the physiological basis is well-supported. The 8 bpm '
            'specific value requires consistent measurement conditions (same time '
            'of day, same body position) to be meaningful. '
            'Calibration path: compare H1 triggers to athlete session completion '
            'data. If the gate fires frequently on valid training days, '
            'consider raising to 10 bpm for the specific athlete profile.'
        ),
    ),

    # ── Hard-stop gate H2: TSB floor ─────────────────────────────────────────
    'HARD_STOP_TSB_FLOOR': ThresholdEvidence(
        parameter='HARD_STOP_TSB_FLOOR',
        value=-50.0,
        evidence_level='HEURISTIC',
        population='RECREATIONAL',
        source=(
            'Coggan (1990/2003) — TSB/CTL/ATL performance management chart '
            '(TrainingPeaks PMC model origin); '
            'Morton et al. (1990) J Appl Physiol 69(3):1171–1182 '
            '— fitness-fatigue systems model'
        ),
        rationale=(
            'TSB < -30 is conventionally "accumulated fatigue" in the PMC model; '
            'TSB < -50 exceeds the functional performance zone for recreational '
            'athletes and is associated with high injury and illness risk in coach '
            'practice. The -50 floor as a quality-session hard stop is a policy '
            'decision derived from coaching convention, not a directly measured '
            'injury threshold.'
        ),
        policy_note=(
            'HEURISTIC. No RCT establishes -50 as a specific injury threshold. '
            'Elite athletes may sustain TSB < -30 in intensification blocks. '
            'Recreational athletes should treat TSB < -30 as a warning. '
            'The -50 hard stop is appropriately conservative for a safety gate. '
            'Calibration path: tag every H2 trigger in OutcomeTracker. '
            'Correlate with injury/illness events across a season to validate '
            'or adjust the floor per athlete.'
        ),
    ),

    # ── Hard-stop gate H4: subjective extreme fatigue ─────────────────────────
    'SUBJECTIVE_FATIGUE_EXTREME': ThresholdEvidence(
        parameter='SUBJECTIVE_FATIGUE_EXTREME',
        value=8,
        evidence_level='MODERATE',
        population='MIXED',
        source=(
            'Borg (1982) Med Sci Sports Exerc 14(5):377–381 '
            '— psychophysical bases of perceived exertion; '
            'Foster et al. (1998) Med Sci Sports Exerc 30(7):1103–1107 '
            '— session-RPE for training monitoring; '
            'Impellizzeri et al. (2004) J Sports Sci 22(1):49–56'
        ),
        rationale=(
            'RPE ≥ 8/10 on the Borg CR10 scale corresponds to "very hard" to '
            '"very very hard." Applied here as a self-reported accumulated fatigue '
            'indicator (not session effort), this level signals the athlete '
            'perceives their systemic state as severely compromised. '
            'Foster\'s session-RPE work validates the scale\'s sensitivity to '
            'training load; the 8/10 threshold for a fatigue gate is conservative '
            'enough to avoid suppressing training on moderately hard days.'
        ),
        policy_note=(
            'MODERATE: the RPE scale is validated; the 8/10 threshold for a '
            'governance hard stop is a policy choice. '
            'Subjective self-report is vulnerable to athlete bias — stoic athletes '
            'under-report, anxious athletes over-report. '
            'Calibration path: compare H4 trigger rates per athlete against '
            'objective signal convergence (HRV, RHR, sleep score on the same day). '
            'An athlete with consistent H4 triggers but green objective signals '
            'suggests a reporting pattern, not physiological overreach.'
        ),
    ),

    # ── Soft downgrade gate: 2-of-4 indicator composite ──────────────────────
    'SUBJECTIVE_FATIGUE_2OF4': ThresholdEvidence(
        parameter='SUBJECTIVE_FATIGUE_2OF4',
        value=6,
        evidence_level='HEURISTIC',
        population='MIXED',
        source=(
            'Policy decision. The 2-of-4 composite gate architecture draws on '
            'multi-signal composite fatigue literature; the specific 6/10 sub-threshold '
            'has no direct external citation.'
        ),
        rationale=(
            'The 2-of-4 gate requires ≥ 2 of {HRV soft trigger, poor sleep, '
            'low readiness score, high subjective fatigue} to fire a downgrade. '
            'This composite structure intentionally requires signal convergence '
            'to reduce single-sensor false positives. The 6/10 subjective '
            'component threshold (lower than the H4 hard stop at 8/10) allows '
            'earlier warning in the composite context where other signals '
            'must also confirm.'
        ),
        policy_note=(
            'HEURISTIC. The 6/10 value and the 2-of-4 composite architecture are '
            'internal design decisions. '
            'Calibration path: after 30+ sessions in OutcomeTracker, compute '
            'the false-positive and false-negative rates of the 2-of-4 gate. '
            'If the gate fires on days where the athlete completes the session '
            'at normal RPE, consider raising the subjective component threshold.'
        ),
    ),

    # ── VO2 eligibility gate V1: ACWR lower bound ────────────────────────────
    'VO2_ACWR_MIN': ThresholdEvidence(
        parameter='VO2_ACWR_MIN',
        value=0.80,
        evidence_level='MODERATE',
        population='MIXED',
        source=(
            'Gabbett (2016) Br J Sports Med 50(5):273–280 '
            '— training-injury prevention paradox; '
            'Hulin et al. (2016) Br J Sports Med 50(4):231–236; '
            'Malone et al. (2017) Int J Sports Physiol Perform 12(8):1100–1106'
        ),
        rationale=(
            'ACWR < 0.8 indicates acute training load is substantially below '
            'the chronic baseline — a detraining signal. Prescribing VO2max '
            'intensity on a detrained base risks maladaptive stimulus and '
            'disproportionate fatigue. The 0.8 lower bound is from the lower '
            'edge of Gabbett\'s "sweet spot" range (0.8–1.3).'
        ),
        policy_note=(
            'MODERATE: Gabbett\'s data is primarily team-sport athletes '
            '(rugby, cricket). Applicability to endurance runners is plausible '
            'but not directly validated. '
            'The ACWR model assumes training load is a homogeneous commodity; '
            'for running, intensity distribution matters as much as volume. '
            'Calibration path: compare VO2 session quality (pace at target HR) '
            'between sessions triggered at ACWR 0.8–0.9 vs 1.0–1.2.'
        ),
    ),

    # ── VO2 eligibility gate V1: ACWR upper bound ────────────────────────────
    'VO2_ACWR_MAX': ThresholdEvidence(
        parameter='VO2_ACWR_MAX',
        value=1.30,
        evidence_level='MODERATE',
        population='RECREATIONAL',
        source=(
            'Gabbett (2016) Br J Sports Med 50(5):273–280; '
            'Malone et al. (2017) Int J Sports Physiol Perform 12(8):1100–1106; '
            'Windt & Gabbett (2017) Br J Sports Med 51(3):209–214'
        ),
        rationale=(
            'The original Gabbett sweet-spot ceiling is 1.5; TITAN tightens this '
            'to 1.30 specifically for VO2-intensity sessions. This is a deliberate '
            'conservative policy: high-intensity work at elevated ACWR amplifies '
            'injury risk beyond what the global 1.5 ceiling implies for all sessions. '
            'The 1.3 ceiling for quality-only sessions aligns with the more '
            'conservative interpretation in Malone (2017).'
        ),
        policy_note=(
            'MODERATE with conservative adjustment. ACWR 1.3–1.5 is "moderate risk" '
            'in Gabbett\'s model — not prohibited for easy sessions. '
            'TITAN applies 1.30 as a quality-session-only constraint, which is '
            'a stricter policy than the published literature requires. '
            'APL further tightens this to 1.10 in PEAK phase and 1.15 in BUILD/OVERLOAD. '
            'Calibration path: log V1-triggered VO2 gates and correlate with '
            'injury/illness incidence in the following 7 days.'
        ),
    ),

    # ── VO2 eligibility gate V2: readiness floor ─────────────────────────────
    'VO2_READINESS_MIN': ThresholdEvidence(
        parameter='VO2_READINESS_MIN',
        value=65.0,
        evidence_level='HEURISTIC',
        population='RECREATIONAL',
        source=(
            'Internal composite readiness model (ReadinessEngine). '
            'No external citation for the specific 65/100 value.'
        ),
        rationale=(
            'The composite readiness score (0–100) blends HRV, RHR, sleep score, '
            'and soreness via the ReadinessEngine. A 65/100 floor for VO2 sessions '
            'requires above-average recovery (the neutral baseline is approximately '
            '70 with normal signals). The specific value is a policy decision '
            'based on the scale design, not a published threshold.'
        ),
        policy_note=(
            'HEURISTIC. The readiness score composite is an internal construct '
            'without external validation. '
            'Calibration path (high priority): correlate readiness score at '
            'VO2 session start with: (a) session RPE, (b) pace at target HR, '
            '(c) completion rate. If sessions with readiness 60–65 complete at '
            'normal RPE, consider lowering the floor to 60. '
            'This is the highest-value calibration candidate in the registry.'
        ),
    ),

    # ── VO2 eligibility gate V3: glycogen debt ───────────────────────────────
    'VO2_GLYCOGEN_DEBT_MAX': ThresholdEvidence(
        parameter='VO2_GLYCOGEN_DEBT_MAX',
        value=7.0,
        evidence_level='MODERATE',
        population='MIXED',
        source=(
            'Jeukendrup (2004) Sports Med 34(5):297–306 '
            '— carbohydrate intake during exercise; '
            'Burke et al. (2011) J Sports Sci 29(Sup1):S17–27 '
            '— carbohydrates for training and competition'
        ),
        rationale=(
            'Glycogen debt ≥ 7 internal units indicates meaningful substrate '
            'depletion that would compromise high-intensity session quality and '
            'elevate cortisol. The physiological basis (glycogen depletion impairs '
            'VO2max-intensity performance) is MODERATE-STRONG. '
            'The specific 7-unit threshold maps to the internal GlycogenDebtAccumulator '
            'model which converts TRIMP + time-above-LT2 into depletion units — '
            'this unit mapping is not externally validated.'
        ),
        policy_note=(
            'MODERATE for physiology; HEURISTIC for the model-unit mapping. '
            'The 7-unit threshold is a model artifact. External validation would '
            'require correlating daily_debt levels with measured muscle glycogen '
            '(biopsy) or indirect proxies (blood glucose trend, respiratory '
            'exchange ratio). '
            'Calibration path: compare V3-triggered sessions with athlete-reported '
            '"heavy legs" or pace degradation at equivalent HR.'
        ),
    ),

    # ── VO2 eligibility gate V5: minimum recovery days ───────────────────────
    'VO2_MIN_DAYS_SINCE_LAST': ThresholdEvidence(
        parameter='VO2_MIN_DAYS_SINCE_LAST',
        value=2,
        evidence_level='STRONG',
        population='MIXED',
        source=(
            'Billat (2001) Sports Med 31(1):13–31 '
            '— interval training for VO2max; '
            'Laursen & Jenkins (2002) Sports Med 32(1):53–73 '
            '— interval training for well-trained athletes (review); '
            'Seiler & Tønnessen (2009) Int J Sports Physiol Perform 4(3):302–321 '
            '— 80/20 polarized training distribution'
        ),
        rationale=(
            '48 hours (2 days) minimum between VO2max-intensity sessions is the '
            'consistent recommendation across endurance training literature. '
            'The requirement allows CNS recovery, glycogen resynthesis, and '
            'prevents accumulated microtrauma from consecutive high-intensity bouts. '
            'Most periodized high-volume programs (Scandinavian model, Lydiard) '
            'space VO2 work at 2–3 sessions/week with ≥ 48h gaps.'
        ),
        policy_note=(
            'STRONG: the 48h principle is well-replicated. The exact integer '
            '(2 days vs 48 hours from session end) is a practical implementation '
            'choice. Elite athletes in specific peaking phases may manage 3 VO2 '
            'sessions/week with careful load management — the gate correctly '
            'blocks a 4th within 48h but would not fire on day 3 of a heavy week.'
        ),
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_evidence(parameter: str) -> Optional[ThresholdEvidence]:
    """Look up provenance record by parameter name. Returns None if not found."""
    return EVIDENCE_REGISTRY.get(parameter)


def get_by_evidence_level(level: str) -> list[ThresholdEvidence]:
    """Return all parameters at a specific evidence level (STRONG/MODERATE/HEURISTIC)."""
    level = level.upper()
    return [v for v in EVIDENCE_REGISTRY.values() if v.evidence_level == level]


def get_policy_parameters() -> list[str]:
    """Return parameter names classified as HEURISTIC (policy decisions)."""
    return [k for k, v in EVIDENCE_REGISTRY.items() if v.evidence_level == 'HEURISTIC']


def get_calibration_candidates() -> list[str]:
    """
    Return parameters that are top candidates for data-driven calibration.

    These are HEURISTIC parameters and MODERATE parameters whose value is
    derived from an internal model rather than directly from a study.
    OutcomeTracker should prioritise collecting outcome data for these first.
    """
    candidates = []
    for k, v in EVIDENCE_REGISTRY.items():
        if v.evidence_level == 'HEURISTIC':
            candidates.append(k)
        elif v.evidence_level == 'MODERATE' and 'internal' in v.source.lower():
            candidates.append(k)
    return candidates


def get_registry_summary() -> dict:
    """Return a structured summary of the registry for display/logging."""
    total = len(EVIDENCE_REGISTRY)
    by_level: dict[str, int] = {}
    by_population: dict[str, int] = {}
    for v in EVIDENCE_REGISTRY.values():
        by_level[v.evidence_level] = by_level.get(v.evidence_level, 0) + 1
        by_population[v.population] = by_population.get(v.population, 0) + 1
    return {
        'total_parameters': total,
        'by_evidence_level': by_level,
        'by_population': by_population,
        'policy_parameters': get_policy_parameters(),
        'calibration_candidates': get_calibration_candidates(),
        'promoted_parameters': [
            v.parameter
            for v in EVIDENCE_REGISTRY.values()
            if v.promoted_from_level is not None
        ],
    }
