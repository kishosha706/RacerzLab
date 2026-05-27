# Archived Tests — RaceLab Garage

Tests moved to `tests_archived/` during the math overhaul spring cleaning (2026-05-27).
Pytest ignores `tests_archived/` by default — see `pyproject.toml`.

---

## Full-File Archives

| File | Why Archived | Active Coverage |
|---|---|---|
| `test_platform_events.py` (13 tests) | All 13 individually test 7 event detectors requiring full .ibt import (~60s). Coverage preserved by integration tests and `test_platform.py` threshold tests. | `test_platform.py::test_platform_threshold_classification` |
| `test_platform_workbench_contract.py` (4 tests) | Full .ibt import + API + trace pipeline (~27s). Channel/trace behavior covered by remaining normalization tests. | `test_telemetry_normalization.py` |
| `test_talladega_baseline_acceptance.py` (1 test) | Single full-import acceptance test (~3s). Import validation covered by header/variable tests. | `test_ibt_header.py::test_file_fingerprint_and_invalid_ibt_error` |
| `test_session_yaml_real.py` (1 test) | Real .ibt YAML parse (~1s). Covered by synthetic `test_session_yaml.py`. | `test_session_yaml.py` |
| `test_ibt_variables.py` (1 test) | Variable definition read from real .ibt. Covered by `test_real_telemetry_normalization`. | `test_telemetry_normalization.py::test_real_telemetry_normalization` |
| `test_report_contract.py` (1 test) | Markdown report shape test. Covered by persistence report API test. | `test_persistence.py::test_markdown_report_from_persisted_data` |
| `test_lap_detection.py` (1 test) | Lap detection logic. Covered by session tests. | `test_session.py` (25 tests) |
| `test_units.py` (1 test) | Unit conversion arithmetic. Covered by `test_analysis_constants.py`. | `test_analysis_constants.py` |

## Partial-File Archives

| Archived Function | Source File | Reason | Active Coverage |
|---|---|---|---|
| `test_real_ibt_header` | `test_ibt_header.py` | Real .ibt header parse. Covered by normalization test. | `test_real_telemetry_normalization` |
| `test_setup_diff_detects_changes` | `test_comparison.py` | Covered by compare API contract tests. | `test_persistence.py::test_compare_same_run_triggers_reference_warning` |
| `test_setup_diff_no_changes` | `test_comparison.py` | Same as above. | Same |
| `test_setup_diff_none_setups` | `test_comparison.py` | Same as above. | Same |
| `test_context_diff_detects_weather` | `test_comparison.py` | Covered by compare API. | Same |
| 9 catalog/metadata tests | `test_telemetry_normalization.py` | Duplicate of classification contract tests. | `test_analysis_constants.py` (18 tests) |

---

## Active Default Suite

**~120 tests** across 16 files. Runtime: ~2s (unit) / ~30s (with slow .ibt tests).

| File | Count | Notes |
|---|---|---|
| `test_analysis_constants.py` | 18 | Constants, sigmoid, WCI profiles |
| `test_comparison.py` | 8 | Core math: grid, interpolation, speed_delta, discipline, verdict |
| `test_desktop_local_config.py` | 7 | Local-only config audit |
| `test_drag_scrub.py` | 9 | Aero-normalized resistance, gate logic |
| `test_edge_cases.py` | 10 | Superspeedway, missing data, yaw-error, aero_load_index |
| `test_geometry.py` | 8 | Pitch/roll, corrected deltas, ride height conversions |
| `test_ibt_header.py` | 1 | Invalid .ibt rejection |
| `test_notebook.py` | 13 | Full CRUD + setup memory |
| `test_persistence.py` | 11 | .ibt import, API, trace, compare, sanitization |
| `test_platform.py` | 2 | CFS thresholds, empty/valid events |
| `test_session.py` | 25 | Session CRUD, lap math, run add/remove |
| `test_session_yaml.py` | 1 | Synthetic YAML parse |
| `test_slip_ratio.py` | 7 | Slip floor, clamp, driven wheel proxy |
| `test_telemetry_normalization.py` | 10 | Core normalization, ride heights, rake, dynamic pressure, extrema |
| `test_track_map.py` | 13 | .mt2 decoder, interpolation, matching |
