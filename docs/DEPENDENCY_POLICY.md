# Dependency Policy — TITAN OS

**Version:** 1.0
**Date:** 2026-03-29
**Owner:** Architect
**Status:** Active

---

## Purpose

This document defines the rules for adding, updating, and removing Python dependencies
in TITAN OS. The policy prioritises supply-chain safety, reproducibility, and operational
stability over convenience.

---

## Governing Principles

1. **All versions are pinned.** No floating version specifiers (`>=`, `~=`, `^`) in
   `requirements.txt`. Every package is pinned to an exact version.
2. **Safety-critical integrations are pinned with heightened scrutiny.** The `garminconnect`
   library is pinned to an exact version and may only be upgraded via an explicit ADR review
   (ADR-0050).
3. **No new dependency without justification.** Adding a dependency requires documenting
   the reason, evaluating alternatives, and verifying the package's maintenance status.
4. **No transitive dependency surprises.** After any dependency change, run
   `pip install -r requirements.txt` in a clean environment and verify the full dependency
   tree has not changed unexpectedly.

---

## Requirements File Structure

`requirements.txt` is the single source of truth for all production and development
dependencies. It is divided into sections:

```
# ── Core runtime ──────────────────────────────────────────────────────
garminconnect==X.Y.Z         # pinned — see ADR-0050
pyTelegramBotAPI==X.Y.Z
requests==X.Y.Z
...

# ── Science / numeric ─────────────────────────────────────────────────
numpy==X.Y.Z
...

# ── Development / testing ─────────────────────────────────────────────
pytest==X.Y.Z
ruff==X.Y.Z
hypothesis==X.Y.Z
...
```

---

## Adding a New Dependency

Before adding a dependency, answer all of the following:

| Question | Requirement |
|----------|-------------|
| Is there an existing dependency that already provides this capability? | Must check — do not add if covered |
| Is the package actively maintained (commit in last 6 months)? | Must confirm via PyPI / GitHub |
| Does the package have a known security vulnerability? | Must check via `pip-audit` or OSV |
| What is the package's licence? | Must be MIT / BSD / Apache-2.0 / PSF — no GPL in production runtime |
| Is an exact version available for pinning? | Must pin exact version |

**Procedure:**
1. Add the package to `requirements.txt` at a pinned exact version.
2. Run `pip install -r requirements.txt` in a clean virtualenv.
3. Run all three mandatory gates (`ruff check .`, `pytest -W error`, `pytest`).
4. Document the addition in the PR description with answers to the table above.

---

## Upgrading a Dependency

Minor/patch upgrades:
1. Change the pinned version in `requirements.txt`.
2. Run the full test suite.
3. Include the changelog diff in the PR description (highlight breaking changes or
   security fixes).

**`garminconnect` upgrades (special rule — ADR-0050):**
- Any version change to `garminconnect` requires a dedicated PR.
- The PR must include evidence that the new version has been validated against a
  live Garmin Connect account (sync test with non-zero result).
- The PR description must reference ADR-0050 and confirm O7 (exact-version pinning retained).

---

## Removing a Dependency

1. Confirm the package is unused: `grep -r "import <package>" titan/ tests/`
2. Remove from `requirements.txt`.
3. Run the full test suite to confirm nothing breaks.
4. Note removal in the PR description.

---

## Hash Pinning (Future)

Current status: dependencies are pinned by exact version but **not** by hash.
Hash pinning (`pip-compile --generate-hashes`) provides stronger supply-chain guarantees
against tampered packages. This is tracked in `TECHNICAL_DEBT.md` as a Phase 8+
improvement. Until implemented, hash pinning is a known residual risk (see
`docs/THREAT_MODEL.md` T-06).

---

## Dependency Audit

Run a dependency audit before any production deployment or Phase boundary:

```bash
pip-audit -r requirements.txt
```

Any high/critical vulnerability must be resolved before the Phase is declared closed.

---

## CI Enforcement

The following CI checks enforce this policy:
- `.github/workflows/secret-scan.yml` — scans for secrets in committed files
- `.github/workflows/codeql.yml` — static analysis for security vulnerabilities
- `ruff check .` — enforces import hygiene (unused imports, circular imports flagged)

---

## Related

- `requirements.txt`
- ADR-0050 — Garmin API Fragility Mitigation (garminconnect pinning obligation O7)
- `docs/THREAT_MODEL.md` — T-06 (supply chain compromise)
- `.github/workflows/codeql.yml`
- `.github/workflows/secret-scan.yml`
