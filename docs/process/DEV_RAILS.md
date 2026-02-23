\# DEV RAILS (Claude vs Codex)



\## Κανόνας 1 — Spec πριν από code

Κάθε feature ξεκινά με:

\- 1 Issue: SPEC (Claude) + link σε docs/specs ή ADR

και μετά

\- 1 Issue: IMPLEMENTATION (Codex) με tests/acceptance gates



\## Κανόνας 2 — PR scope

\- PRs είναι μικρά και μονοθεματικά.

\- Docs-only PR: 0 αλλαγές σε \*.py

\- Code PR: απαιτεί tests + minimal diff



\## Κανόνας 3 — Acceptance gates (min)

\- unit tests περνάνε

\- no unrelated files

\- deterministic checks όπου χρειάζεται



\## Κανόνας 4 — Ρόλοι

\- Claude: αρχιτεκτονική, specs, ADRs, checklists

\- Codex: υλοποίηση, refactors μόνο όταν υπάρχει ticket, tests

