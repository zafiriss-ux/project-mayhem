# ADR-0024: Canonical Lock Codes

Date: 2026-04-28
Status: Pending — referenced by thresholds.py:182. Author in Phase 13.

## Context
`titan/config/thresholds.py` line 182 references ADR-0024 as the governance
decision that established the `CANONICAL_LOCK_CODES` frozenset — the
machine-readable set of lock codes that all governance engines must use when
locking a session recommendation.

This ADR number was reserved to document that decision but was not formally
authored during the initial governance implementation phases.

## Decision
N/A — pending formal authoring in Phase 13.

## Consequences
Until this ADR is authored, `CANONICAL_LOCK_CODES` in `thresholds.py` is the
authoritative canonical source. Any addition, renaming, or removal of lock
codes must update that frozenset directly. The reference in `thresholds.py:182`
serves as a forward-pointer to this ADR for future readers.
