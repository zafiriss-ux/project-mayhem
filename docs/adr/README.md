# Architecture Decision Records

Αυτός ο φάκελος περιέχει Architecture Decision Records (ADRs) σύμφωνα με τη
μορφή [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
**Context → Decision → Consequences**.

Κάθε ADR τεκμηριώνει μία **αρχιτεκτονική απόφαση** — μία επιλογή που αφορά
τη δομή, τα modules, τα contracts, ή τα safety gates του συστήματος.

> **Σημείωση:** Μετά από triage (2026-03-07), ο φάκελος περιέχει μόνο αληθινές
> αρχιτεκτονικές αποφάσεις (28 ADRs). Οι process-rule ADRs (0021, 0024, 0025,
> 0028, 0029, 0031, 0035, 0036, 0039, 0040) έχουν μεταφερθεί στο `AGENTS.md §16`.
> ADR-0022 επαναχρησιμοποιείται ως Phase 8 Entry Gate Review (architect sign-off).
> Τα historical bug-fix ADRs (0001–0005, 0019, 0043) έχουν αποσυρθεί — το περιεχόμενό
> τους υπάρχει στο `CHANGES.md` και στο `FUTURE_UPGRADES.md`.

---

## Ευρετήριο

| # | Τίτλος | Κατηγορία | Status | Commit |
|---|--------|-----------|--------|--------|
| [0006](0006-architectural-hardening-cold-start-and-engine-sync.md) | Architectural hardening: cold-start, engine sync, null safety | Architecture / Safety | ✅ Implemented | TBD |
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
| [0018](0018-kernel-boundary-decision-pipeline-effect-runner-split.md) | Kernel Boundary: Decision Pipeline / Effect Runner Split | Architecture / Safety | ✅ Phase A + Phase B Implemented (v5.8.0; commit c51e217) | TBD |
| [0020](0020-persistence-failure-policy-dailycoach.md) | Persistence Failure Behavioral Policy: DailyCoach degraded conservative mode | Architecture / Safety | ✅ Accepted (2026-03-05) — T1-15 execution pending | — |
| [0022](0022-review-phase8-go.md) | Phase 8 Entry Gate Review and Architect Sign-off | Architecture / Governance | ✅ Accepted — Phase 8 OPEN (2026-03-08) | — |
| [0023](0023-physiological-input-validation-contract.md) | Physiological Input Validation Contract: bounds validation at DB→engine boundary | Architecture / Safety | ✅ Accepted (2026-03-06) — T1-18 execution pending | — |
| [0026](0026-input-data-sanity-layer.md) | Input Data Sanity Layer: structural/temporal validation at Garmin sync boundary | Architecture / Safety | ✅ Accepted (2026-03-06) — T1-19 execution pending | — |
| [0027](0027-hidden-inter-module-coupling-prevention.md) | Hidden Inter-Module Coupling Prevention: TypedDict contracts + coupling invariant test | Architecture / Quality | ✅ Accepted (2026-03-06) — T4-26 execution pending | — |
| [0030](0030-external-data-source-resilience.md) | External Data Source Resilience Policy: Garmin/Weather staleness gates + degraded-mode integration | Architecture / Safety | ✅ Accepted (2026-03-06) — T1-20, T2-15 execution pending | — |
| [0032](0032-ml-advisory-explainability-protocol.md) | ML Advisory Explainability Protocol: ExplainableOutput contract for advisory models + promotion gate | Architecture / ML | ✅ Accepted (2026-03-06) — T5-06-A: Phase 8 prerequisite | — |
| [0033](0033-physiological-model-aging-and-multi-athlete-architecture.md) | Physiological Model Aging & Multi-Athlete Architecture: model staleness detection + multi-athlete isolation contract | Architecture / Science | ✅ Accepted (2026-03-06) — T5-07 Layers 1–2: Phase 8 prerequisite; Layer 3: Phase 9 | — |
| [0034](0034-environmental-stress-compensation-training-zones.md) | Environmental Stress Compensation for Training Zones: ESI framework (dew point / temperature) + zone adjustment overlay | Architecture / Science | ✅ Accepted (2026-03-06) — T4-29 execution deferred Phase 8 | — |
| [0037](0037-non-training-stress-safety-partition.md) | Non-Training Stress Safety Partition: classify HRV/RHR anomalies as training-explained vs. illness-pattern vs. unexplained | Architecture / Safety | ✅ Accepted (2026-03-06) — T1-21 execution pending | — |
| [0038](0038-governance-decision-rationale-protocol.md) | Governance Decision Rationale Protocol: DecisionRationale contract + gate templates + override-rate monitoring | Architecture / Observability | ✅ Accepted (2026-03-06) — T2-16 execution pending | — |
| [0041](0041-unified-external-data-trust-contract.md) | Unified External Data Trust Contract: DataTrustLevel enum + DataTrustReport + mandatory onboarding gate for new data sources | Architecture / Invariant | ✅ Accepted (2026-03-06) — ACTIVE IMMEDIATELY — T1-23 implementation pending (Phase 8 prerequisite) | — |
| [0042](0042-human-override-first-class-invariant.md) | Human Override as First-Class Architectural Invariant: OverrideSignal contract + Telegram override button + override handler registry per lock code | Architecture / Invariant | ✅ Accepted (2026-03-06) — ACTIVE IMMEDIATELY — T4-32 implementation pending | — |
| [0044](0044-postgresql-migration-phase8a-entry-gate.md) | PostgreSQL Migration as Phase 8A Entry Gate | Architecture / Data | ✅ Accepted (2026-03-06) | — |
| [0045](0045-local-llm-backend-abstraction.md) | Local LLM Backend Abstraction: Ollama and On-Device Model Support | Architecture / AI Platform | ✅ Accepted (2026-03-06) | — |

---

## Πώς να προσθέσεις νέο ADR

Χρησιμοποίησε τον παρακάτω οδηγό μόνο για **αρχιτεκτονικές αποφάσεις**. Οι process rules
ανήκουν στο `AGENTS.md §16`, και τα changelogs/bugfixes ανήκουν στο `CHANGES.md`.

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
