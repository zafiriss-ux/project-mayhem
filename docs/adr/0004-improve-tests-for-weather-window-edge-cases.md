# ADR 0004: Βελτίωση δοκιμών για weather-window edge cases

- **Status:** Implemented
- **Date:** 2026-02-17
- **Commit:** 421e7e1

## Context

Πριν από αυτό το ADR δεν υπήρχαν unit tests για το
`WeatherAPI.find_optimal_training_windows()`. Regression στη λογική
slicing/scoring θα περνούσε απαρατήρητη.

## Decision

Δύο συμπληρωματικές test classes στο `test_core_modules.py`:

### `TestWeatherWindows` (monkeypatched, fully deterministic)

Χρησιμοποιεί `monkeypatch.setattr` για να αντικαταστήσει
`get_hourly_forecast()` με συνθετικό forecast → zero network dependency.

| Test | Τι ελέγχει |
|------|-----------|
| `test_zero_duration_returns_empty` | guard για `duration=0` |
| `test_negative_duration_returns_empty` | guard για `duration<0` |
| `test_integer_duration_slots` | `duration=1.0` → 24 windows (1 slot each) |
| `test_fractional_duration_ceiling` | `duration=1.5` → 23 windows (ceil=2) |
| `test_two_hour_duration_boundary` | `duration=2.0` → 23 windows |
| `test_full_day_duration` | `duration=24` → 1 window |
| `test_duration_exceeding_day_returns_empty` | `duration=25` → [] |
| `test_sparse_forecast_respects_boundary` | 3 slots + 2h → 2 windows |
| `test_single_slot_forecast_1h` | 1 slot + 1h → 1 window |
| `test_single_slot_forecast_2h` | 1 slot + 2h → [] |
| `test_window_has_required_keys` | result dict keys |
| `test_windows_sorted_best_first` | ascending score sort |
| `test_tie_sort_stable` | no windows lost on equal scores |

### `TestWeatherTrainingWindows` (live simulated API)

Χρησιμοποιεί το built-in simulated forecast του `WeatherAPI`
(χωρίς network) για end-to-end validation:

| Test | Τι ελέγχει |
|------|-----------|
| `test_duration_hours_non_positive_returns_empty` | guard (0, -1) |
| `test_fractional_duration_uses_ceil_slots` | `ceil(1.5)=2` slots χρησιμοποιούνται για averages |

## Reasoning

- **Monkeypatched tests**: ελέγχουν αυστηρά τη λογική boundary/slicing
  χωρίς εξάρτηση από εξωτερικά δεδομένα.
- **Simulated API tests**: ελέγχουν τον ολόκληρο pipeline με realistic
  (αλλά offline) forecast.
- Τα δύο layers αλληλοσυμπληρώνονται χωρίς να είναι redundant.

## Edge cases που ελέγχθηκαν

- `duration_hours` 0, αρνητικό, fractional (1.5), integer (1, 2, 24), over-day (25)
- Forecast με 1 slot (boundary)
- Forecast με 3 slots (sparse)
- Midnight: day filtering via `datetime.date()` comparison
- Tie sorting: score ίδιο → windows δεν χάνονται, list sorted

## Υλοποίηση

Αρχείο: `test_core_modules.py`
- Helper function: `_make_forecast(hours, date_str)` → synthetic forecast list
- Fixture: `patched_api(api, monkeypatch)` → WeatherAPI με synthetic data
- 13 + 2 = 15 νέα tests, όλα pass

Τρέξιμο: `pytest test_core_modules.py::TestWeatherWindows test_core_modules.py::TestWeatherTrainingWindows -v`
