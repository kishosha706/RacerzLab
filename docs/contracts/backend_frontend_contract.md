# RaceLab Garage — Backend/Frontend Contract

## Overview

This document defines the contract between the RaceLab Garage Python backend (FastAPI) and the TypeScript/React frontend. It serves as the single source of truth for API shapes, field dispositions, enum values, and known gaps.

## API Endpoints and Frontend Consumers

| Endpoint | Method | Frontend Function | TS Type |
|---|---|---|---|
| `/api/health` | GET | — | `HealthResponse` |
| `/api/imports/ibt` | POST | `importIbtFile`, `importIbtFileFromPath` | `ImportIbtResponse` |
| `/api/imports/mt2` | POST | `importMt2File`, `importMt2FileFromPath` | `TrackMapIndexEntry` |
| `/api/imports/mt2-folder` | POST | `importMt2Folder` | `{imported, entries}` |
| `/api/runs` | GET | `fetchRunList` | `RunListItem[]` |
| `/api/runs/{run_id}/overview` | GET | `fetchOverview` | `RunOverview` |
| `/api/runs/{run_id}/laps` | GET | `fetchLaps` | `LapSummary[]` |
| `/api/runs/{run_id}/lap-windows` | GET | `fetchLapWindows` | `LapWindowsResponse` |
| `/api/runs/{run_id}/channels` | GET | `fetchChannels` | `ChannelCatalogItem[]` |
| `/api/runs/{run_id}/trace` | GET | `fetchTrace` | `TraceResponse` |
| `/api/runs/{run_id}/events` | GET | `fetchEvents` | `TelemetryEvent[]` |
| `/api/runs/{run_id}/platform-events` | GET | `fetchPlatformEvents` | `PlatformEventItem[]` |
| `/api/runs/{run_id}/setup` | GET | `fetchSetup` | `SetupSnapshot` |
| `/api/runs/{run_id}/report` | GET | `fetchReport` | `ReportResponse` |
| `/api/runs/{run_id}/track-map-package` | GET | `fetchRunTrackMapPackage` | `TrackMapPackage` |
| `/api/compare` | POST | direct `fetch` | `CompareResponse` |
| `/api/compare/preview` | GET | direct `fetch` | `ComparePreviewResponse` |
| `/api/compare/delta-traces` | POST | `fetchCompareDeltaTraces` | `DeltaTraceResponse` |
| `/api/compare/insights` | POST | `fetchCompareInsights` | `ComparisonInsightsResponse` |
| `/api/laps/compare-selection` | POST | — | `LapCompareSelection` |
| `/api/notebook/findings/from-comparison` | POST | direct `fetch` | `NotebookFinding` |
| `/api/notebook/findings` | GET | — | `NotebookFinding[]` |
| `/api/notebook/findings/{id}` | GET/PATCH | — | `NotebookFinding` |
| `/api/notebook/findings/{id}/test-plan` | POST | — | `TestPlan` |
| `/api/notebook/test-plans` | GET | — | `TestPlan[]` |
| `/api/notebook/test-plans/{id}` | PATCH | — | `TestPlan` |
| `/api/notebook/setup-memory` | GET | — | `SetupMemorySummary` |
| `/api/sessions` | GET/POST | `fetchSessions`, `createSession` | `RaceLabSession` |
| `/api/sessions/{id}` | GET/PATCH/DELETE | `fetchSession`, `updateSession`, `deleteSession` | `RaceLabSession` |
| `/api/sessions/{id}/archive` | POST | `archiveSession` | `RaceLabSession` |
| `/api/sessions/{id}/runs` | POST | `addRunToSession` | `RaceLabSession` |
| `/api/sessions/runs/{run_id}/laps` | GET | `fetchRunLapList` | `RunLapList` |
| `/api/track-maps` | GET | `fetchTrackMaps` | `TrackMapIndexEntry[]` |
| `/api/track-maps/{map_id}` | GET | `fetchTrackMap` | `TrackMap` |

## Canonical Status Values

### Verdict Values
| Backend Value | Frontend Label | Color |
|---|---|---|
| `keep_direction` | Keep Direction | `#22c55e` |
| `undo_partially` | Undo Partially | `#f97316` |
| `undo` | Undo | `#ef4444` |
| `retest` | Retest | `#f59e0b` |
| `inconclusive` | Inconclusive | `#8d9aaa` |
| `reference_mode` | Reference | `#38bdf8` |

### Severity Levels
| Backend Value | Frontend Label | Color |
|---|---|---|
| `info` | Info | `#38bdf8` |
| `watch` | Watch | `#f59e0b` |
| `high` | High | `#f97316` |
| `critical` | Critical | `#ef4444` |

### Confidence Levels
| Backend Value | Frontend Label |
|---|---|
| `low` | Low |
| `medium` | Medium |
| `high` | High |

### Event Types (Platform Events)
| Backend `event_type` | Category | Track Map Layer |
|---|---|---|
| `MIN_SPLITTER` | `front_scrape` | Platform |
| `WORST_SPEED_LOSS` | `speed_loss` | Drag/Scrub |
| `WORST_DRAG_SCRUB` | `drag_scrub` | Drag/Scrub |
| `HIGHEST_RAKE` | `front_scrape` | Platform |
| `HIGHEST_PLATFORM_COMPRESSION` | `front_scrape` | Platform |
| `HIGHEST_SHOCK_ACTIVITY` | `shocks` | Shocks |
| `MAX_DYNAMIC_PRESSURE` | `aero` | Aero |
| `MIN_REAR_RIDE_HEIGHT` | `rear_scrape` | Platform |
| `REAR_PLATFORM_LOW` | `rear_scrape` | Platform |
| `REAR_PLATFORM_SCRAPE` | `rear_scrape` | Platform |
| `REAR_CONTACT_RISK` | `rear_scrape` | Platform |
| `WHOLE_CAR_BOTTOMING_RISK` | `whole_car_bottoming` | Platform |

### Track Map Status Values
| Backend Value | Meaning |
|---|---|
| `parsed` | Fully parsed and usable |
| `partial` | Partially parsed — some data may be missing |
| `unsupported` | Format not supported |

### Track Map Source Types
| Backend Value | Meaning |
|---|---|
| `mt2` | From .mt2 file |
| `telemetry` | Generated from telemetry |
| `fallback` | Fallback/generic map |

### Notebook Finding Status
| Backend Value | Meaning |
|---|---|
| `saved` | Saved but not reviewed |
| `confirmed` | Confirmed as correct |
| `rejected` | Rejected as incorrect |
| `needs_retest` | Needs retesting |
| `archived` | Archived |

### Test Plan Status
| Backend Value | Meaning |
|---|---|
| `planned` | Planned but not executed |
| `completed` | Completed |
| `cancelled` | Cancelled |

| Backend Value | Meaning |
|---|---|

### Import Status Values
| Backend Value | Meaning |
|---|---|
| `success` | Import succeeded |
| `partial` | Partial import with warnings |
| `error` | Import failed |

## Field Disposition Summary

### Warnings — Must be displayed where present
All `warnings[]` arrays from backend must be surfaced in the UI. Currently handled:
- `RunOverview.warnings[]` → EvidenceInspector
- `LapWindowsResponse.warnings[]` → LapsTab
- `CompareResponse.warnings[]` → DidItWorkCard
- `TrackMapPackage.warnings[]` → TrackMapTab
- `ImportIbtResponse.status.warnings[]` → ImportPanel
- `NotebookFinding.warnings[]` → NotebookTab

### Confidence — Must be displayed as badge or score
- `PlatformEventItem.confidence` → EvidenceInspector badge
- `DidItWorkVerdict.confidence_score` → DidItWorkCard
- `LapWindowSummary.confidence_score` → LapsTab
- `LapWindowSummary.pace_quality_score` → LapsTab
- `LapWindowSummary.evidence_confidence_score` → LapsTab
- `LapWindowSummary.setup_usefulness_score` → LapsTab
- `TrackMapIndexEntry.match_confidence` → TrackMapTab
- `NotebookFinding.confidence_score` → NotebookTab

### Proxy/Estimate — Must show ProxyBadge or warning
- `ChannelCatalogItem.is_proxy` → EvidenceInspector
- `PlatformEventItem.is_proxy_based` → EvidenceInspector PROXY pill
- `PlatformEventItem.proxy_warning` → EvidenceInspector tooltip
- `DeltaTraceChannel.is_proxy` → DeltaTracesView

## Known Backend-Only Fields

These fields are intentionally not exposed in the UI:

| Field | Reason |
|---|---|
| `LapSummary.pct_min`, `pct_max`, `pct_span` | Internal lap boundary tracking |
| `LapSummary.start_time`, `end_time` | Session timestamps — not user-facing |
| `SessionSummary.file_hash` | Internal dedup |
| `SessionSummary.car_path` | Internal iRacing path |
| `SessionSummary.track_id_or_path` | Internal iRacing path |
| `SessionSummary.telemetry_rate_hz` | Debug info |
| `SessionSummary.variable_count` | Debug info |
| `SessionSummary.record_count` | Debug info |
| `SetupSnapshot.tape_percent` | Internal setup detail |
| `SetupSnapshot.rear_end_ratio` | Internal setup detail |
| `Recommendation.evidence_event_ids[]` | Internal linking |
| `TelemetryEvent.evidence_json{}` | Raw evidence — use `evidence[]` instead |
| `TelemetryEvent.distance_m_peak` | Internal — use `lap_pct_peak` instead |
| `PlatformEventItem.metadata{}` | Internal extensibility |

## Known Debug-Only Fields

These fields are used internally and should not appear in normal UI:

| Field | Reason |
|---|---|
| `TrackMapPoint.lap_pct` | Raw lap percentage — use section/marker labels |
| `TrackMapMarker.lap_pct` | Raw lap percentage — use section/marker labels |
| `TrackMapSection.start_lap_pct`, `end_lap_pct` | Raw lap percentage — use section names |
| `TrackMapOverlayMarker.lap_pct` | Raw lap percentage — use section names |
| `LapSummary.pct_min`, `pct_max` | Internal lap boundary |
| `TraceResponse.downsample` | Debug rendering info |
| `TraceResponse.preserve_extrema` | Debug rendering info |
| `ChannelCatalogItem.formula` | Debug — shown in RawChannelsTab |
| `ChannelCatalogItem.dependencies[]` | Debug — shown in RawChannelsTab |

## Track Map Raw lap_pct Visibility Rule

**Rule:** Normal UI must not show raw lap percentages. Use `trackLocation.ts` helpers to convert `lap_pct` to friendly labels like "Entry Turn 1", "Center Front Stretch", "Exit Turn 3", etc.

The `TrackLocation` type includes `debug_lap_pct` which is explicitly marked as debug-only and should only be shown when `DEBUG_LOCATION` flag is enabled.

## Proxy/Estimate Honesty Rule

Any field marked as `is_proxy: true` or `is_estimate: true` in `channelMeta.ts` must display a `ProxyBadge` or equivalent indicator. Proxy warnings must be shown in tooltips or detail panels. No proxy value should appear as a measured truth.

## Vectorized Engine

The vectorized engine in `racelab_engine/analysis/vectorized_channels.py` is opt-in only. The default engine is the standard `calculated_channels.py`. Vectorized parity issues are tracked separately and are not part of this contract audit.

## Dynamic Track Profile Tuning

Dynamic track profile tuning is deferred until more .ibt data is available. The current track map system uses .mt2 files with centerline-only support.

## Implemented Deferred Items (2026-05-28)

### TireComparison
- Backend: `aggregate_tire_comparison()` in `compare_math.py`
- Wired into `routes_compare.py` → `EnhancedComparisonSummary.tire_comparison`
- Frontend: `TiresView` in `CompareTab.tsx`

### ShockComparison
- Backend: `aggregate_shock_comparison()` in `compare_math.py`
- Wired into `routes_compare.py` → `EnhancedComparisonSummary.shock_comparison`
- Frontend: `ShocksView` in `CompareTab.tsx`

### Success Metric Threading
- `success_metric` added to `DidItWorkVerdict` model
- Threaded from `Recommendation` through compare response
- Displayed in `DidItWorkCard` and save-finding payload

### Recommendation Fields
- `cause_bucket`, `required_next_data`, `do_not_change_warnings` added to `DidItWorkVerdict`
- Displayed in `DidItWorkCard`

### Degradation Trends
- `tire_stress_trend`, `platform_stress_trend`, `cooling_stress_trend` displayed in LapsTab

### PlatformEvent Metadata
- Safe metadata renderer in `ui/src/utils/metadataRenderer.tsx`

### Channel Formulas
- Expandable detail row in `RawChannelsTab` with formula, dependencies, confidence filter

### Setup Tech
- `setup_passed_tech` and `setup_modified` displayed in `RunContextBar`

### Import Cache
- Cache info indicator in `ImportPanel`

## Language Honesty Rules (Tire/Shock)

The `aggregate_tire_comparison()` and `aggregate_shock_comparison()` functions only summarize observed channel deltas. They do not claim causality:

- **Good**: "Pressure gain changed by X psi." / "Temp spread changed by X°C." / "Shock activity increased."
- **Avoided**: "Tire degradation caused the slowdown." / "Adjust rebound because damper energy increased."
- Damper energy is explicitly labeled as proxy.
- Short runs get low confidence with explicit warning.

## Validation Results (2026-05-28)

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ Passed |
| `npx tsc --noEmit --noUnusedLocals --noUnusedParameters` | ✅ Passed |
| `npm run build` | ✅ Passed (2181 modules, 6.56s) |
| `python -B -m pytest -m "not slow and not integration"` | ✅ All passed |
| `powershell -ExecutionPolicy Bypass -File scripts/audit_local_only.ps1` | ✅ Passed |

## Still-Deferred Items

| Gap | Area | Reason | Risk |
|---|---|---|---|
| `grade_context_label` not displayed in LapsTab expanded view | Laps | Field on LapQualitySummary, not LapSummary | Low |
| `session_date` not displayed in LapsTab expanded view | Laps | Field on LapQualitySummary, not LapSummary | Low |
| NotebookTab filter/columns improvements | Notebook | Larger UI change — deferred | Low |
| Dynamic track-type scoring | Analysis | Waiting for more real .ibt validation | Medium |

