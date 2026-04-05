"""
Parameter Provenance Registry — source evidence for constants, bounds, and
parameters used across the project.

This is the project-wide provenance registry. titan/config/thresholds.py is
one source of parameters tracked here, not the exclusive source; constants
owned by other modules may also have entries. This registry is the mandatory
prerequisite before any science-tuning of tracked values. Without provenance,
changes are noise; with provenance, they are evidence-based decisions.

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

from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdEvidence:
    """
    Provenance record for a single tracked constant or parameter.

    The `value` field mirrors the live constant in its owning module.
    It is stored here for reference only — the owning module remains the
    single source of truth at runtime. Do not import from here to drive logic.
    """
    parameter: str          # Exact name as defined in the owning module
    value: float            # Mirror of the current live value (informational)
    evidence_level: str     # STRONG / MODERATE / HEURISTIC
    population: str         # ELITE / RECREATIONAL / MASTER / MIXED
    source: str             # Author (year). Journal. Citation details.
    rationale: str          # Why this specific value was chosen
    policy_note: str | None = None   # Deviations, caveats, calibration path
    promoted_from_level: str | None = None  # Prior evidence level, if promoted
    promotion_evidence_count: int | None = None  # Paired outcomes backing promotion
    promotion_date: str | None = None  # YYYY-MM-DD date promotion was approved


# ──────────────────────────────────────────────────────────────────────────────
# Registry — entries for constants across all owning modules (thresholds.py
# and others); one entry per tracked parameter
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

    # ── HRV rolling-baseline drift detector (HD-01 / INV-06) ─────────────────
    'HRV_DRIFT_THRESHOLD_MS': ThresholdEvidence(
        parameter='HRV_DRIFT_THRESHOLD_MS',
        value=8.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source=(
            'Kiviniemi et al. (2007) Eur J Appl Physiol 101(6):743–751; '
            'Plews et al. (2013) Int J Sports Physiol Perform 8(5):512–521'
        ),
        rationale=(
            'The 8ms threshold represents a clinically meaningful chronic shift in '
            'HRV rolling baseline. Unlike the per-cycle HARD_STOP_HRV_DELTA (15ms), '
            'this detector operates on 14-day windows to catch gradual multi-day '
            'deterioration that stays below the acute hard-stop threshold each day '
            'but represents a physiologically significant cumulative trend. '
            'The 8ms value sits at roughly half the hard-stop delta and corresponds '
            'to approximately one standard deviation of inter-day HRV variability '
            'in endurance athletes.'
        ),
        policy_note=(
            'HEURISTIC: the 8ms/14-day window pairing is a conservative heuristic. '
            'No published calibration study validates this exact threshold-window '
            'combination. Calibration path: correlate drift-warning events with '
            'athlete-reported recovery outcome and subsequent performance decline '
            'over the following 7 days.'
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

    # ── Banister model windows: CTL/ATL EMA decay constants ──────────────────
    'CTL_DECAY_DAYS': ThresholdEvidence(
        parameter='CTL_DECAY_DAYS',
        value=42,
        evidence_level='STRONG',
        population='MIXED',
        source=(
            'Banister et al. (1975) Aust J Sports Med 7(3):57–61; '
            'Coggan (2003) Training and Racing with a Power Meter '
            '(PMC implementation guidance)'
        ),
        rationale=(
            'A 42-day EMA is the canonical CTL horizon in the Banister/PMC model, '
            'representing chronic fitness adaptation. Centralizing this value '
            'prevents semantic drift between CTL/ATL producers and consumers.'
        ),
        policy_note=(
            'STRONG for the model convention. Individual athlete optimization '
            'may later tune this value, but all runtime components must share '
            'a single canonical source.'
        ),
    ),

    'ATL_DECAY_DAYS': ThresholdEvidence(
        parameter='ATL_DECAY_DAYS',
        value=7,
        evidence_level='STRONG',
        population='MIXED',
        source=(
            'Banister et al. (1975) Aust J Sports Med 7(3):57–61; '
            'Coggan (2003) Training and Racing with a Power Meter '
            '(PMC implementation guidance)'
        ),
        rationale=(
            'A 7-day EMA is the canonical ATL horizon in the Banister/PMC model, '
            'capturing acute fatigue. Keeping the value centralized ensures '
            'consistent CTL/ATL/TSB behaviour across modules.'
        ),
        policy_note=(
            'STRONG for the model convention. Value changes, if ever approved, '
            'must be propagated via thresholds.py only.'
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

    # ── Physiological Bounds (ADR-0023, T1-18) ────────────────────────────────
    # These bounds are INPUT SANITY GUARDS, not governance thresholds.
    # They live in titan/science/physiological_bounds.BOUNDS at runtime.
    # Evidence level: HEURISTIC for all — plausibility ranges without specific
    # RCT validation. Promote to MODERATE when OutcomeTracker confirms ≥100
    # sessions with no false-positive clamp/null events.

    'PHYS_BOUNDS_HRV_MS': ThresholdEvidence(
        parameter='PHYS_BOUNDS_HRV_MS',
        value=0.1,  # lo bound; hi = 300.0 (see physiological_bounds.BOUNDS)
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — derived from published RMSSD normative ranges (Shaffer & Ginsberg 2017; Makivic 2013).',
        rationale=(
            'RMSSD range [0.1, 300.0] ms. Floor 0.1 excludes sensor-zero (zero HRV = '
            'Garmin optical failure, not physiology). Ceiling 300.0 ms exceeds the highest '
            'published healthy-athlete RMSSD (~250 ms); values above this indicate artefact. '
            'These are plausibility guards — not threshold triggers.'
        ),
        policy_note='HEURISTIC. Promote to MODERATE when ≥100 sessions confirm no false-positive nulling.',
    ),

    'PHYS_BOUNDS_RHR_BPM': ThresholdEvidence(
        parameter='PHYS_BOUNDS_RHR_BPM',
        value=25.0,  # lo bound; hi = 120.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — floor from elite endurance athlete records; ceiling from clinical artefact observation.',
        rationale=(
            'RHR range [25, 120] bpm. Floor 25 bpm is the lowest reliably recorded resting HR '
            'in elite endurance athletes (Miguel Indurain ~28 bpm). Values below 25 are optical '
            'artefact. Ceiling 120 bpm is a clinical threshold above which an optically-read '
            '"resting HR" is almost certainly a measurement error (motion artefact).'
        ),
        policy_note='HEURISTIC. Promote to MODERATE when ≥100 sessions confirm no false-positive clamps.',
    ),

    'PHYS_BOUNDS_CTL': ThresholdEvidence(
        parameter='PHYS_BOUNDS_CTL',
        value=0.0,  # lo bound; hi = 300.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — Coggan (2003) TSS model; 300 TSS/day exceeds documented elite peak loads.',
        rationale=(
            'CTL range [0.0, 300.0] TSS/day. Floor 0.0 is correct for new athletes. '
            'Ceiling 300.0 exceeds any documented sustained CTL in competitive endurance '
            'athletes (~180 TSS/day elite peak); values above this signal data corruption '
            'rather than physiology.'
        ),
        policy_note='HEURISTIC. Not a governance gate — input sanity only.',
    ),

    'PHYS_BOUNDS_ATL': ThresholdEvidence(
        parameter='PHYS_BOUNDS_ATL',
        value=0.0,  # lo bound; hi = 500.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — ATL ceiling set higher than CTL ceiling to allow for acute race/training peaks.',
        rationale=(
            'ATL range [0.0, 500.0] TSS/day. Higher ceiling than CTL because ATL is a 7-day '
            'EMA and can spike significantly during race week or training blocks. 500 is a '
            'conservative artefact ceiling — no documented athlete has sustained 500 TSS/day '
            'even in a 7-day race week.'
        ),
        policy_note='HEURISTIC. Not a governance gate — input sanity only.',
    ),

    'PHYS_BOUNDS_ACWR': ThresholdEvidence(
        parameter='PHYS_BOUNDS_ACWR',
        value=0.0,  # lo bound; hi = 3.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — consistent with Gabbett (2016) ACWR framework; ceiling caps division artefacts.',
        rationale=(
            'ACWR range [0.0, 3.0]. Floor 0.0 is correct when CTL = 0 (new athlete). '
            'Ceiling 3.0 is 2.3× the VO2_ACWR_MAX governance threshold (1.30); values '
            'above 3.0 indicate data corruption rather than a real load spike.'
        ),
        policy_note='HEURISTIC. See VO2_ACWR_MIN/MAX in thresholds.py for governance gate values.',
    ),

    'PHYS_BOUNDS_GLYCOGEN_DEBT': ThresholdEvidence(
        parameter='PHYS_BOUNDS_GLYCOGEN_DEBT',
        value=0.0,  # lo bound; hi = 20.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — negative glycogen debt is logically impossible; ceiling is 2.86× the VO2_GLYCOGEN_DEBT_MAX governance threshold.',
        rationale=(
            'Glycogen debt range [0.0, 20.0]. Negative values are a calorie-accounting '
            'error (logically impossible). Ceiling 20.0 is 2.86× the VO2_GLYCOGEN_DEBT_MAX '
            'gate (7.0); values above 20 indicate data corruption.'
        ),
        policy_note='HEURISTIC. Not a governance gate — input sanity only.',
    ),

    'PHYS_BOUNDS_TEMPERATURE_C': ThresholdEvidence(
        parameter='PHYS_BOUNDS_TEMPERATURE_C',
        value=-40.0,  # lo bound; hi = 55.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — operational climate range covering training locations from subarctic to desert.',
        rationale=(
            'Temperature range [-40.0, 55.0] °C. Covers all realistic outdoor training '
            'environments. Values outside this range indicate weather API failures or '
            'unit conversion errors (e.g., Fahrenheit returned where Celsius expected).'
        ),
        policy_note='HEURISTIC. Not a governance gate — input sanity only.',
    ),

    'PHYS_BOUNDS_DEW_POINT_C': ThresholdEvidence(
        parameter='PHYS_BOUNDS_DEW_POINT_C',
        value=-40.0,  # lo bound; hi = 40.0
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — dew point cannot exceed ambient temperature and is bounded by physical thermodynamics.',
        rationale=(
            'Dew point range [-40.0, 40.0] °C. A dew point above 40°C is physically '
            'impossible at sea level (would require near-100% humidity at 40°C ambient). '
            'Values outside range indicate API error.'
        ),
        policy_note='HEURISTIC. Not a governance gate — input sanity only.',
    ),

    # ── Data freshness thresholds — ADR-0026 / T1-19 ─────────────────────────

    'STALE_DATA_WARN_HOURS': ThresholdEvidence(
        parameter='STALE_DATA_WARN_HOURS',
        value=24.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — ADR-0026 §3 (Layer 2 temporal freshness check).',
        rationale=(
            '24 hours is the natural Garmin sync cadence (6h background + manual). '
            'If the last sync timestamp is >24 h old the system is operating on data '
            'that is at least one training day stale. A warning is emitted but '
            'coaching output is not degraded.'
        ),
        policy_note='HEURISTIC. Calibration path: review how often 24 h staleness coincides with degraded coaching accuracy via OutcomeTracker.',
    ),

    'STALE_DATA_HARD_CEILING_HOURS': ThresholdEvidence(
        parameter='STALE_DATA_HARD_CEILING_HOURS',
        value=72.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal — ADR-0026 §3 (Layer 2 temporal freshness check).',
        rationale=(
            '72 hours (3 days) of sync gap means at least 2 training days are untracked. '
            'CTL/ATL calculations will be materially incorrect, and HRV baseline will be '
            'stale. The system sets data_confidence_low=True at this threshold, which '
            'flows into the governance context and degrades intensity prescriptions '
            'via the T2-10 advisory mechanism.'
        ),
        policy_note='HEURISTIC. 72 h is a policy decision; promote to MODERATE after validating governance accuracy on stale-data days via OutcomeTracker.',
    ),

    'ILLNESS_PATTERN_HRV_DELTA': ThresholdEvidence(
        parameter='ILLNESS_PATTERN_HRV_DELTA',
        value=20.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal policy threshold for illness-pattern partition (ADR-0037).',
        rationale='20% HRV drop is used as a conservative illness-signal boundary to separate likely non-training stress responses from normal post-load noise.',
        policy_note='HEURISTIC. Promote when classified illness-pattern days are validated against symptom logs and training outcomes.',
    ),

    'ILLNESS_PATTERN_RHR_DELTA': ThresholdEvidence(
        parameter='ILLNESS_PATTERN_RHR_DELTA',
        value=10.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal policy threshold for illness-pattern partition (ADR-0037).',
        rationale='10 bpm RHR elevation complements the HRV illness threshold and requires dual convergence before illness-pattern gating is applied.',
        policy_note='HEURISTIC. Promote when retrospective labeling confirms precision/recall of illness-pattern classification.',
    ),

    'GARMIN_DATA_MAX_AGE_HOURS': ThresholdEvidence(
        parameter='GARMIN_DATA_MAX_AGE_HOURS',
        value=26.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal resilience policy — ADR-0030 external data source freshness gate.',
        rationale='26 hours allows expected daily sync cadence plus operational slack before data is treated as too old for high-confidence governance.',
        policy_note='HEURISTIC. Calibrate using observed sync-latency distribution and downstream coaching accuracy impact.',
    ),

    'GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT': ThresholdEvidence(
        parameter='GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT',
        value=3.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal API resilience policy — ADR-0050 Garmin fragility mitigation.',
        rationale='Three consecutive sync failures distinguish a transient outage from a non-transient provider degradation event requiring operator notification.',
        policy_note='HEURISTIC. Calibrate using observed Garmin outage duration distribution; promote once field data covers at least 10 distinct outage episodes.',
    ),

    'OUTCOME_INDEPENDENCE_WINDOW_DAYS': ThresholdEvidence(
        parameter='OUTCOME_INDEPENDENCE_WINDOW_DAYS',
        value=2.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal feedback-loop integrity policy — ADR-0035.',
        rationale='A 2-day independence window reduces circular validation between recommendation generation and near-immediate outcome scoring.',
        policy_note='HEURISTIC. Promote after evaluating leakage rate in OutcomeTracker calibration audits.',
    ),

    'CALIBRATION_MAX_THRESHOLD_DELTA_PCT': ThresholdEvidence(
        parameter='CALIBRATION_MAX_THRESHOLD_DELTA_PCT',
        value=0.10,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal calibration safety guardrail — ADR-0035.',
        rationale='Per-update threshold adjustments are capped at ±10% to prevent unstable oscillations from sparse outcome data.',
        policy_note='HEURISTIC. Revisit once long-horizon calibration traces show stable convergence under controlled A/B replay.',
    ),

    'CALIBRATION_MIN_OUTCOME_COUNT': ThresholdEvidence(
        parameter='CALIBRATION_MIN_OUTCOME_COUNT',
        value=10.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal calibration sample-size guardrail — ADR-0035.',
        rationale='At least 10 outcome samples are required before any threshold calibration to avoid fitting to anecdotal noise.',
        policy_note='HEURISTIC. Promote when empirical variance analysis supports an evidence-based minimum sample threshold.',
    ),

    'GARMIN_DATA_SUSPECT_AGE_HOURS': ThresholdEvidence(
        parameter='GARMIN_DATA_SUSPECT_AGE_HOURS',
        value=12.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Unified data trust contract policy — ADR-0041.',
        rationale='Data older than 12 hours is marked suspect for trust scoring, enabling advisory degradation without immediate hard lock.',
        policy_note='HEURISTIC. Tune with observed trust-level false-positive rates across normal sync delays.',
    ),

    'WEATHER_DATA_SUSPECT_AGE_HOURS': ThresholdEvidence(
        parameter='WEATHER_DATA_SUSPECT_AGE_HOURS',
        value=2.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Unified data trust contract policy — ADR-0041.',
        rationale='Weather volatility makes forecasts older than 2 hours materially less reliable for environmental stress decisions.',
        policy_note='HEURISTIC. Recalibrate with forecast error deltas versus age in production weather snapshots.',
    ),

    'ADAPTIVE_MEMORY_EASY_PACE_DROP_MULTIPLIER': ThresholdEvidence(
        parameter='ADAPTIVE_MEMORY_EASY_PACE_DROP_MULTIPLIER',
        value=1.08,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal AdaptiveMemory policy threshold (T5-18 Category A extraction).',
        rationale='Easy-pace slowdown greater than 8% versus baseline is treated as a mechanical-load stress proxy requiring caution.',
        policy_note='HEURISTIC. Promote when OutcomeTracker supports athlete-level precision/recall for easy-pace-drop risk signaling.',
    ),

    'ADAPTIVE_MEMORY_HOURS_24': ThresholdEvidence(
        parameter='ADAPTIVE_MEMORY_HOURS_24',
        value=24.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal AdaptiveMemory recovery-window boundary policy (T5-18 Category A extraction).',
        rationale='24 hours is the lower boundary for recovery and spacing advisories in AdaptiveMemory window checks.',
        policy_note='HEURISTIC. Shared time-window boundary centralization policy constant.',
    ),

    'ADAPTIVE_MEMORY_HOURS_36': ThresholdEvidence(
        parameter='ADAPTIVE_MEMORY_HOURS_36',
        value=36.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal AdaptiveMemory session-density policy boundary (T5-18 Category A extraction).',
        rationale='36 hours marks the downgrade-intensity caution boundary for recent quality session spacing.',
        policy_note='HEURISTIC. Shared time-window boundary centralization policy constant.',
    ),

    'ADAPTIVE_MEMORY_HOURS_48': ThresholdEvidence(
        parameter='ADAPTIVE_MEMORY_HOURS_48',
        value=48.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal AdaptiveMemory recovery/peak transition policy boundary (T5-18 Category A extraction).',
        rationale='48 hours separates recovery from supercompensation-peak classification and cautionary spacing messaging.',
        policy_note='HEURISTIC. Shared time-window boundary centralization policy constant.',
    ),

    'ADAPTIVE_MEMORY_HOURS_72': ThresholdEvidence(
        parameter='ADAPTIVE_MEMORY_HOURS_72',
        value=72.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal AdaptiveMemory supercompensation upper-bound policy (T5-18 Category A extraction).',
        rationale='72 hours is the upper limit for supercompensation peak labeling before baseline classification resumes.',
        policy_note='HEURISTIC. Shared time-window boundary centralization policy constant.',
    ),


    'INTENSITY_GOVERNOR_DRIFT_YELLOW': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_DRIFT_YELLOW',
        value=3.5,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='Cardiac drift above 3.5% is treated as early intensity-governor caution signaling.',
        policy_note='HEURISTIC governance-facing yellow boundary for drift risk escalation.',
    ),

    'INTENSITY_GOVERNOR_DRIFT_RED': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_DRIFT_RED',
        value=5.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='Cardiac drift above 5.0% triggers red intensity-governor restriction.',
        policy_note='HEURISTIC governance-facing red boundary for drift risk escalation.',
    ),

    'INTENSITY_GOVERNOR_GLYCOGEN_YELLOW': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_GLYCOGEN_YELLOW',
        value=4.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='Glycogen debt at or above 4.0 is treated as a yellow caution boundary.',
        policy_note='HEURISTIC policy boundary for glycogen-related caution signals.',
    ),

    'INTENSITY_GOVERNOR_GLYCOGEN_RED': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_GLYCOGEN_RED',
        value=6.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='Glycogen debt above 6.0 triggers red intensity-governor restriction.',
        policy_note='HEURISTIC policy boundary for severe glycogen debt signal escalation.',
    ),

    'INTENSITY_GOVERNOR_ACWR_YELLOW': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_ACWR_YELLOW',
        value=1.3,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='ACWR above 1.3 is treated as a yellow caution boundary for load-spike risk.',
        policy_note='HEURISTIC policy boundary aligned with conservative load-governance practice.',
    ),

    'INTENSITY_GOVERNOR_ACWR_RED': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_ACWR_RED',
        value=1.5,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='ACWR above 1.5 triggers red intensity-governor restriction for elevated risk.',
        policy_note='HEURISTIC policy boundary for high load-spike risk condition.',
    ),

    'INTENSITY_GOVERNOR_READINESS_YELLOW': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_READINESS_YELLOW',
        value=55.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='Readiness below 55 shifts governance to yellow caution to reduce intensity.',
        policy_note='HEURISTIC readiness caution floor for intensity governance.',
    ),

    'INTENSITY_GOVERNOR_READINESS_RED': ThresholdEvidence(
        parameter='INTENSITY_GOVERNOR_READINESS_RED',
        value=40.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal IntensityGovernor policy threshold (T5-31 Category A extraction).',
        rationale='Readiness below 40 triggers red restriction and easy-session override.',
        policy_note='HEURISTIC readiness hard floor for intensity governance.',
    ),

    'INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE': ThresholdEvidence(
        parameter='INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE',
        value=0.7,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Conservative-fail default per ADR-0051; applied when intensity gate fires but volume_modifier key is absent from gate payload.',
        rationale='A 30% volume reduction is the conservative fallback when the gate payload is incomplete. Absent modifier on a flagged gate must not silently pass full volume (optimistic default eliminated per ADR-0051/INV-05).',
        policy_note='HEURISTIC policy constant; not derived from population data. Recalibrate via OutcomeTracker if conservative ceiling proves too restrictive.',
    ),

    'VLG_TSB_YELLOW_MIN': ThresholdEvidence(
        parameter='VLG_TSB_YELLOW_MIN',
        value=-30.0,
        evidence_level='MODERATE',
        population='MIXED',
        source='Coggan performance management chart interpretation adopted for VLG warning-band policy (T5-35 Category A extraction).',
        rationale='TSB at or below -30 marks the VLG yellow load-band boundary before hard-stop red threshold at HARD_STOP_TSB_FLOOR.',
        policy_note='MODERATE policy threshold; warning-band boundary should be recalibrated with cohort fatigue outcomes.',
    ),

    'VLG_ACWR_RED_MIN': ThresholdEvidence(
        parameter='VLG_ACWR_RED_MIN',
        value=0.7,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal VLG low-load red-band policy boundary (T5-35 Category A extraction).',
        rationale='ACWR below 0.7 is treated as red due to severe under-load / detraining risk band in VLG.',
        policy_note='HEURISTIC lower red boundary for VLG ACWR banding.',
    ),

    'VLG_ACWR_YELLOW_MIN': ThresholdEvidence(
        parameter='VLG_ACWR_YELLOW_MIN',
        value=0.8,
        evidence_level='MODERATE',
        population='MIXED',
        source='Gabbett (2016) load-band conventions translated to VLG caution range (T5-35 Category A extraction).',
        rationale='ACWR below 0.8 enters VLG yellow caution band before red under-load boundary.',
        policy_note='MODERATE policy boundary aligned with common ACWR detraining-risk interpretation.',
    ),

    'VLG_ACWR_YELLOW_MAX': ThresholdEvidence(
        parameter='VLG_ACWR_YELLOW_MAX',
        value=1.3,
        evidence_level='MODERATE',
        population='MIXED',
        source='Gabbett (2016) conservative safe-band upper boundary adapted for VLG caution model (T5-35 Category A extraction).',
        rationale='ACWR above 1.3 enters VLG yellow caution band, indicating elevated spike risk versus green range.',
        policy_note='MODERATE policy boundary harmonized with conservative load-spike governance.',
    ),

    'VLG_ACWR_RED_MAX': ThresholdEvidence(
        parameter='VLG_ACWR_RED_MAX',
        value=1.5,
        evidence_level='MODERATE',
        population='MIXED',
        source='Gabbett (2016) elevated-risk load band translated to VLG red policy boundary (T5-35 Category A extraction).',
        rationale='ACWR above 1.5 is classified red in VLG due to high load-spike risk.',
        policy_note='MODERATE policy boundary for high-risk ACWR escalation in VLG.',
    ),

    'VLG_GLYCOGEN_YELLOW_MIN': ThresholdEvidence(
        parameter='VLG_GLYCOGEN_YELLOW_MIN',
        value=4.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal glycogen debt accumulator policy threshold for VLG caution band (T5-35 Category A extraction).',
        rationale='Glycogen debt at or above 4.0 enters VLG yellow caution state.',
        policy_note='HEURISTIC warning threshold pending outcome-linked calibration.',
    ),

    'VLG_GLYCOGEN_RED_MIN': ThresholdEvidence(
        parameter='VLG_GLYCOGEN_RED_MIN',
        value=7.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal glycogen debt accumulator policy threshold for VLG red band (T5-35 Category A extraction).',
        rationale='Glycogen debt at or above 7.0 triggers VLG red state for severe depletion risk.',
        policy_note='HEURISTIC hard boundary aligned with VO2_GLYCOGEN_DEBT_MAX governance ceiling.',
    ),

    'FATIGUE_SORENESS_PERIPHERAL_MIN': ThresholdEvidence(
        parameter='FATIGUE_SORENESS_PERIPHERAL_MIN',
        value=5.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal FatigueEngine policy threshold (T5-28 Category A extraction).',
        rationale='Soreness score at or above 5 marks peripheral fatigue contribution in classification output.',
        policy_note='HEURISTIC governance-facing threshold for peripheral fatigue tagging.',
    ),

    'GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD': ThresholdEvidence(
        parameter='GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD',
        value=0.80,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal GovernanceEngine policy threshold (T5-30 Category A extraction).',
        rationale='Override ratio above 80% over 14 days indicates plan-integrity breakdown and triggers conservative quality-session lockdown.',
        policy_note='HEURISTIC governance control threshold pending outcome-linked override efficacy calibration.',
    ),

    'GOVERNANCE_CS_CONFIDENCE_THRESHOLD': ThresholdEvidence(
        parameter='GOVERNANCE_CS_CONFIDENCE_THRESHOLD',
        value=0.70,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal GovernanceEngine policy threshold (T5-30 Category A extraction).',
        rationale='Critical speed confidence below 70% indicates inadequate calibration quality for race-simulation guidance.',
        policy_note='HEURISTIC confidence quality floor; tune with calibration success and downstream prediction error.',
    ),

    'DURABILITY_PACE_DECAY_EXCELLENT_MAX': ThresholdEvidence(
        parameter='DURABILITY_PACE_DECAY_EXCELLENT_MAX',
        value=2.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal DurabilityEngine policy banding (T5-27 Category A extraction).',
        rationale='Upper bound for excellent pace-fade classification in durability assessment output.',
        policy_note='HEURISTIC governance-facing threshold; calibrate with race-outcome decay cohorts.',
    ),

    'DURABILITY_PACE_DECAY_GOOD_MAX': ThresholdEvidence(
        parameter='DURABILITY_PACE_DECAY_GOOD_MAX',
        value=5.0,
        evidence_level='MODERATE',
        population='MIXED',
        source='Durability literature summary (Maunder et al. 2021; Spragg et al. 2023) translated into policy bands.',
        rationale='Upper bound for good pace-fade classification before moderate fade warning.',
        policy_note='MODERATE: policy boundary aligned with common endurance fade interpretation.',
    ),

    'DURABILITY_PACE_DECAY_MODERATE_MAX': ThresholdEvidence(
        parameter='DURABILITY_PACE_DECAY_MODERATE_MAX',
        value=8.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal DurabilityEngine policy banding (T5-27 Category A extraction).',
        rationale='Upper bound for moderate fade classification before poor-durability warning.',
        policy_note='HEURISTIC policy split; review against cohort durability outcomes.',
    ),

    'DURABILITY_INDEX_DEVELOPING_MIN': ThresholdEvidence(
        parameter='DURABILITY_INDEX_DEVELOPING_MIN',
        value=85.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal Durability Index policy ladder (T5-27 Category A extraction).',
        rationale='Lower boundary for developing durability tier in DI classification.',
        policy_note='HEURISTIC threshold used for governance-facing durability tier messaging.',
    ),

    'DURABILITY_INDEX_COMPETITIVE_MIN': ThresholdEvidence(
        parameter='DURABILITY_INDEX_COMPETITIVE_MIN',
        value=90.0,
        evidence_level='MODERATE',
        population='MIXED',
        source='Durability performance-maintenance framing from endurance science translated into tier thresholds.',
        rationale='Lower boundary for competitive durability tier in DI classification.',
        policy_note='MODERATE policy threshold; tune with observed race-decay distributions.',
    ),

    'DURABILITY_INDEX_ELITE_MIN': ThresholdEvidence(
        parameter='DURABILITY_INDEX_ELITE_MIN',
        value=95.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal Durability Index policy ladder (T5-27 Category A extraction).',
        rationale='Lower boundary for elite durability tier in DI classification.',
        policy_note='HEURISTIC policy threshold for high durability messaging.',
    ),

    'DURABILITY_INDEX_WORLD_CLASS_MIN': ThresholdEvidence(
        parameter='DURABILITY_INDEX_WORLD_CLASS_MIN',
        value=98.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal Durability Index policy ladder (T5-27 Category A extraction).',
        rationale='Lower boundary for world-class durability tier in DI classification.',
        policy_note='HEURISTIC upper-tier threshold; validate with elite-level longitudinal data.',
    ),

    'DURABILITY_PROTOCOL_BASE_BUILD_MAX': ThresholdEvidence(
        parameter='DURABILITY_PROTOCOL_BASE_BUILD_MAX',
        value=88.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal DurabilityEngine training-protocol ladder (T5-27 Category A extraction).',
        rationale='Upper boundary for base-build protocol assignment.',
        policy_note='HEURISTIC protocol-routing threshold for durability intervention intensity.',
    ),

    'DURABILITY_PROTOCOL_MAINTENANCE_MAX': ThresholdEvidence(
        parameter='DURABILITY_PROTOCOL_MAINTENANCE_MAX',
        value=93.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal DurabilityEngine training-protocol ladder (T5-27 Category A extraction).',
        rationale='Upper boundary for maintenance protocol assignment before strong-durability path.',
        policy_note='HEURISTIC protocol-routing threshold; calibrate with adaptation rates.',
    ),

    'DURABILITY_PROTOCOL_STRONG_MAX': ThresholdEvidence(
        parameter='DURABILITY_PROTOCOL_STRONG_MAX',
        value=96.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal DurabilityEngine training-protocol ladder (T5-27 Category A extraction).',
        rationale='Upper boundary for strong-durability protocol before elite-maintain path.',
        policy_note='HEURISTIC protocol-routing threshold for top-end durability maintenance.',
    ),

    'ACWR_SEVERE_DETRAINING_MAX': ThresholdEvidence(
        parameter='ACWR_SEVERE_DETRAINING_MAX',
        value=0.5,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Policy decision based on ACWR workload banding conventions used in endurance coaching.',
        rationale='Lower boundary for severe detraining classification in ACWR status output.',
        policy_note='HEURISTIC: governance-facing policy threshold pending OutcomeTracker calibration.',
    ),

    'ACWR_DETRAINING_RISK_MAX': ThresholdEvidence(
        parameter='ACWR_DETRAINING_RISK_MAX',
        value=0.8,
        evidence_level='MODERATE',
        population='MIXED',
        source='Gabbett (2016) Br J Sports Med 50(5):273–280; policy boundary for low-load ACWR band.',
        rationale='Upper boundary for detraining risk and lower boundary for maintenance classification.',
        policy_note='MODERATE: ACWR principle is supported; exact cut-point is policy-tuned.',
    ),

    'ACWR_MAINTENANCE_MAX': ThresholdEvidence(
        parameter='ACWR_MAINTENANCE_MAX',
        value=1.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Policy decision for neutral ACWR maintenance banding.',
        rationale='Upper boundary of maintenance classification used by ACWR status and risk score.',
        policy_note='HEURISTIC policy threshold; calibrate against adaptation outcomes by block type.',
    ),

    'ACWR_SWEET_SPOT_MAX': ThresholdEvidence(
        parameter='ACWR_SWEET_SPOT_MAX',
        value=1.3,
        evidence_level='MODERATE',
        population='MIXED',
        source='Gabbett (2016) Br J Sports Med 50(5):273–280; commonly used ACWR upper safe band.',
        rationale='Upper boundary for sweet-spot adaptation zone and moderate-risk onset.',
        policy_note='MODERATE: widely used in load management; monitor cohort-specific false positives.',
    ),

    'ACWR_MODERATE_RISK_MAX': ThresholdEvidence(
        parameter='ACWR_MODERATE_RISK_MAX',
        value=1.5,
        evidence_level='MODERATE',
        population='MIXED',
        source='Gabbett (2016) Br J Sports Med 50(5):273–280; elevated injury risk above ACWR 1.5.',
        rationale='Upper boundary for moderate-risk status before high-risk classification.',
        policy_note='MODERATE: policy threshold with broad literature support for elevated risk band.',
    ),

    'ACWR_HIGH_RISK_MAX': ThresholdEvidence(
        parameter='ACWR_HIGH_RISK_MAX',
        value=1.7,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Policy extension of ACWR risk ladder for injury-risk score gradation.',
        rationale='Upper boundary for high-risk score bucket before extreme-risk classification.',
        policy_note='HEURISTIC band split for scoring granularity; validate with OutcomeTracker incidents.',
    ),


    'LACTATE_LT1_MAX_DRIFT_PCT': ThresholdEvidence(
        parameter='LACTATE_LT1_MAX_DRIFT_PCT',
        value=3.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal LactateLogic LT1 policy boundary (T5-32 Category A extraction).',
        rationale='Upper exclusive drift boundary for LT1 zone detection in estimate_lt1().',
        policy_note='HEURISTIC policy threshold pending cohort calibration with paired lactate and drift data.',
    ),

    'LACTATE_LT1_MAX_HR_PCT': ThresholdEvidence(
        parameter='LACTATE_LT1_MAX_HR_PCT',
        value=78.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal LactateLogic LT1 policy boundary (T5-32 Category A extraction).',
        rationale='Upper inclusive heart-rate percent boundary for LT1 zone detection in estimate_lt1().',
        policy_note='HEURISTIC policy threshold for aerobic-zone messaging; validate against field lactate testing.',
    ),

    'LACTATE_LT2_MIN_RPE': ThresholdEvidence(
        parameter='LACTATE_LT2_MIN_RPE',
        value=6.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal LactateLogic LT2 policy boundary (T5-32 Category A extraction).',
        rationale='Lower inclusive RPE boundary for LT2 approximation in estimate_lt2().',
        policy_note='HEURISTIC policy threshold based on CR10 tempo-zone interpretation; calibrate with outcomes.',
    ),

    'LACTATE_LT2_MAX_RPE': ThresholdEvidence(
        parameter='LACTATE_LT2_MAX_RPE',
        value=7.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Internal LactateLogic LT2 policy boundary (T5-32 Category A extraction).',
        rationale='Upper inclusive RPE boundary for LT2 approximation in estimate_lt2().',
        policy_note='HEURISTIC policy threshold for threshold-zone classification pending cohort-specific validation.',
    ),

    'ESI_MODERATE_MIN': ThresholdEvidence(
        parameter='ESI_MODERATE_MIN',
        value=16.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='T5-14 ESI policy model: composite environmental stress score (temperature + 0.5*dew point).',
        rationale='Lower bound for beginning pace-compensation guidance under mild environmental stress.',
        policy_note='HEURISTIC. Calibrate against cohort-specific heat-strain response and completion quality.',
    ),

    'ESI_HIGH_MIN': ThresholdEvidence(
        parameter='ESI_HIGH_MIN',
        value=22.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='T5-14 ESI policy model: composite environmental stress score (temperature + 0.5*dew point).',
        rationale='Boundary for high stress where stronger pace compensation is required.',
        policy_note='HEURISTIC. Tune after accumulating telemetry for heat/pace divergence under comparable workloads.',
    ),

    'ESI_EXTREME_MIN': ThresholdEvidence(
        parameter='ESI_EXTREME_MIN',
        value=28.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='T5-14 ESI policy model: composite environmental stress score (temperature + 0.5*dew point).',
        rationale='Boundary for extreme stress; VO2 work is blocked by governance V4 safety condition.',
        policy_note='HEURISTIC safety threshold. Review against adverse-outcome rate and false-positive lock frequency.',
    ),

    'ESI_PACE_ADJUSTMENT_MODERATE_SEC_PER_KM': ThresholdEvidence(
        parameter='ESI_PACE_ADJUSTMENT_MODERATE_SEC_PER_KM',
        value=8,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='T5-14 ESI policy calibration seed (moderate stress pace compensation).',
        rationale='Baseline pace reduction to preserve internal load under moderate ESI.',
        policy_note='HEURISTIC. Adjust with athlete-specific response profiles from post-run strain markers.',
    ),

    'ESI_PACE_ADJUSTMENT_HIGH_SEC_PER_KM': ThresholdEvidence(
        parameter='ESI_PACE_ADJUSTMENT_HIGH_SEC_PER_KM',
        value=15,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='T5-14 ESI policy calibration seed (high stress pace compensation).',
        rationale='Higher pace reduction for high ESI to maintain intended zone distribution.',
        policy_note='HEURISTIC. Calibrate with quality-session completion and post-session recovery drift.',
    ),

    'ESI_PACE_ADJUSTMENT_EXTREME_SEC_PER_KM': ThresholdEvidence(
        parameter='ESI_PACE_ADJUSTMENT_EXTREME_SEC_PER_KM',
        value=25,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='T5-14 ESI policy calibration seed (extreme stress pace compensation).',
        rationale='Maximal pace reduction recommendation used in Telegram guidance during extreme ESI.',
        policy_note='HEURISTIC conservative guardrail; reassess after heat-event telemetry review.',
    ),

    'ESI_DEW_POINT_FALLBACK_C': ThresholdEvidence(
        parameter='ESI_DEW_POINT_FALLBACK_C',
        value=18.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source=(
            'T5-68 / ADR-0034 / ADR-0051. '
            'Aligned with WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C (18.0°C) — the lower '
            'boundary of the uncomfortable dew-point band per NOAA/NWS operational guidance.'
        ),
        rationale=(
            'When dew_point is absent from weather data, the ESI composite score '
            '(temperature_c + 0.5 * dew_point_c) must not silently underestimate thermal '
            'stress. Defaulting to 12.0°C (the comfortable band) would suppress ESI '
            'modifiers when data is unknown. 18.0°C is the conservative-fail choice: '
            'it is the minimum value at which humidity begins to affect perceived exertion, '
            'consistent with ADR-0051 missing-data policy (optimistic defaults eliminated).'
        ),
        policy_note=(
            'HEURISTIC — value equals WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C intentionally. '
            'Calibrate with session-outcome data once dew_point telemetry coverage improves. '
            'Do not set below WEATHER_DEW_POINT_COMFORTABLE_MIN_C (12.0°C).'
        ),
    ),


    'WEATHER_DEW_POINT_EXTREME_MIN_C': ThresholdEvidence(
        parameter='WEATHER_DEW_POINT_EXTREME_MIN_C',
        value=24.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='NOAA/NWS operational dew-point comfort advisories adapted for training safety messaging (T5-41 extraction).',
        rationale='Exclusive lower bound where conditions are treated as extreme and training avoidance is recommended.',
        policy_note='HEURISTIC policy boundary for conservative athlete guidance; calibrate with heat-strain outcomes.',
    ),

    'WEATHER_DEW_POINT_OPPRESSIVE_MIN_C': ThresholdEvidence(
        parameter='WEATHER_DEW_POINT_OPPRESSIVE_MIN_C',
        value=21.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Operational meteorology dew-point comfort bands (T5-41 extraction).',
        rationale='Boundary for oppressive humidity where significant intensity reduction guidance begins.',
        policy_note='HEURISTIC categorization threshold aligned with practical coaching heat-risk communication.',
    ),

    'WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C': ThresholdEvidence(
        parameter='WEATHER_DEW_POINT_UNCOMFORTABLE_MIN_C',
        value=18.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Operational meteorology dew-point comfort bands (T5-41 extraction).',
        rationale='Boundary for uncomfortable conditions used in heat-status messaging and window scoring.',
        policy_note='HEURISTIC threshold pending cohort-specific completion/performance validation.',
    ),

    'WEATHER_DEW_POINT_STICKY_MIN_C': ThresholdEvidence(
        parameter='WEATHER_DEW_POINT_STICKY_MIN_C',
        value=15.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Operational meteorology dew-point comfort bands (T5-41 extraction).',
        rationale='Boundary for sticky humidity where mild pacing penalties are applied.',
        policy_note='HEURISTIC comfort threshold; tune with athlete subjective heat-load reports.',
    ),

    'WEATHER_DEW_POINT_COMFORTABLE_MIN_C': ThresholdEvidence(
        parameter='WEATHER_DEW_POINT_COMFORTABLE_MIN_C',
        value=12.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Operational meteorology dew-point comfort bands (T5-41 extraction).',
        rationale='Boundary separating pleasant/comfortable domain from drier bonus conditions in window scoring.',
        policy_note='HEURISTIC advisory threshold for training comfort messaging.',
    ),

    'WEATHER_DEW_POINT_PLEASANT_MIN_C': ThresholdEvidence(
        parameter='WEATHER_DEW_POINT_PLEASANT_MIN_C',
        value=8.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Operational meteorology dew-point comfort bands (T5-41 extraction).',
        rationale='Boundary above dry/cold classification for pleasant-condition labeling.',
        policy_note='HEURISTIC messaging threshold; retain as policy constant for centralized tuning.',
    ),

    'OPERATOR_TRUST_DRIFT_WARNING_RATE_30D': ThresholdEvidence(
        parameter='OPERATOR_TRUST_DRIFT_WARNING_RATE_30D',
        value=0.25,
        evidence_level='HEURISTIC',
        population='MIXED',
        source='Override rationale protocol policy — ADR-0038.',
        rationale='A 30-day warning threshold at 25% identifies sustained human-vs-system trust drift requiring operational review.',
        policy_note='HEURISTIC. Promote after correlating drift alerts with true governance quality regressions and override quality audits.',
    ),

    # ── API rate-limiter key ceiling — HD-05 / OBS-038 ───────────────────────
    'RATE_LIMITER_MAX_KEYS': ThresholdEvidence(
        parameter='RATE_LIMITER_MAX_KEYS',
        value=10_000.0,
        evidence_level='HEURISTIC',
        population='MIXED',
        source=(
            'Internal capacity model — HD-05 / OBS-038. '
            'No external RCT; derived from per-key memory footprint: '
            'deque of float timestamps at ~8 bytes each, 60-entry max per window, '
            '~500 bytes/key overhead → 10 000 keys ≈ 5 MB peak resident.'
        ),
        rationale=(
            '10 000 unique (user_id, role, endpoint) tuples covers all plausible '
            'concurrent session × endpoint combinations for a single-tenant TITAN '
            'deployment. Beyond this ceiling the marginal key is from an evicted or '
            'rotated identity and LRU eviction has negligible correctness impact: '
            'the evicted key simply restarts its window on next access.'
        ),
        policy_note=(
            'HEURISTIC. Calibration path: monitor limiter_eviction event frequency '
            'in production. If evictions occur on active sessions (not just stale '
            'keys), raise the ceiling in proportion to the observed concurrent-key '
            'count. Do not lower below 1 000 without capacity analysis.'
        ),
    ),
}


METRIC_LIFECYCLE_STATES: frozenset[str] = frozenset({'Active', 'Under Review', 'Deprecated'})

# Metric lifecycle audit registry (ADR-0039 / T2-17).
#
# Governance gates use lock-code taxonomy: H1-H4 (hard stops), C1 (composite),
# V1-V5 (VO2 eligibility), IG-YELLOW/IG-RED (intensity governor overlays).
METRIC_LIFECYCLE: dict[str, dict[str, object]] = {
    'hrv_delta_ms': {
        'state': 'Active',
        'governance_gates': ['H1', 'C1'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'rhr_delta_bpm': {
        'state': 'Active',
        'governance_gates': ['H1', 'C1'],
        'telegram_briefing': False,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'readiness_score': {
        'state': 'Active',
        'governance_gates': ['V2', 'C1'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'sleep_score': {
        'state': 'Active',
        'governance_gates': ['C1'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'subjective_fatigue_score': {
        'state': 'Active',
        'governance_gates': ['H4', 'C1'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'fatigue_level': {
        'state': 'Active',
        'governance_gates': ['V5', 'IG-YELLOW', 'IG-RED'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'glycogen_debt': {
        'state': 'Active',
        'governance_gates': ['C1', 'V3', 'IG-YELLOW', 'IG-RED'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'acwr': {
        'state': 'Active',
        'governance_gates': ['V1'],
        'telegram_briefing': False,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'days_since_last_vo2': {
        'state': 'Active',
        'governance_gates': ['V4'],
        'telegram_briefing': False,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'fueling_confirmed': {
        'state': 'Active',
        'governance_gates': ['V5'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'tsb': {
        'state': 'Active',
        'governance_gates': ['IG-YELLOW', 'IG-RED'],
        'telegram_briefing': True,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'drift_pct': {
        'state': 'Active',
        'governance_gates': ['IG-YELLOW', 'IG-RED'],
        'telegram_briefing': False,
        'operator_console_payload': True,
        'evidence_registry_entry': True,
    },
    'trimp': {
        'state': 'Under Review',
        'governance_gates': [],
        'telegram_briefing': False,
        'operator_console_payload': False,
        'evidence_registry_entry': False,
    },
    'efficiency_index': {
        'state': 'Under Review',
        'governance_gates': [],
        'telegram_briefing': False,
        'operator_console_payload': False,
        'evidence_registry_entry': False,
    },
    'biomechanics_score': {
        'state': 'Under Review',
        'governance_gates': [],
        'telegram_briefing': False,
        'operator_console_payload': False,
        'evidence_registry_entry': False,
    },
    'durability_score': {
        'state': 'Under Review',
        'governance_gates': [],
        'telegram_briefing': False,
        'operator_console_payload': False,
        'evidence_registry_entry': False,
    },
}


def get_metrics_under_review() -> list[str]:
    """Return audited metrics whose lifecycle state is `Under Review`."""
    return [
        name
        for name, metadata in METRIC_LIFECYCLE.items()
        if metadata.get('state') == 'Under Review'
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_evidence(parameter: str) -> ThresholdEvidence | None:
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
        if v.evidence_level == 'HEURISTIC' or v.evidence_level == 'MODERATE' and 'internal' in v.source.lower():
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
