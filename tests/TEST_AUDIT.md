# Test Audit — RaceLab Garage

**Date:** 2026-05-26
**Total tests:** 91 across 16 files

---

## Inventory by Protected Contract

### .ibt import & local-only behavior (7 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_ibt_header.py` | `test_file_fingerprint_and_invalid_ibt_error` | Invalid .ibt rejection | KEEP |
| `test_ibt_header.py` | `test_real_ibt_header` | Real header parsing | KEEP |
| `test_ibt_variables.py` | `test_real_ibt_variable_definitions` | Variable definitions | KEEP |
| `test_talladega_baseline_acceptance.py` | `test_talladega_baseline_acceptance` | Full import acceptance | KEEP |
| `test_desktop_local_config.py` | 7 tests | Backend loopback, Tauri local config | KEEP (all unique) |

### Filename/path sanitization (3 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_persistence.py` | `test_sanitize_filename_strips_path_traversal` | ../ stripped | KEEP |
| `test_persistence.py` | `test_sanitize_filename_preserves_safe_names` | Safe names preserved | KEEP |
| `test_persistence.py` | `test_import_endpoint_rejects_non_ibt_multipart` | Non-.ibt = 400 | KEEP |

### Telemetry normalization & unit conversions (5 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_telemetry_normalization.py` | `test_real_telemetry_normalization` | Full pipeline | KEEP |
| `test_telemetry_normalization.py` | `test_missing_channel_behavior` | Missing channel safety | KEEP |
| `test_telemetry_normalization.py` | `test_calculated_channels_imports_units_constants` | Units import contract | KEEP |
| `test_units.py` | `test_unit_conversions` | Conversion accuracy | KEEP |
| `test_session_yaml_real.py` | `test_real_session_yaml_extracts_summary_and_setup` | Session YAML | KEEP |

### Ride-height/rake/platform (4 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_telemetry_normalization.py` | `test_calculated_ride_height_channels` | Ride height calc | KEEP |
| `test_telemetry_normalization.py` | `test_platform_rake_channels` | Rake formulas | KEEP |
| `test_telemetry_normalization.py` | `test_dynamic_pressure_channels` | Dynamic pressure | KEEP |
| `test_platform.py` | `test_platform_threshold_classification` | CFS thresholds | KEEP |
| `test_platform.py` | `test_platform_analyzer_empty_and_valid_event` | Empty data safety | KEEP |

### Tire/Shock calculations (2 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_telemetry_normalization.py` | `test_new_calculated_channels_exist` | New calc channels | KEEP |
| `test_platform_workbench_contract.py` | `test_missing_channel_and_geometry_behavior_is_safe` | Missing geometry safe | KEEP |

### Channel metadata & classification (7 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_telemetry_normalization.py` | `test_channel_metadata_labels` | Labels exist | KEEP |
| `test_telemetry_normalization.py` | `test_channel_metadata_used_by` | Used_by fields | KEEP |
| `test_telemetry_normalization.py` | `test_proxy_channels_have_estimate_warning` | Proxy warnings | KEEP |
| `test_telemetry_normalization.py` | `test_channel_classification_contract` | Proxy/calc/raw | KEEP |
| `test_telemetry_normalization.py` | `test_dynamic_pressure_index_not_comparable_across_runs` | Cross-run warning | KEEP |
| `test_telemetry_normalization.py` | `test_channel_catalog_includes_new_channels` | Catalog has new ch | KEEP |
| `test_telemetry_normalization.py` | `test_channel_catalog_includes_metadata_fields` | Catalog metadata | KEEP |
| `test_telemetry_normalization.py` | `test_channel_catalog_preset_channels_exist` | Preset channels | KEEP |

### Trace payload, platform events, compare (14 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_telemetry_normalization.py` | `test_extrema_downsampling_preserves_min_cfs` | Extrema preservation | KEEP |
| `test_telemetry_normalization.py` | `test_trace_preserves_extrema_with_new_channels` | Trace extrema | KEEP |
| `test_platform_events.py` | 7 individual detector tests | Event detection | KEEP (distinct) |
| `test_platform_events.py` | 6 integration tests | Integration | KEEP (distinct) |

### Comparison math (12 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_comparison.py` | `test_build_lap_grid` — `test_did_it_work_inconclusive` (12) | Full compare contract | KEEP (all distinct) |

### Same-run identity (2 tests — 1 DUPLICATE)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_persistence.py` | `test_compare_same_run_triggers_reference_warning` | Same-run = inconclusive | **KEEP** |
| `test_telemetry_normalization.py` | `test_same_run_compare_uses_identity_not_speed_delta` | Same-run identity | **DELETE** (duplicate of above) |

### Whole-car index, delta traces, insights (1 test)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_persistence.py` | `test_compare_different_run_not_blocked` | Zero delta ≠ same run | KEEP |

### Notebook persistence (13 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_notebook.py` | 13 tests | Full notebook CRUD + contracts | KEEP (all distinct) |

### API route shapes (3 tests)
| File | Test | Protected Behavior | Verdict |
|---|---|---|---|
| `test_persistence.py` | `test_api_runs_and_persisted_overview_after_repository_reopen` | API shape | KEEP |
| `test_persistence.py` | `test_trace_endpoint_and_lap3_invalid_event` | API shape | KEEP |
| `test_report_contract.py` | `test_markdown_report_contract` | Report shape | KEEP |

---

## Actions

### DELETE — 1 true duplicate
- `test_telemetry_normalization.py::test_same_run_compare_uses_identity_not_speed_delta` → identical behavior already covered by `test_persistence.py::test_compare_same_run_triggers_reference_warning` (which is in the correct module for comparison contracts)

### KEEP — 90 distinct tests
All remaining tests protect unique behaviors, edge cases, or contract boundaries. No other duplicates found.

### MERGE — None recommended
The 13 platform event detector tests could theoretically be parameterized but each tests different synthetic row construction — parameterization would make them harder to read and debug. Comparison verdict tests similarly use distinct synthetic payload shapes.

---

## Final Count

| Metric | Before | After |
|---|---|---|
| Total tests | 91 | 90 |
| Files | 16 | 16 |
| Contracts preserved | All | All |
| ENGINEERING_CONTRACTS.md rules | All protected | All protected |
