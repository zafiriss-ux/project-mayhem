# ADR 0002: Διόρθωση off-by-one στο `find_optimal_training_windows` για fractional διάρκεια

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-02-17 |
| **Commits** | `421e7e1` |
| **Files** | `titan/integrations/weather_api.py` |

---

## Context

Η μέθοδος `WeatherAPI.find_optimal_training_windows(duration_hours)` χρησιμοποιούσε
διαφορετική λογική για το boundary check και για το slicing:

```python
# πριν — buggy: δύο διαφορετικοί τρόποι υπολογισμού slots
if i + duration_hours > len(day_forecast):      # float arithmetic
    break
window_forecast = day_forecast[i:i+int(duration_hours)+1]  # int truncation + 1
```

Αυτή η ασυνέπεια έδινε λάθος αποτέλεσμα για κάθε τιμή `duration_hours`:

| `duration_hours` | Slots (πριν) | Slots (σωστό) | Σχόλιο |
|---|---|---|---|
| 1.0 | 2 (`int(1.0)+1`) | 1 (`ceil(1.0)`) | Off-by-one |
| 1.5 | 2 (`int(1.5)+1`) | 2 (`ceil(1.5)`) | Τυχαία σωστό |
| 2.0 | 3 (`int(2.0)+1`) | 2 (`ceil(2.0)`) | Off-by-one |
| 2.5 | 3 (`int(2.5)+1`) | 3 (`ceil(2.5)`) | Τυχαία σωστό |

Επίσης δεν υπήρχε validation για `duration_hours <= 0`.

**Downstream επίπτωση**: λάθος αριθμός slots → λάθος μέση τιμή dew point/temp
→ λάθος score → λάθος recommendation ώρας προπόνησης.

---

## Decision

Εισαγωγή ενός ενιαίου `required_slots` που χρησιμοποιείται τόσο για το
boundary check όσο και για το slicing:

```python
# μετά — σωστό
if duration_hours <= 0:
    return []

required_slots = max(1, math.ceil(duration_hours))

...
if i + required_slots > len(day_forecast):
    break
window_forecast = day_forecast[i:i+required_slots]
```

`math.ceil` είναι η σωστή επιλογή: μια προπόνηση 1.5h χρειάζεται 2 ωριαία
buckets για να υπολογιστεί ο μέσος όρος συνθηκών.

---

## Consequences

**Θετικά**
- Consistent boundary check και slice — μία μόνο μεταβλητή `required_slots`.
- Σωστός αριθμός slots για κάθε `duration_hours` (integer ή fractional).
- Guard για `duration_hours <= 0` αποτρέπει silent λάθη.
- 13 deterministic tests καλύπτουν όλα τα boundary cases (βλ. ADR 0004).

**Ουδέτερα**
- Για `duration_hours` ακριβώς integer: `ceil(N) = N`, ίδιο αποτέλεσμα με
  `int(N)+1` μόνο αν `int(N)+1 = N`, δηλαδή μόνο αν `N=1`. Για `N≥2` η
  συμπεριφορά αλλάζει (π.χ. 2h: 3→2 slots).
- Αλλαγή σε downstream averages: windows με `duration_hours=2.0` τώρα
  υπολογίζουν μέσο όρο 2 ωρών αντί 3. Αυτό είναι **σωστό**.

**Αρνητικά**
- Η αλλαγή δεν είναι backward-compatible για callers που ανέμεναν το buggy
  behavior (απίθανο σε πρακτική χρήση).

---

## Επαλήθευση

```bash
pytest test_core_modules.py::TestWeatherWindows -v
# 13 passed
```
