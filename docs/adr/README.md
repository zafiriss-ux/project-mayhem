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
| [0005](0005-fix-runtime-startup-issues.md) | Διόρθωση runtime προβλημάτων εκκίνησης (5 bugs) | Bug fix | ✅ Implemented | TBD |

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
