# TITAN OS — Threat Model

**Version:** 1.0
**Date:** 2026-03-29
**Owner:** Architect
**Status:** Active
**Scope:** TITAN OS v5.8.x, single-athlete self-hosted deployment

---

## System Overview

TITAN OS is a self-hosted coaching system. The primary threat surface consists of:
1. External API credentials (Garmin, Telegram) stored in `~/Documents/TITAN/.env`
2. SQLite database containing athlete biometric and training history
3. Telegram bot receiving and dispatching commands
4. FastAPI service `titan-api` on port 8000 (Docker), with JWT login/refresh and coach routes (ADR-0048, ADR-0054)

---

## Trust Boundaries

| Boundary | Inbound | Outbound |
|----------|---------|----------|
| Garmin Connect API | OAuth token; activity/biometric data | None |
| Open-Meteo API | Weather JSON | None |
| Telegram Bot API | Commands from `TELEGRAM_CHAT_ID` | Coaching messages |
| SQLite DB file | Local process reads | Local process writes |
| `.env` file | Loaded at startup | Never transmitted |

---

## Threat Inventory

### T-01 — Credential Exposure via `.env` File

| Field | Detail |
|-------|--------|
| **Asset** | `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| **Threat** | Credentials exfiltrated if the `.env` file is committed to a repository or if the host filesystem is accessed by an attacker |
| **Likelihood** | Medium (accidental git commit is common) |
| **Impact** | High — full Garmin account access; Telegram bot hijack |
| **Control** | `.env` is in `.gitignore`; `system_check.py` warns if `.env` is missing; credentials are never logged |
| **Residual Risk** | Low — mitigated by .gitignore and no-log policy |

---

### T-02 — Garmin Token Theft / Replay

| Field | Detail |
|-------|--------|
| **Asset** | `.garth_token` OAuth token file |
| **Threat** | If an attacker gains read access to the token file, they can replay it to access the Garmin account |
| **Likelihood** | Low (local file system access required) |
| **Impact** | Medium — Garmin data exposure; read-only access to athlete profile |
| **Control** | Token file is local only; not transmitted; token is refreshed on 401 |
| **Residual Risk** | Low |

---

### T-03 — Telegram Bot Command Injection

| Field | Detail |
|-------|--------|
| **Asset** | `TitanTelegramBot` command handlers |
| **Threat** | Attacker sends crafted Telegram messages to the bot to trigger unintended actions or extract data |
| **Likelihood** | Low (bot only processes messages from `TELEGRAM_CHAT_ID`) |
| **Impact** | Medium — could trigger coaching actions for wrong athlete; data leakage |
| **Control** | `TELEGRAM_CHAT_ID` allowlist enforced on all incoming messages; commands are parsed with fixed dispatch table (no eval/exec) |
| **Residual Risk** | Low — chat ID allowlist is the primary control |

---

### T-04 — Governance Gate Bypass via Crafted Input

| Field | Detail |
|-------|--------|
| **Asset** | 7-gate governance pipeline |
| **Threat** | Crafted biometric values in the database cause a hard-stop gate to not fire when it should |
| **Likelihood** | Very low (local DB, no remote write path in current architecture) |
| **Impact** | Critical — unsafe training recommendation delivered to athlete |
| **Control** | Gate thresholds are constants in `titan/config/thresholds.py`; gates cannot be disabled at runtime; `tests/test_p0_safety_gates.py` enforces boundary conditions in CI |
| **Residual Risk** | Very low |

---

### T-05 — ML Shadow Model Poisoning

| Field | Detail |
|-------|--------|
| **Asset** | `LoadPredictionShadowModel`, `InjuryRiskEnsembleModel`, `AutomatedPeriodizationEngine` |
| **Threat** | Attacker manipulates training data to bias ML model outputs over time |
| **Likelihood** | Very low (local data only; no external training pipeline) |
| **Impact** | Low — ML models are in shadow/advisory mode; kill-switch enforced; governance pipeline is deterministic and unaffected |
| **Control** | `TITAN_ML_KILL_SWITCH` defaults to enabled; ML output is never the sole decision signal; ADR-0014 |
| **Residual Risk** | Very low |

---

### T-06 — Supply Chain Compromise via Dependencies

| Field | Detail |
|-------|--------|
| **Asset** | All Python packages in `requirements.txt` |
| **Threat** | A compromised package version is installed, executing malicious code |
| **Likelihood** | Low (pinned versions in `requirements.txt`; CI secret scan) |
| **Impact** | High — full process compromise |
| **Control** | All versions pinned; `garminconnect` pinned to exact version (ADR-0050); GitHub Actions CodeQL scan; secret scanning workflow |
| **Residual Risk** | Medium — no hash pinning (pip-compile with hashes not yet implemented); see `docs/DEPENDENCY_POLICY.md` |

---

### T-07 — Database Corruption / Tampering

| Field | Detail |
|-------|--------|
| **Asset** | `titan_core.db` SQLite file |
| **Threat** | Local attacker or buggy write corrupts the athlete database |
| **Likelihood** | Low |
| **Impact** | High — loss of training history; governance pipeline runs on invalid data |
| **Control** | All writes use `threading.Lock`; `DailyCoach` enters degraded-conservative mode on persistence failure (ADR-0020); the Docker worker takes a verified daily backup to a separate volume (7 daily + 4 weekly) |
| **Residual Risk** | Low in Docker (both volumes are on the same host disk; copy backups off the machine, `docs/RUNBOOK_DR.md`). Medium in local mode, which takes no automatic backups |

---

## Out of Scope (Current Phase)

- Multi-tenant / multi-athlete isolation (Phase 9 — addressed in ADR-0033 Layer 3)
- Network-level DDoS or API rate-limit exhaustion attacks
- Physical host security

---

## Review Cadence

This threat model is reviewed:
- At every Phase boundary
- When a new external integration is added
- After any P0/P1 security incident

**Last review:** 2026-03-29 (initial)
