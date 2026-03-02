# ADR 0010: Operator Console Readiness Dashboard MVP Payload

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-03-02 |
| **Commits** | TBD |
| **Files** | `titan/ui/operator_console.py`, `tests/test_operator_console_dashboard.py`, `docs/specs/operator_console_readiness_dashboard.md`, `docs/ROADMAP.MD` |

## Context
Η Phase 6 ξεκινά με ανάγκη για operator visibility πάνω σε readiness/load (TSB, ACWR, readiness score, VLG color). Μέχρι σήμερα δεν υπήρχε ενιαίο payload service για dashboard κατανάλωση.

## Decision
Προστέθηκε `OperatorConsoleService` στο `titan/ui/` που χτίζει read-only payload από `governance_outcomes`:
- χρονοσειρά για widgets
- summary aggregations για γρήγορη επιχειρησιακή εικόνα

Η υλοποίηση παραμένει εκτός governance/science logic και δεν μεταβάλλει αποφάσεις προπόνησης.

## Consequences
### Θετικά
- Σαφές integration boundary για επόμενο βήμα UI (Streamlit/React).
- Επαναχρησιμοποιήσιμο και τεστάριστο payload contract.

### Ουδέτερα
- MVP δεν καλύπτει ακόμη manual annotations ούτε session explorer.

### Αρνητικά
- Απαιτεί υπάρχοντα governance outcome δεδομένα για να είναι χρήσιμο production dashboard.
