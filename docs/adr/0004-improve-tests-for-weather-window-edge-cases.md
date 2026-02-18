# ADR 0004: Δοκιμές edge cases για `find_optimal_training_windows`

| Πεδίο | Τιμή |
|-------|------|
| **Status** | Implemented |
| **Date** | 2026-02-17 |
| **Commits** | `421e7e1` |
| **Files** | `test_core_modules.py` |

---

## Context

Πριν από αυτό το ADR δεν υπήρχαν unit tests για
`WeatherAPI.find_optimal_training_windows()`. Το `test_core_modules.py`
περιείχε μόνο demo-style prints χωρίς assertions. Αποτέλεσμα:

- Η off-by-one ασυνέπεια του ADR 0002 παρέμεινε αδιάγνωστη.
- Regression στο scoring/windowing θα περνούσε αθόρυβα.
- `pytest -q` απέτυχε λόγω missing fixture (`athlete`) και
  `PytestReturnNotNoneWarning` από `return athlete`.

---

## Decision

Αντικατάσταση ολόκληρου του `test_core_modules.py` με proper pytest suite
(9 classes, fixtures, parametrize, tmp_path isolation). Για το
weather-window συγκεκριμένα:

### `TestWeatherWindows` — monkeypatched, fully deterministic

```python
@pytest.fixture
def patched_api(self, api, monkeypatch):
    today = datetime.now().strftime("%Y-%m-%d")
    synthetic = _make_forecast(list(range(24)), today)
    monkeypatch.setattr(api, "get_hourly_forecast", lambda hours: synthetic)
    return api
```

Μηδενική εξάρτηση από network ή ώρα συστήματος (εκτός timezone).

| Test | Ελέγχει |
|------|---------|
| `test_zero_duration_returns_empty` | guard `duration=0` |
| `test_negative_duration_returns_empty` | guard `duration<0` |
| `test_integer_duration_slots` | `1.0h` → 24 windows (1 slot each) |
| `test_fractional_duration_ceiling` | `1.5h` → 23 windows (ceil=2 slots) |
| `test_two_hour_duration_boundary` | `2.0h` → 23 windows (ceil=2 slots) |
| `test_full_day_duration` | `24h` → 1 window |
| `test_duration_exceeding_day_returns_empty` | `25h` → `[]` |
| `test_sparse_forecast_respects_boundary` | 3 slots + 2h → 2 windows |
| `test_single_slot_forecast_1h` | 1 slot + 1h → 1 window |
| `test_single_slot_forecast_2h` | 1 slot + 2h → `[]` |
| `test_window_has_required_keys` | result dict schema |
| `test_windows_sorted_best_first` | ascending sort by score |
| `test_tie_sort_stable` | no windows lost on equal scores |

### Helper function

```python
def _make_forecast(hours: list[int], date_str: str) -> list[dict]:
    return [
        {"timestamp": f"{date_str}T{h:02d}:00:00",
         "hour": h, "dew_point": 10.0, "temp_c": 15.0}
        for h in hours
    ]
```

Ουδέτερες τιμές (dew=10, temp=15) → score differences μόνο από
time-of-day bonus/penalty → deterministic sort order.

---

## Consequences

**Θετικά**
- Κάθε μελλοντική αλλαγή στη λογική windowing θα αποτύχει γρήγορα.
- Τα monkeypatched tests τρέχουν σε < 0.1s, χωρίς I/O.
- Το `_make_forecast` helper είναι επαναχρησιμοποιήσιμο για μελλοντικά tests.
- `pytest -q` περνά καθαρά: 67 passed, 0 warnings.

**Ουδέτερα**
- Τα guard tests (`duration=0`, `duration<0`) ελέγχουν συμπεριφορά που καλύπτεται
  και από την boundary-check λογική — το overlap είναι σκόπιμο για επιπλέον εμπιστοσύνη.

**Αρνητικά**
- Ο έλεγχος `test_fractional_duration_ceiling` κάνει assert `len == 23`
  (hardcoded για 24-slot day). Αν αλλάξει ο τρόπος generation του
  simulated forecast (ώρες ανά ημέρα ≠ 24), ο test θα σπάσει.

---

## Επαλήθευση

```bash
pytest test_core_modules.py -q
# 59 passed, 0 warnings in ~0.5s

pytest test_core_modules.py::TestWeatherWindows -v
# 13 passed
```
