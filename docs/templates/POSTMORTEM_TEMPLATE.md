# Post-Mortem: [Incident Title]

**Date of Incident:** YYYY-MM-DD
**Date of Post-Mortem:** YYYY-MM-DD
**Severity:** P0 (data loss / safety) | P1 (user-facing outage) | P2 (degraded service) | P3 (minor)
**Status:** Draft | In Review | Final
**Author(s):** [Name(s)]

---

## Summary

<!-- 2–4 sentences: what happened, what was the impact, and how was it resolved. -->

---

## Timeline

All times in UTC.

| Time | Event |
|------|-------|
| HH:MM | Incident begins |
| HH:MM | First detection |
| HH:MM | On-call paged / team notified |
| HH:MM | Root cause identified |
| HH:MM | Mitigation applied |
| HH:MM | Service restored |
| HH:MM | Incident closed |

---

## Root Cause

<!-- Single paragraph. Use the "5 Whys" method. Be specific: file, function, line, config value. -->

---

## Contributing Factors

- <!-- Factor 1 -->
- <!-- Factor 2 -->

---

## Impact

- **Users affected:** N (or "all" / "none")
- **Data integrity:** [No data loss | Partial data loss — describe scope | Full data loss]
- **Safety gates:** [Not affected | Bypassed — describe | Triggered correctly]
- **Duration:** ~N minutes / hours

---

## Detection

<!-- How was this detected? Alert, user report, manual observation? What was the detection lag? -->

---

## Resolution

<!-- Step-by-step mitigation applied. Include any rollback, hotfix, or config change. -->

---

## What Went Well

- <!-- W1 -->
- <!-- W2 -->

---

## What Went Wrong

- <!-- W1 -->
- <!-- W2 -->

---

## Action Items

| Item | Owner | Priority | Due | Status |
|------|-------|----------|-----|--------|
| <!-- Short description --> | @handle | P0/P1/P2 | YYYY-MM-DD | Open |

---

## Lessons Learned

<!-- 1–3 sentences: what systemic change does this incident drive? -->

---

## Related

- ADR-XXXX (if architectural decision required)
- TECHNICAL_DEBT.md entry T_-_ (if debt item created)
- Runbook: `docs/runbooks/[relevant-runbook].md`
