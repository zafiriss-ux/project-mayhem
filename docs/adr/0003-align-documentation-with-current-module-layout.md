# ADR 0003: Ευθυγράμμιση τεκμηρίωσης με το πραγματικό module layout

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-02-17 |
| **Commits** | `421e7e1`, `eebed78`, `eb1fe54` |
| **Files** | `ARCHITECTURE.md`, `README.md`, `CHANGES.md` |

---

## Context

Τα docs περιέγραφαν αρχεία και directories που δεν υπήρχαν στο repository.
Audit έναντι `find titan/ -name "*.py" | sort`:

### ARCHITECTURE.md — phantom entries

| Εικονικό αρχείο/dir | Ενότητα που αναφερόταν |
|---|---|
| `features/optimal_time.py` | Directory tree + Module Responsibilities |
| `integrations/wearables.py` | Directory tree |
| `orchestration/weekly_coach.py`, `notification_manager.py` | Directory tree |
| `ui/cli.py` | Directory tree |
| `core/config.py`, `logger.py`, `profile_manager.py` | Directory tree |
| `utils/validators.py`, `helpers.py`, `exceptions.py` | Directory tree |
| 9 feature modules (session_builder, coaching_strategy κ.ά.) | Directory tree |
| `tests/`, `data/`, `scripts/` directories | Directory tree |
| `config.yaml` | Configuration section |

### ARCHITECTURE.md — δομικά προβλήματα

- **Module Responsibilities**: 6 Python docstring blocks (~120 γραμμές) που
  μπορούν να drift από τον πραγματικό κώδικα.
- **Threading**: 5 speculative threads, μόνο 3 υπάρχουν.
- **DB Schema "New Tables"**: 5 πίνακες (`weight_log`, `hrv_log`, κ.ά.)
  παρουσιάζονταν ως υλοποιημένοι — δεν υπάρχουν στο `DatabaseManager`.
- **Footer**: `🚧 Architecture approved - Beginning implementation` (stale).
- **Test count**: `99 tests` (λάθος — πραγματικό: 59 + 8 = 67).

### README.md

- Αναφορά `integrations/wearables.py` (δεν υπάρχει).

### CHANGES.md

- `✅ All tests passing` — λάθος: το baseline `pytest` απέτυχε λόγω
  missing fixture στο αρχικό `test_core_modules.py`.
- `✅ Added: weight_log, hrv_log…` — πίνακες που δεν υπάρχουν.

---

## Decision

### ARCHITECTURE.md — πλήρης αναθεώρηση:

1. **Directory tree**: μόνο on-disk αρχεία. Προσθήκη `setup_wizard.py` (υπήρχε
   αλλά δεν τεκμηριωνόταν), `docs/adr/` (νέος φάκελος).
2. **Module Responsibilities**: docstrings → markdown πίνακες (4 sections).
3. **Threading**: 5 → 3 threads (Garmin, Weather, Daily Coach).
4. **Configuration**: αφαίρεση `config.yaml`, μόνο env variables.
5. **DB Schema**: actual tables (`daily_metrics`, `training_log`, `gear_usage`,
   `personal_bests`) + "Planned tables" section.
6. **Footer**: `✅ v51.1 deployed — 31 modules, 67 tests passing`.

### README.md:

- Αφαίρεση `integrations/wearables.py`, προσθήκη σημείωσης για `garmin_sync.py`.

### CHANGES.md:

- Αντικατάσταση `✅ All tests passing` με ακριβή αναφορά στο πρόβλημα.
- Αντικατάσταση `✅ Added: weight_log…` με `⏳ Planned: weight_log…`.
- Προσθήκη πλήρους v51.1 changelog.

---

## Consequences

**Θετικά**
- Το `ARCHITECTURE.md` είναι πλέον "source of truth" για current state.
- Πίνακες modules: maintainable, scannable, χωρίς drift risk.
- Ο διαχωρισμός current/planned είναι ξεκάθαρος.
- Νέοι contributors βλέπουν ακριβώς τι υπάρχει.

**Ουδέτερα**
- Aspirational content (Future Enhancements) παραμένει — αλλά σαφώς
  διαχωρισμένο ως roadmap.
- Migration docs (`CORE_MIGRATION_SUMMARY.md`) αφήνονται αναλλοίωτα ως
  historical context.

**Αρνητικά**
- Κανένα. Η αφαίρεση phantom entries δεν επηρεάζει λειτουργικό κώδικα.

---

## Επαλήθευση

```bash
# Κάθε path στο ARCHITECTURE.md directory tree να υπάρχει:
rg "\.py" ARCHITECTURE.md | grep "├──\|└──" | \
  sed 's/.*── //' | sed 's/ .*//' | \
  while read f; do [ -f "titan/$f" ] || echo "MISSING: $f"; done

# Κανένα phantom integration path στο README:
rg "integrations/" README.md
# → garmin_sync.py, weather_api.py, telegram_bot.py μόνο
```
