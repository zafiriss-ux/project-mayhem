# ADR 0001: Διόρθωση τυπογραφικού λάθους σε αναφορά module

- **Status:** Implemented
- **Date:** 2026-02-17
- **Commit:** d57b6a4 / 421e7e1

## Context

Στο `ARCHITECTURE.md` το module του optimal time εμφανιζόταν ως
`features/optimal_time.py`, ενώ το πραγματικό αρχείο είναι
`features/optimal_time_calculator.py`.

## Decision

Στοχευμένη διόρθωση σε όλα τα active docs ώστε να χρησιμοποιείται
το σωστό όνομα αρχείου (`optimal_time_calculator.py`).

## Reasoning

- Μειώνει onboarding friction.
- Αποτρέπει λάθος import paths σε μελλοντικό development.

## Edge cases εξεταστηκών

- Παλαιές αναφορές σε migration docs (v50/v51): δεν υπήρχαν.
- `README.md` αναφέρει ήδη το σωστό όνομα — δεν χρειάστηκε αλλαγή.

## Υλοποίηση

1. `ARCHITECTURE.md` — Directory Structure tree: `optimal_time.py` → `optimal_time_calculator.py`
2. `ARCHITECTURE.md` — Module Responsibilities section: ίδια διόρθωση
3. Επαλήθευση: `rg "optimal_time\.py" *.md` → 0 αποτελέσματα
