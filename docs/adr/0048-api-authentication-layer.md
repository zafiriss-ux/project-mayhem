# ADR-0048 — API Authentication Layer

**Date:** 2026-03-15
**Status:** Accepted
**Owner:** Architect
**Implements:** T5-11
**Prerequisite for:** All Phase 8B FastAPI endpoints
**Related:** ADR-0013 (React/FastAPI technology path), ADR-0044 (PostgreSQL/RLS), ADR-0046 (multi-athlete execution model), T5-13 (coach audit trail)

---

## §1 Context

T5-11 has defined the problem clearly: the FastAPI application Phase 8B will serve health data (HRV, RHR, governance decisions, training log) for multiple athletes, without an auth layer having been designed. This is a GDPR violation and a P0 security risk.

`TECHNICAL_DEBT.md` references three options (JWT + refresh, OAuth2 Google/GitHub, session-based) and gives a recommendation for OAuth2.

Before deciding, the constraints that determine the correct choice are defined:

1. **Deployment target Phase 8B:** Local-first, single-operator (the coach or the athlete themselves), up to ~50 athletes. Not SaaS. No external identity provider mandatory.
2. **Dependency philosophy:** TITAN OS has already rejected cloud dependencies in Phase 1. External OAuth2 provider (Google) means: internet required, third-party availability, and external consent flow — contradictions with the local-first architecture.
3. **Multi-athlete isolation:** ADR-0044 (RLS) + ADR-0046 (stateless execution) require that `athlete_id` is always tied to authenticated identity — not to a request parameter.
4. **GDPR:** T5-13 (audit trail) requires a stable `coach_id` per request so the audit log has attribution. This means the auth layer and the audit layer share the same identity contract.

---

## §2 Decision

### 2.1 Auth mechanism: JWT (stateless) with HTTP-only cookie transport

**Rejection of external OAuth2 provider (Google/GitHub):**
- Contradictions with local-first architecture
- Internet dependency — if Garmin sync already has fragility risk (T5-12), no second external dependency is added to the auth path
- Overkill for single-operator deployment Phase 8B
- Not excluded for Phase 9+ multi-tenant SaaS path

**Selection: JWT (RS256) + refresh token rotation, cookie-based transport**

- **Access token:** Short-lived (15 min), RS256 signed, stateless verification
- **Refresh token:** Long-lived (7 days), stored server-side in `auth_tokens` table (PostgreSQL) — this allows revocation, which pure stateless JWT does not permit
- **Transport:** HTTP-only Secure cookie (not exposed to JavaScript — XSS protection), instead of Authorization header
- **Credential input:** Username + bcrypt-hashed password, stored in `auth_users` table

**Why RS256 and not HS256:**
RS256 allows future extension to multiple services that verify tokens without sharing a shared secret. Consistency with Phase 9 architecture.

---

### 2.2 Role model

Two roles for Phase 8B. Flat model — no role hierarchy in Phase 8B. Extension to Phase 9+ if required.

| Role | Identifier | Access |
|---|---|---|
| `COACH` | string literal | Can view data for any athlete. Can submit override for any athlete. Cannot manage users/roles. |
| `ATHLETE` | string literal | Sees **only** their own data. The `athlete_id` is bound from the JWT claim — not from a request parameter. Cannot override other athletes. |

**Isolation invariant (immutable):**

Every endpoint that returns athlete data performs two checks:

1. RLS (PostgreSQL) — backend-level enforcement
2. Application-level check in the FastAPI dependency — `current_user.athlete_id == requested_athlete_id OR current_user.role == "COACH"`

Both must pass. RLS alone is not sufficient (defense in depth).

---

### 2.3 Token / session policy

| Parameter | Value | Rationale |
|---|---|---|
| Access token TTL | 15 min | Minimizes window if token is stolen |
| Refresh token TTL | 7 days | Sufficient for weekly coaching workflow |
| Refresh token rotation | On every use | Old token is automatically invalidated |
| Max active refresh tokens per user | 3 | Supports coach multi-device (laptop + phone + tablet) |
| Token revocation | Explicit logout + server-side deletion from `auth_tokens` | |
| Cookie flags | `HttpOnly`, `Secure`, `SameSite=Strict` | XSS + CSRF protection |
| Failed login lockout | 5 consecutive failures → 15 min lockout | Brute force mitigation |

**Secret storage:**
- Private key (RS256): environment variable `TITAN_JWT_PRIVATE_KEY` (PEM format)
- Public key: environment variable `TITAN_JWT_PUBLIC_KEY`
- Not stored in code or config files

---

### 2.4 Module structure

```
titan/api/
├── auth.py          # JWT creation, verification, cookie handling
├── dependencies.py  # FastAPI Depends() — get_current_user(), require_coach()
├── models.py        # AuthUser, TokenPayload Pydantic models
└── main.py          # FastAPI app, router mounting, auth middleware
```

**Database tables (Phase 8B Alembic migration):**

```sql
CREATE TABLE auth_users (
    id          TEXT PRIMARY KEY,       -- UUID
    username    TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,        -- bcrypt
    role        TEXT NOT NULL,          -- 'COACH' | 'ATHLETE'
    athlete_id  TEXT,                   -- NOT NULL if role='ATHLETE'; NULL if role='COACH'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE auth_tokens (
    id              TEXT PRIMARY KEY,   -- UUID (jti claim)
    user_id         TEXT NOT NULL REFERENCES auth_users(id),
    issued_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE
);
```

**Public endpoint exception (sole exception):**
`GET /health` — no auth required. All other endpoints require a valid JWT.

---

## §3 Relationship T5-11 / T5-13 (auth / audit lane)

The two items **are not merged** — they remain separate. But they have structural coupling that must be acknowledged:

- The `coach_audit_log` of T5-13 requires `coach_id` — which comes from the JWT claim of T5-11
- Therefore: **T5-11 must be implemented first**, and the T5-13 middleware writes `current_user.id` from the `get_current_user()` dependency

**Sequencing:**

```
T5-11 (ADR-0048 auth implementation) → T5-13 (audit middleware, uses auth identity)
```

The two items can be executed in consecutive Codex passes without interruption. The reason they remain separate: T5-13 has its own schema migration (`coach_audit_log`), its own acceptance criteria (GDPR accountability), and a different failure mode if separated incorrectly. A single "auth + audit" task would be excessively large scope for a single Codex pass.

---

## §4 Non-goals / Exclusions

The following are **not** part of T5-11 / ADR-0048:

- OAuth2 external provider (Google, GitHub) — Phase 9 option if TITAN OS becomes multi-tenant SaaS
- RBAC with role hierarchy (admin > coach > athlete) — Phase 9
- Multi-factor authentication — Phase 9
- API key authentication for M2M (machine-to-machine) integrations — Phase 10
- Single Sign-On — out of scope
- Password reset / email verification flow — Phase 8C minimum viable addition
- Rate limiting per endpoint — recognized as gap, tracked as T5-36 (see §5)

---

## §5 New Debt Item

**T5-36 · No API rate limiting — DoS risk on Phase 8B endpoints**

- **Status:** OPEN
- **Priority:** P2 Phase 8B (does not block T5-11 implementation, but must close before production deployment)
- **Scope:** FastAPI rate limiting per user per endpoint (slowapi or custom middleware). 100 req/min per coach, 30 req/min per athlete.
- **Location:** `titan/api/middleware.py`
- **Note:** Does not require ADR. Clean implementation item, Path A.

---

## §6 Acceptance Gate for T5-11 (binary)

T5-11 is DONE when:

1. `auth_users` and `auth_tokens` tables exist in Alembic migration
2. `titan/api/auth.py` — JWT create/verify with RS256
3. `titan/api/dependencies.py` — `get_current_user()`, `require_coach()` FastAPI dependencies
4. Every existing or new endpoint is behind `Depends(get_current_user)` except `GET /health`
5. Application-level isolation check: `ATHLETE` role sees only their own data
6. `tests/titan/api/test_auth.py` — happy path + token expiry + role violation + isolation violation
7. All mandatory gates green: `ruff check .` → `pytest -q -W error::pytest.PytestWarning` → `pytest -q`

**Opus QA trigger:** YES — T5-11 touches cross-subsystem auth logic with security invariants. Path B.

---

## §7 Sequencing confirmation

```
T5-08-B ✅ RESOLVED
T5-25   ✅ RESOLVED
T5-16-A ✅ RESOLVED
         ↓
T5-11   ← current (ADR-0048 accepted — Codex implementation pass next)
         ↓
T5-13   ← after T5-11 (audit middleware requires auth identity)
         ↓
T5-36   ← rate limiting (before production deployment)
```

---

**ADR-0048 status: Accepted — 2026-03-15**
**Codex handoff: authorized for T5-11 implementation pass (Path B — Opus QA required)**
