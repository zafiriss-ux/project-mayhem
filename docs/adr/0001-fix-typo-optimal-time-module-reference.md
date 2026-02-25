# ADR 0001: Διόρθωση τυπογραφικού λάθους στο όνομα module `optimal_time`

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-02-17 |
| **Commits** | `d57b6a4`, `421e7e1` |
| **Files** | `ARCHITECTURE.md` |

---

## Context

Στο `ARCHITECTURE.md` το module του optimal time εμφανιζόταν με λάθος όνομα:

```
features/optimal_time.py            # ← δεν υπάρχει
```

Το πραγματικό αρχείο στο repository είναι:

```
features/optimal_time_calculator.py  # ← αυτό υπάρχει
```

Έλεγχος όλων των doc αρχείων (`README.md`, `CHANGES.md`, `DEPLOYMENT_GUIDE.md`,
`titan/QUICK_REFERENCE.md`, `titan/MIGRATION_CORE_MODULES.md`): μόνο το
`ARCHITECTURE.md` περιείχε το λάθος όνομα, σε δύο σημεία:
1. Directory Structure tree (γραμμή `├── optimal_time.py`)
2. Module Responsibilities header (`features/optimal_time.py`)

---

## Decision

Στοχευμένη αντικατάσταση και στα δύο σημεία:
`optimal_time.py` → `optimal_time_calculator.py`.

Δεν χρειάστηκε αλλαγή σε migration docs (CORE_MIGRATION_SUMMARY.md) — τα
historical paths αφήνονται ως έχουν για ιστορικό πλαίσιο.

---

## Consequences

**Θετικά**
- Μηδενικό onboarding friction για νέους contributors που αναζητούν το module.
- `grep`/`rg` για `optimal_time.py` στα docs επιστρέφει 0 αποτελέσματα.
- Τα docs είναι consistent με το filesystem.

**Ουδέτερα**
- Μικρή αλλαγή — δεν επηρεάζει κώδικα ή tests.

**Αρνητικά**
- Κανένα.

---

## Επαλήθευση

```bash
rg "optimal_time\.py" docs/ README.md ARCHITECTURE.md CHANGES.md
# → 0 αποτελέσματα
```
