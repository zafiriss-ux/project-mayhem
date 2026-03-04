# Architecture Decision Records

Αυτός ο φάκελος περιέχει Architecture Decision Records (ADRs) σύμφωνα με τη
μορφή [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
**Context → Decision → Consequences**.

Κάθε ADR τεκμηριώνει μία αλλαγή που έγινε στο codebase/docs, γιατί έγινε,
και ποιες είναι οι συνέπειές της.

---

## Ευρετήριο

| # | Τίτλος | Κατηγορία | Status | Commit |
|---|--------|-----------|--------|--------|
| [0001](0001-fix-typo-optimal-time-module-reference.md) | Διόρθωση τυπογραφικού λάθους στο όνομα module `optimal_time` | Typo / Docs | ✅ Implemented | `d57b6a4` |
| [0002](0002-fix-weather-window-duration-bug.md) | Διόρθωση off-by-one στο `find_optimal_training_windows` | Bug fix | ✅ Implemented | `421e7e1` |
| [0003](0003-align-documentation-with-current-module-layout.md) | Ευθυγράμμιση τεκμηρίωσης με πραγματικό module layout | Docs / Consistency | ✅ Implemented | `421e7e1`, `eebed78`, `eb1fe54` |
| [0004](0004-improve-tests-for-weather-window-edge-cases.md) | Δοκιμές edge cases για `find_optimal_training_windows` | Tests | ✅ Implemented | `421e7e1` |
| [0005](0005-fix-runtime-startup-issues.md) | Διόρθωση runtime προβλημάτων εκκίνησης (5 bugs) | Bug fix | ✅ Implemented | `4076f2d` |
| [0006](0006-architectural-hardening-cold-start-and-engine-sync.md) | Architectural hardening: cold-start, engine sync, null safety | Bug fix / Tests | ✅ Implemented | TBD |
| [0007](0007-intensity-governance-architecture-audit.md) | Intensity governance architecture audit (C1–C5 conflicts, gate gaps) | Architecture / Audit | ✅ Resolved (see 0009) | TBD |
| [0008](0008-adaptive-priority-lock-and-vlg-specs.md) | Adaptive Priority Lock and Volume Load Gauge specs | Architecture / Science | ✅ Implemented (v5.7.1) | TBD |
| [0009](0009-safety-gate-hardening-C1-C2-resolution.md) | Safety gate hardening: C1 & C2 resolution (OR semantics + gate reorder) | Architecture / Safety | ✅ Implemented (v5.7.4) | TBD |
| [0010](0010-operator-console-readiness-dashboard-mvp.md) | Operator Console readiness/load dashboard MVP payload service | Architecture / UI | ✅ Implemented (v5.8.0) | TBD |
| [0011](0011-operator-console-session-explorer.md) | Operator Console: Session Explorer payload + manual annotation | Architecture / UI | ✅ Implemented (v5.8.0) | TBD |
| [0012](0012-operator-console-manual-override-workflow.md) | Operator Console: Manual Override Workflow | Architecture / UI | ✅ Accepted (v5.8.0) | TBD |
| [0013](0013-operator-console-technology-path.md) | Operator Console: Technology path — Streamlit → React + FastAPI | Architecture / UI | ✅ Accepted (v5.8.0) | TBD |
| [0014](0014-phase7-ml-scaffold-shadow-advisory-mode.md) | Phase 7 ML scaffold: shadow/advisory mode, kill-switch, evidence labels | Architecture / ML | ✅ Implemented (v5.8.0) | TBD |
| [0015](0015-sqlite-retention-and-phase8-data-lifecycle-gate.md) | SQLite retention strategy and Phase 8 data lifecycle gate | Architecture / Data lifecycle | ✅ Accepted | TBD |
| [0016](0016-phase8-multisport-scope-and-adapter-gate.md) | Phase 8 multi-sport scope and unified adapter gate | Architecture / Integrations | ✅ Accepted | TBD |
| [0017](0017-composition-root-and-dailycoach-architecture-audit.md) | Composition root fan-in and DailyCoach god-orchestrator audit | Architecture / Audit | ✅ Accepted (assessment only, 2026-03-04) | TBD |

---

## Πώς να προσθέσεις νέο ADR

1. Δημιούργησε αρχείο: `docs/adr/NNNN-short-title.md`
2. Ακολούθησε τη δομή:

```markdown
# ADR NNNN: Τίτλος

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Proposed / Implemented / Deprecated / Superseded by [MMMM] |
| **Date** | YYYY-MM-DD |
| **Commits** | `hash` |
| **Files** | `path/to/file.py` |

## Context
Γιατί χρειάστηκε αυτή η απόφαση.

## Decision
Τι αποφασίστηκε.

## Consequences
**Θετικά**, **Ουδέτερα**, **Αρνητικά**.
```

3. Πρόσθεσε γραμμή στον παραπάνω πίνακα.
4. Commit: `git add docs/adr/ && git commit -m "docs(adr): add ADR NNNN ..."`
