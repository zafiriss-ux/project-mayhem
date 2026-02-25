# ADR 0005: Διόρθωση runtime προβλημάτων εκκίνησης

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-02-18 |
| **Commits** | `4076f2d` |
| **Files** | `main.py`, `titan/science/hrv_engine.py`, `titan/science/tsb_engine.py`, `titan/orchestration/daily_coach.py`, `titan/integrations/garmin_sync.py` |

---

## Context

Κατά την πρώτη πραγματική χρήση του συστήματος εντοπίστηκαν 5 runtime σφάλματα
που εμπόδιζαν τη λειτουργία:

| # | Πρόβλημα | Αιτία |
|---|----------|-------|
| 1 | `ModuleNotFoundError` εκκινώντας από root | Δεν υπήρχε root-level `main.py` — έπρεπε να τρέχει κανείς `cd titan && python main.py` |
| 2 | `AttributeError: get_latest_hrv` | `HRVGuidedEngine` δεν είχε `get_latest_hrv()` αν και το `menu_system.py:359` το καλούσε |
| 3 | TSB/CTL/ATL = 0.0 μετά από restart | `_hydrate_engines_from_db()` έκανε `self.tsb.load_history = loads` — ανύπαρκτο attribute στο `TSBEngine`· τα loads δεν φορτώνονταν ποτέ στο `daily_loads` |
| 4 | Garmin crash σε token expiry | Generic exception — ο χρήστης δεν γνώριζε ότι πρέπει να διαγράψει `~/.garth` |
| 5 | *(N/A)* `get_latest_tsb()` — η μέθοδος δεν υπήρχε (defensive addition) | |

---

## Decision

### 1. Root-level `main.py` (νέο αρχείο)

```python
# main.py — project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from titan.main import main
if __name__ == "__main__":
    main()
```

Λεπτό wrapper. Το `titan/main.py` παραμένει αναλλοίωτο (ήδη είχε δικό του
`sys.path.insert`).

### 2. `get_latest_hrv()` στο `HRVGuidedEngine`

```python
def get_latest_hrv(self) -> float:
    return round(self.hrv_log[-1][1], 1) if self.hrv_log else 0.0
```

Η ίδια τιμή επιστρέφεται και από `get_hrv_summary()["latest_hrv"]` — η νέα
μέθοδος είναι convenience alias.

### 3. Διόρθωση TSB hydration

```python
# πριν — buggy: ορίζε ανύπαρκτο attribute
self.tsb.load_history = loads

# μετά — σωστό: χρησιμοποιεί τη δημόσια API
for date_str, load in reversed(loads):   # reversed: DB επιστρέφει DESC
    self.tsb.add_daily_load(date_str, float(load))
```

Το `reversed()` είναι κρίσιμο: η DB query επιστρέφει `ORDER BY date DESC`,
αλλά το `calculate_ctl()` χρειάζεται chronological order για το EMA.

### 4. Garmin token expiry — εμφάνιση recovery instruction

```python
if any(k in err for k in ("OAuth", "token", "401", "403", "Unauthorized")):
    print("❌ Garmin token expired. Clear cached tokens:\n   rm -rf ~/.garth")
```

### 5. `get_latest_tsb()` στο `TSBEngine` (defensive)

```python
def get_latest_tsb(self) -> float:
    val, _ = self.calculate_tsb()
    return val if val is not None else 0.0
```

---

## Consequences

**Θετικά**
- `python main.py` από root directory δουλεύει χωρίς `cd titan/`.
- Menu 4 → Data Browser → HRV timeline δεν κρασάρει.
- Μετά από restart, CTL/ATL/TSB φορτώνουν σωστά από DB (όχι 0.0).
- Token expiry δείχνει actionable μήνυμα αντί για cryptic traceback.

**Ουδέτερα**
- `titan/main.py` δεν αλλάζει — εξακολουθεί να λειτουργεί και standalone
  (`python titan/main.py`).
- 59/59 tests pass (0 νέα tests — fixes αφορούν runtime flow, όχι pure logic).

**Αρνητικά**
- Κανένα.

---

## Επαλήθευση

```bash
# Root launcher
python main.py          # πρέπει να δείχνει banner χωρίς ImportError

# TSB hydration (ελέγχει ότι daily_loads φορτώνει)
python -c "
from titan.science.tsb_engine import TSBEngine
t = TSBEngine()
t.add_daily_load('2026-02-01', 50.0)
t.add_daily_load('2026-02-10', 80.0)
t.add_daily_load('2026-02-17', 60.0)
print(t.get_latest_tsb())           # ≠ 0.0
print(t.calculate_tsb())            # (value, status_string)
"

# HRV convenience method
python -c "
from titan.science.hrv_engine import HRVGuidedEngine
h = HRVGuidedEngine()
h.add_hrv_measurement('2026-02-17', 55.0)
print(h.get_latest_hrv())           # 55.0
"

pytest test_core_modules.py -q
# 59 passed, 0 warnings
```
