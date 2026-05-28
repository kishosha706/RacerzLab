# RaceLab Garage — Contract Gap Audit
Last updated: 2026-05-28

## Gap Matrix Summary

### P0 Gaps (Correctness/Trust/Safety)
| ID | Area | Gap | Status |
|---|---|---|---|
| GAP-NULL-001 | CornerTireMap | Math.abs(v) where v can be null | OPEN |
| GAP-CMP-001 | ComparisonInsightPanel | (s.avg_speed_delta_mph ?? 0) null as zero | OPEN |

### P1 Gaps (All Closed)
| ID | Area | Gap |
|---|---|---|
| GAP-EVT-001 | Labels | MIN_REAR_RIDE_HEIGHT label missing |
| GAP-TAG-001 | Labels | UNKNOWN_DRAFT_STATUS label missing |
| GAP-SESS-001 | RunContextBar | Session metadata hidden |
| GAP-REC-001 | OverviewTab | Recommendations not rendered |
| GAP-CHAN-001 | RawChannelsTab | is_proxy not displayed |
| GAP-RUNLIST-001 | RunListItem | Missing fields |
| GAP-SETUP-001 | Compare | related_to_target_issue |
| GAP-CTX-001 | Compare | baseline_value/test_value |
| GAP-LAPS-001 | Laps | classification_tags/confidence_notes |
| GAP-LAPS-002 | Laps | Generic invalid_reasons |
| GAP-EVT-002 | Events | Category not using event_type |
| GAP-CHAN-002 | Channels | Missing mm ride height metadata |
| GAP-EVID-001 | EvidenceCard | Missing event details |

### P2 Gaps
| ID | Area | Gap | Status |
|---|---|---|---|
| GAP-WF-001 | Compare→Notebook | Evidence preservation | MONITOR |
| GAP-WF-002 | TrackMap→Platform | Event sync | MONITOR |
| GAP-LAP-003 | LapsTab | Extended quality fields | DEFERRED |
| GAP-CMP-002 | Compare | Tire/Shock sub-comparisons | **IMPLEMENTED** |
| GAP-CMP-003 | Verdict | success_metric threading | **IMPLEMENTED** |
| GAP-IMP-001 | Import | Cache info display | **IMPLEMENTED** |

## Implemented Deferred Items (2026-05-28)

### TireComparison
- Backend: `aggregate_tire_comparison()` in `compare_math.py` — computes pressure gain, temp spread, wear spread, camber bias deltas
- Returns `available=false` with explanation when tire data missing
- Short runs (<10 laps) get low confidence
- Wired into `routes_compare.py` → `EnhancedComparisonSummary.tire_comparison`
- Frontend: `TiresView` in `CompareTab.tsx` displays tire comparison data

### ShockComparison
- Backend: `aggregate_shock_comparison()` in `compare_math.py` — computes shock activity, velocity RMS, damper energy deltas
- Treats damper energy as proxy
- Returns `available=false` when shock data missing
- Wired into `routes_compare.py` → `EnhancedComparisonSummary.shock_comparison`
- Frontend: `ShocksView` in `CompareTab.tsx` displays shock comparison data

### Success Metric Threading
- Added `success_metric` field to `DidItWorkVerdict` model
- Threaded from `Recommendation.success_metric` through `routes_compare.py` → compare response
- Displayed in `DidItWorkCard` when present
- Included in save-finding payload to Notebook

### Recommendation Fields into Verdict
- Added `cause_bucket`, `required_next_data`, `do_not_change_warnings` to `DidItWorkVerdict`
- Threaded from `Recommendation` model through compare route
- Displayed in `DidItWorkCard` as "Cause", "Required Next Data", "Do Not Change Yet" sections

### Degradation Trend Fields
- `LapDegradationSummary` already had `tire_stress_trend`, `platform_stress_trend`, `cooling_stress_trend`
- Added display in `LapsTab` as "Stress Trends" section with color-coded improving/stable/worsening indicators

### PlatformEvent Metadata Rendering
- Created `ui/src/utils/metadataRenderer.tsx` — safe metadata renderer
- Whitelists primitive values only
- Hides raw debug fields (debug_lap_pct, internal_id, etc.)
- Humanizes keys (snake_case → Title Case)
- Uses ValueDisplay for numeric values
- Collapses under "More Evidence" / "Metadata"

### Channel Formulas/Dependencies Display
- Added expandable detail row in `RawChannelsTab`
- Shows formula, dependencies, description, used_by_charts, used_by_events
- Added confidence level filter (measured/calculated/estimate/proxy)
- Missing formula shows "Formula unavailable."

### Setup Tech Display
- Added `setup_passed_tech` and `setup_modified` display to `RunContextBar`
- Shows "Tech Passed" / "Tech Failed" / "Tech Unknown" based on null safety
- Shows "Modified" badge when setup was modified

### Import Cache Display
- Added cache info indicator to `ImportPanel` when status contains "cached"

### Metadata Completeness
- `speed_fps` and `vert_accel_g` already present in frontend `channelMeta.ts` and `workbenchChannels.ts`
- `front_wheel_speed_mismatch` and `rear_wheel_speed_mismatch` base aliases added

## Backend-Only Fields (Documented)
SetupSnapshot: setup_json, extracted_values
SessionSummary: car_path, track_id_or_path, setup_passed_tech, setup_modified, file_hash, source_file

## Files Changed (Deferred Implementation Session)

| File | Change |
|---|---|
| `racelab_engine/analysis/compare_math.py` | Added `aggregate_tire_comparison()`, `aggregate_shock_comparison()` |
| `racelab_engine/analysis/comparison.py` | Added `success_metric`, `cause_bucket`, `required_next_data`, `do_not_change_warnings` to `DidItWorkVerdict`; updated `_verdict_dict` |
| `api/routes_compare.py` | Wired tire/shock comparisons, threaded recommendation fields into verdict |
| `ui/src/types/compare.ts` | Added `success_metric`, `cause_bucket`, `required_next_data`, `do_not_change_warnings` to `DidItWorkVerdict` |
| `ui/src/components/DidItWorkCard.tsx` | Added `causeBucket`, `requiredNextData`, `doNotChangeWarnings` props and rendering |
| `ui/src/tabs/CompareTab.tsx` | Wired new verdict fields to VerdictView; added `success_metric` to save-finding payload |
| `ui/src/tabs/LapsTab.tsx` | Added Stress Trends section showing tire/platform/cooling trends |
| `ui/src/tabs/RawChannelsTab.tsx` | Added expandable detail row with formula/dependencies; added confidence level filter |
| `ui/src/components/RunContextBar.tsx` | Added setup tech pass/fail/unknown and modified display |
| `ui/src/components/ImportPanel.tsx` | Added cache info indicator |
| `ui/src/utils/metadataRenderer.tsx` | **NEW** — Safe metadata renderer for PlatformEvent metadata |
| `tests/test_contract.py` | Added 17 new tests |
| `docs/contracts/gap_audit.md` | Updated |
| `docs/contracts/backend_frontend_contract.md` | Updated |

## Validation Results (2026-05-28)

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ Passed |
| `npx tsc --noEmit --noUnusedLocals --noUnusedParameters` | ✅ Passed |
| `npm run build` | ✅ Passed (2181 modules, 6.56s) |
| `python -B -m pytest -m "not slow and not integration"` | ✅ All passed |
| `powershell -ExecutionPolicy Bypass -File scripts/audit_local_only.ps1` | ✅ Passed |

## Language Honesty Rules (Tire/Shock)

The `aggregate_tire_comparison()` and `aggregate_shock_comparison()` functions only summarize observed channel deltas. They do not claim causality:

- **Good**: "Pressure gain changed by X psi." / "Temp spread changed by X°C." / "Shock activity increased."
- **Avoided**: "Tire degradation caused the slowdown." / "Adjust rebound because damper energy increased."
- Damper energy is explicitly labeled as proxy.
- Short runs get low confidence with explicit warning.
