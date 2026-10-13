# Archived Tests — RaceLab Garage

Tests moved to `tests_archived/` during the math overhaul spring cleaning (2026-05-27)
and the UI/workflow cleanup (2026-10-13).
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
| `test_contract_legacy.py` (37 tests) | Generic model-shape checks, stale warning examples, and two placeholder checks that did not exercise a renderer or real frontend mapping. Focused model/API contracts are maintained in their owning test modules. | `test_lap_windows.py`, `test_notebook.py`, `test_comparison.py`, `test_compare_greenfield_contract.py`, `test_platform.py`, `test_import_hardening.py`, `test_persistence.py` |
| `test_vehicle_dynamics_legacy.py` (3 tests) | Its three formula/missing-input checks are duplicated by the broader physics-estimate suite. | `test_physics_estimates.py` |

## Partial-File Archives

| Archived Function | Source File | Reason | Active Coverage |
|---|---|---|---|
| `test_real_ibt_header` | `test_ibt_header.py` | Real .ibt header parse. Covered by normalization test. | `test_real_telemetry_normalization` |
| `test_setup_diff_detects_changes` | `test_comparison.py` | Covered by compare API contract tests. | `test_persistence.py::test_compare_same_run_triggers_reference_warning` |
| `test_setup_diff_no_changes` | `test_comparison.py` | Same as above. | Same |
| `test_setup_diff_none_setups` | `test_comparison.py` | Same as above. | Same |
| `test_context_diff_detects_weather` | `test_comparison.py` | Covered by compare API. | Same |
| 9 catalog/metadata tests | `test_telemetry_normalization.py` | Duplicate of classification contract tests. | `test_analysis_constants.py` (18 tests) |
| 7 obsolete Platform layout assertions | `test_platform_chart_visibility.py` | Removed Priority/Platform broadcast and old chart-order contracts no longer describe the current Platform workbench. Remaining chart, trace, scope, and missing-data tests stay active. | Current `PlatformTab.tsx` workbench and remaining tests in the same file |
| 1 obsolete Platform recovery assertion | `test_platform_recovery_and_session_run_navigation_frontend_contract.py` | Expected the removed global “Retry platform evidence” surface. Resource scoping and session recovery tests remain active. | Remaining functions in the same file |
| 2 obsolete Platform broadcast assertions | `test_platform_setup_broadcast_frontend_contract.py` | Expected the removed Platform broadcast/handoff controls. | Remaining trace-failure and setup-identity contracts in the same file |
| 3 obsolete Priority Rail assertions | `test_shell_ux_frontend_contract.py` | Priority Rail was removed from the shell in the current workspace redesign. | Remaining shell keyboard, import, timeline, and scope contracts |
| 1 obsolete startup copy assertion | `test_startup_import_polish_frontend_contract.py` | Startup copy was rewritten around the new workspace journey. | Remaining import progress/retry/completion contracts |
| 1 obsolete Platform broadcast assertion | `test_tab_experience_polish_frontend_contract.py` | Platform no longer owns the removed global broadcast. | Overview, Laps, and Setup experience contracts |
| 1 obsolete lazy-load assertion | `test_ui_performance_contract.py` | The removed Priority Rail is no longer a lazy-loaded surface. | Remaining lazy-load and chart-performance contracts |
| `test_cfs_half_inch_claim_is_needs_review` | `test_setup_guide_digest.py` | Duplicate of the richer review-queue assertion in the owning setup-knowledge tests. | `test_setup_knowledge.py::test_cfs_half_inch_item_remains_needs_review` |
| `test_arb_discrete_options_remain_exact` | `test_setup_guide_digest.py` | Exact duplicate of the Next Gen ARB option contract in the owning setup-knowledge tests. | `test_setup_knowledge.py::test_next_gen_arb_diameter_and_arm_constraints_valid` |
| `test_next_gen_query_never_returns_legacy_disabled_areas` | `test_setup_guide_digest.py` | Same query and disabled-area assertion already covered by the owning matcher tests. | `test_setup_knowledge.py::test_next_gen_never_returns_disabled_legacy_areas` |
| `test_every_setup_effect_has_effect_and_counter_effect` | `test_setup_guide_digest.py` | Duplicate structural check; the owning test also verifies the counter-effect language. | `test_setup_knowledge.py::test_every_effect_has_effect_and_counter_effect_arrays` |
| `test_platform_threshold_classification` | `test_platform.py` | Repeated the same splitter classifier boundaries already covered by the focused metrics test. | `test_platform_metrics.py::test_splitter_height_classification_boundaries` |

---

## Active Default Suite

The active collection is measured rather than frozen in a hand-maintained file list.
Verification snapshot on 2026-10-13: 2,868 active items across 208 modules;
the fast command selects 2,834 items across 205 modules. Archived modules are
excluded by the pytest configuration.
