# ADR 0011: Operator Console Session Explorer Payload + Manual Annotation

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-03-02 |
| **Commits** | TBD |
| **Files** | `titan/ui/operator_console.py`, `titan/core/database.py`, `tests/test_operator_console_dashboard.py`, `docs/specs/operator_console_session_explorer.md`, `docs/ROADMAP.MD` |

## Context
Η επόμενη εργασία της Phase 6 μετά το readiness dashboard είναι το session explorer: να υπάρχει payload για review των governance decisions ανά session και δυνατότητα manual annotation από operator.

## Decision
Προστέθηκαν:
- `OperatorConsoleService.session_explorer(limit=...)` για session feed + decision trail.
- `OperatorConsoleService.add_manual_annotation(date, note)` για αποθήκευση operator notes.
- `DatabaseManager.annotate_governance_outcome(date, note)` που ενημερώνει μόνο το `outcome_notes` του τελευταίου decision της ημέρας.

## Consequences
### Θετικά
- Υπάρχει ξεκάθαρο contract για UI session explorer widgets.
- Το annotation write-path είναι περιορισμένο σε ένα πεδίο (`outcome_notes`) με μικρό operational risk.

### Ουδέτερα
- Η υλοποίηση βασίζεται στο ήδη αποθηκευμένο `governance_outcomes` ιστορικό.

### Αρνητικά
- Δεν προστέθηκε ξεχωριστός πίνακας annotations (single-note overwrite policy ανά ημερομηνία).
