# ADR 0002: Διόρθωση bug στο weather window selection για fractional διάρκεια

- **Status:** Implemented
- **Date:** 2026-02-17
- **Commit:** 421e7e1

## Context

Στο `WeatherAPI.find_optimal_training_windows()` η λογική για
`duration_hours` χρησιμοποιούσε μίξη float/int:

```python
# πριν — buggy
if i + duration_hours > len(day_forecast):   # float comparison
    break
window_forecast = day_forecast[i:i+int(duration_hours)+1]  # int+1 slice
```

Αυτό οδηγούσε σε off-by-one για όλες τις τιμές:
- `duration_hours=1.0` → 2 slots αντί για 1
- `duration_hours=1.5` → 2 slots (τυχαία σωστό)
- `duration_hours=2.0` → 3 slots αντί για 2

## Decision

Εισαγωγή `required_slots = max(1, math.ceil(duration_hours))` ως
ενιαία τιμή για boundary check και slicing.
Προσθήκη guard για `duration_hours <= 0` (return `[]`).

## Reasoning

- Σταθερή και προβλέψιμη επιλογή παραθύρων για οποιαδήποτε διάρκεια.
- `ceil` είναι η σωστή στρογγυλοποίηση: 1.5h χρειάζεται 2 ωριαία buckets.
- Μικρότερο ρίσκο για λάθος recommendations σε production.

## Edge cases που ελέγχθηκαν

- `duration_hours <= 0` → `[]`
- `duration_hours = 0.25h` (15 λεπτά) → `ceil=1` slot
- Τελευταία ώρα ημέρας → boundary check αποτρέπει OOB
- `duration_hours > 24` → `[]` (κανένα παράθυρο δεν χωράει)
- Midnight: η φιλτράρισμα βάσει `date()` διασφαλίζει ότι μόνο
  ώρες της target ημέρας μπαίνουν στο `day_forecast`

## Υλοποίηση

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

## Επαλήθευση

13 edge-case tests στο `TestWeatherWindows` + `TestWeatherTrainingWindows`
(ADR 0004) — όλα περνούν.
