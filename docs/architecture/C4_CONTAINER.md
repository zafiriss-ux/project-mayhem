# C4 Container Diagram — TITAN OS

**Level:** C4 Level 2 (Container)
**Version:** 1.0
**Date:** 2026-03-29
**Status:** Current (v5.8.0)

This document describes the container-level architecture of TITAN OS using C4 model
conventions. Diagrams are expressed in textual form; a rendered SVG can be generated
from the PlantUML source below.

---

## System Context (C4 Level 1 Summary)

```
[Athlete] ──────────────────────► [TITAN OS]
                                      │
                     ┌────────────────┼──────────────────┐
                     ▼                ▼                  ▼
             [Garmin Connect]  [Open-Meteo API]  [Telegram Bot API]
```

- **Athlete** interacts via Telegram messages.
- **TITAN OS** is a single self-hosted Python process.
- **Garmin Connect** provides biometric and training data (OAuth).
- **Open-Meteo** provides weather data (no key required).
- **Telegram Bot API** delivers coaching messages and receives commands.

---

## Container Diagram (C4 Level 2)

```
┌──────────────────────────────────────────────────────────────────────┐
│  TITAN OS Process (Python 3.11+, single host)                        │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Orchestration Layer                                         │    │
│  │  DailyCoach v5.8 (titan/orchestration/daily_coach.py)       │    │
│  │  12-step morning routine · cron scheduler · effect runner   │    │
│  └────────────────────────┬────────────────────────────────────┘    │
│                            │ calls                                   │
│  ┌─────────────────────────┼──────────────────────────────────┐     │
│  │  Science Layer           │                                  │     │
│  │                          ▼                                  │     │
│  │  ┌─────────────────────────────────────────────────────┐   │     │
│  │  │  Governance Engine (7-gate pipeline)                │   │     │
│  │  │  titan/science/governance_engine.py                 │   │     │
│  │  └─────────────────────────────────────────────────────┘   │     │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │     │
│  │  │ HRV Engine    │  │ TSB/CTL/ATL   │  │ ACWR Engine   │   │     │
│  │  │ Readiness     │  │ Engine        │  │ Glycogen      │   │     │
│  │  │ Lactate       │  │ Fatigue       │  │ Efficiency    │   │     │
│  │  └───────────────┘  └───────────────┘  └───────────────┘   │     │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │     │
│  │  │ AutonomicFusion│  │ CriticalSpeed │  │ AdaptiveMemory│   │     │
│  │  │ Engine (AFI)  │  │ RCP Engine    │  │               │   │     │
│  │  └───────────────┘  └───────────────┘  └───────────────┘   │     │
│  │  ┌───────────────────────────────────────────────────────┐  │     │
│  │  │  ML Scaffold (shadow/advisory only — kill-switch on)  │  │     │
│  │  │  LoadPrediction · InjuryRisk · AutomatedPeriodization │  │     │
│  │  └───────────────────────────────────────────────────────┘  │     │
│  └──────────────────────────────────────────────────────────────┘    │
│                            │                                         │
│  ┌─────────────────────────┼──────────────────────────────────┐     │
│  │  Features Layer          │                                  │     │
│  │  WeeklyPlanGenerator  OptimalTimeCalculator  NutritionOptim│     │
│  └──────────────────────────────────────────────────────────────┘    │
│                            │                                         │
│  ┌─────────────────────────┼──────────────────────────────────┐     │
│  │  Core Layer              │                                  │     │
│  │  UniversalAthleteProfile │ DatabaseManager (SQLite)         │     │
│  │  PeriodizationManager    │ PersistenceAdapter               │     │
│  └──────────────────────────────────────────────────────────────┘    │
│                            │                                         │
│  ┌─────────────────────────┼──────────────────────────────────┐     │
│  │  Integrations Layer      │                                  │     │
│  │  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐ │     │
│  │  │ GarminSync   │  │  WeatherAPI   │  │ TitanTelegramBot │ │     │
│  │  │ (6h thread)  │  │  (1h cache)   │  │ (command router) │ │     │
│  │  └──────────────┘  └───────────────┘  └──────────────────┘ │     │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  UI Layer                                                     │   │
│  │  MenuSystem  SetupWizard  OperatorConsole (payload only)      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Storage                                                      │   │
│  │  SQLite: titan.db                                             │   │
│  │  Tables: daily_metrics · training_log · gear_usage ·          │   │
│  │          personal_bests · governance_outcomes                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘

External:
  Garmin Connect API ◄── GarminSync (HTTPS, OAuth, garminconnect lib)
  Open-Meteo API     ◄── WeatherAPI  (HTTPS, no auth)
  Telegram Bot API   ◄── TitanTelegramBot (HTTPS, pyTelegramBotAPI)
```

---

## Background Threads

| Thread | Trigger | Cadence |
|--------|---------|---------|
| Garmin Sync Thread | Daemon; starts at launch | Every 6 hours |
| Weather Update Thread | Daemon; starts at launch | Every 1 hour |
| Daily Coach Scheduler | Cron-style | 07:00 morning briefing; 20:00 Sunday weekly plan |

---

## Key Data Flows

### Morning Briefing Flow

```
Scheduler trigger (07:00)
  → DailyCoach.run_morning_routine()
  → GarminSync.get_latest() → DatabaseManager.get_daily_metrics()
  → [12 science engines hydrated from DB]
  → GovernanceEngine.evaluate() → GovernanceDecision
  → WeeklyPlanGenerator.get_today_session()
  → OptimalTimeCalculator.get_window()
  → NutritionOptimizer.get_macros()
  → TitanTelegramBot.send_briefing()
```

### Governance Decision Flow

```
GovernanceEngine.evaluate(metrics)
  → H1 (override check)
  → H2 (HRV delta)  → HARD_STOP if triggered
  → H3 (RHR delta)  → HARD_STOP if triggered
  → H4 (TSB floor)  → HARD_STOP if triggered
  → H5 (subjective) → HARD_STOP if triggered
  → H6 (fueling)    → LOCK / FLAG
  → H7 (2-of-4)     → DOWNGRADE if 2+ soft metrics hit
  → returns GovernanceDecision(lock_codes, session_type, rationale)
  → OutcomeTracker.record_decision()
```

---

## Phase 8B Future State (Not Yet Implemented)

Phase 8B (ADR-0013) will add:
- **FastAPI backend** — REST API for Operator Console
- **React frontend** — web UI for Operator Console
- **JWT authentication** — RS256, HTTP-only cookies (ADR-0048)
- **PostgreSQL** — replaces SQLite (ADR-0044)

The container diagram will be updated when Phase 8B containers are deployed.

---

## Related

- `ARCHITECTURE.md` — full architectural design with prose
- ADR-0013 — Operator Console technology path (Streamlit → React + FastAPI)
- ADR-0018 — Kernel Boundary: Decision Pipeline / Effect Runner Split
- ADR-0046 — DailyCoach multi-athlete execution model
- `docs/training/DECISION_MODEL.md` — governance gate pipeline detail
