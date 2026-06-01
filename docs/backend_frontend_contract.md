# Backend/Frontend Contract Reference

This document catalogs the API contracts between the RaceLab Engine backend (Python/FastAPI)
and the RaceLab Garage frontend (TypeScript/React). It serves as the canonical reference for
response shapes, status values, enum mappings, and known gaps.

---

## API Endpoints and Frontend Consumers

| Endpoint | Method | Frontend Consumer | Response Type |
|---|---|---|---|
| `/api/health` | GET | — (infrastructure) | `{ status: string }` |
| `/api/imports/ibt` | POST | `importIbtFile()`, `importIbtFileFromPath()` | `ImportIbtResponse` |
| `/api/imports/mt2` | POST | `importMt2File()`, `importMt2FileFromPath()` | `TrackMapIndexEntry` |
| `/api/imports/mt2-folder` | POST | `importMt2Folder()` | `{ imported: number; entries: TrackMapIndexEntry[] }` |
| `/api/runs` | GET | `fetchRunList()` | `RunListItem[]` |
| `/api/runs/{id}/overview` | GET | `fetchOverview()` | `RunOverview` |
| `/api/runs/{id}/laps` | GET | `fetchLaps()` | `LapSummary[]` |
| `/api/runs/{id}/lap-windows` | GET | `fetchLapWindows()` | `LapWindowsResponse` |
| `/api/runs/{id}/channels` | GET | `fetchChannels()` | `ChannelCatalogItem[]` |
| `/api/runs/{id}/trace` | GET | `fetchTrace()` | `TraceResponse` |
| `/api/runs/{id}/platform-events` | GET | `fetchPlatformEvents()` | `PlatformEventItem[]` |
| `/api/runs/{id}/setup` | GET | `fetchSetup()` | `SetupSnapshot` |
| `/api/runs/{id}/report` | GET | `fetchReport()` | `{ run_id: string; markdown: string }` |
| `/api/runs/{id}/track-map-package` | GET | `fetchRunTrackMapPackage()` | `TrackMapPackage` |
| `/api/compare` | POST | CompareTab | `CompareResponse` |
| `/api/compare/preview` | GET | CompareTab | `ComparePreviewResponse` |
| `/api/compare/delta-traces` | POST | `fetchCompareDeltaTraces()` | `DeltaTraceResponse` |
| `/api/compare/insights` | POST | `fetchCompareInsights()` | `ComparisonInsightsResponse` |
| `/api/notebook/findings` | GET | NotebookTab | `NotebookFinding[]` |
| `/api/notebook/findings/{id}` | GET/PATCH | NotebookTab | `NotebookFinding` |
| `/api/notebook/test-plans` | GET | NotebookTab | `TestPlan[]` |
| `/api/notebook/setup-memory` | GET | NotebookTab | `SetupMemorySummary` |
| `/api/sessions` | GET/POST | SessionManager | `RaceLabSession[]` / `RaceLabSession` |
| `/api/track-maps` | GET | `fetchTrackMaps()` | `TrackMapIndexEntry[]` |

---

## Canonical Status Values

| Value | Meaning | Frontend Constant |
|---|---|---|

### Lap Classification Tags
| Value | Meaning |
|---|---|
| `OUT_LAP` | First lap from pit |
| `COOLDOWN` | Slow/cool-down lap |
| `PIT_ROAD` | Lap includes pit entry/exit |
| `WRECK_OR_SPIN` | Incident detected |
| `INVALID_SPEED_EVENT` | Speed anomaly |
| `SOLO_CLEAN` | Verified clean lap |

### Verdict Kinds
| Value | Meaning | Color |
|---|---|---|
| `keep_direction` | Change worked | Green |
| `undo` | Change hurt | Red |
| `retest` | Inconclusive, retest | Amber |
| `inconclusive` | Cannot determine | Gray |

Frontend-only verdicts (not produced by backend):
- `undo_partially` — UI state for partial revert
- `reference_mode` — UI state for self-comparison

### Severity Levels
| Value | Color |
|---|---|
| `critical` | Red |
| `high` | Orange |
| `watch` | Amber |
| `info` | Cyan |
| `safe` | Green |
| `unavailable` | Gray |

### Compare Basket Readiness
| Value | Meaning |
|---|---|
| `ready` | Both slots filled, no blocking warnings |
| `caution` | Both slots filled, non-blocking warnings |
| `not_valid` | Cannot compare (different car/track) |
| `reference_mode` | Same lap selected as baseline and test |

### Test Discipline Labels
| Value | Meaning |
|---|---|
| `clean` | Single change, same conditions |
| `mostly_clean` | Minor context differences |
| `mixed` | Multiple changes or context shifts |
| `weak` | Significant confounds |
| `invalid` | Cannot evaluate |

### Confidence Tiers
| Value | Meaning |
|---|---|
| `high` | Reliable evidence |
| `medium` | Moderate confidence |
| `low` | Weak evidence |

### Workspace IDs
| Value | Frontend Tab |
|---|---|
| `overview` | OverviewTab |
| `map` | TrackMapTab |
| `laps` | LapsTab |
| `platform_trace` | PlatformTab |
| `setup_impact` | SetupTab |
| `compare` | CompareTab |
| `notebook` | NotebookTab |
| `channels` | RawChannelsTab |

---

## Known Intentionally Backend-Only Fields

These fields exist in backend models but are not serialized to API responses
or are internal-only:

| Model | Field | Reason |
|---|---|---|
| `SetupSnapshot` | `setup_json` | Raw setup JSON, not needed by frontend |
| `SetupSnapshot` | `extracted_values` | Internal extraction cache |
| `SessionSummary` | `car_path` | Internal file path, not exposed |
| `SessionSummary` | `track_id_or_path` | Internal file path, not exposed |
| `SessionSummary` | `setup_passed_tech` | Not currently displayed |
| `SessionSummary` | `setup_modified` | Not currently displayed |

## Known Intentionally Frontend-Only State

These values exist only in frontend state, never produced by backend:

| Value | Location | Purpose |
|---|---|---|
| `reference_mode` | `VerdictKind` | Self-comparison UI state |
| `undo_partially` | `VerdictKind` | Partial revert UI state |
| `manual` | Map match confidence | User manually selected map |
| Basket queue items | `CompareBasketContext` | Not persisted to backend |

---

## Deferred Contract Gaps

| Gap | Impact | Reason Deferred |
|---|---|---|
| `NotebookFinding` list lacks `next_step`/`success_metric` columns | Cannot sort/filter by next step in list view | Requires backend schema change to include in list response |
| `PlatformTab` "why this trace matters" tooltips | Users may not understand trace purpose | Requires new data structure mapping preset rows to explanations |
| `RawChannelsTab` proxy/confidence filters | Power users cannot filter by channel quality | Requires new filter UI components |
| `SegmentSummary` not in frontend types | Segments are used internally by analysis, not directly consumed by UI | No current UI surface for raw segment data |
| Dynamic track-type weighting | Pace quality scoring not track-adaptive | Deferred until more .ibt variety collected |
| Vectorized engine as default | Row engine remains default | Deferred until road course validation passes |
| `TireComparison`/`ShockComparison` in CompareResponse | Frontend expects `tire_comparison`/`shock_comparison` but backend doesn't compute them | These sub-comparisons need dedicated analysis modules |
| `DidItWorkVerdict.success_metric` field | Backend `Recommendation` has `success_metric` but verdict response doesn't include it | Needs field threading through compare pipeline |

### Recently Closed Gaps (2026-05-28)

| Gap | Resolution |
|---|---|
| `RunListItem` missing `best_lap_time_s`, `lap_count`, `has_setup_snapshot` | Added to backend model + repository query |
| `SetupChange.related_to_target_issue` not serialized | Added to setup_changes dict in routes_compare.py (both compare and preview) |
| `ContextChange.baseline_value`/`test_value` not serialized | Added to context_changes dict in routes_compare.py (both compare and preview) |
| `LapSummaryItem` missing `classification_tags`/`confidence_notes` in session lap list | Passed through in `build_lap_list_for_run()` |
| `LapSummaryItem.invalid_reasons` always generic | Now populated from classification tags with descriptive reasons |
| `ChannelCatalogItem.is_proxy` optional in TypeScript | Changed to required `boolean` matching backend |
| Channel metadata missing `lf/rf/lr/rr_ride_height_mm` | Added to `channelMeta.ts` (149 workbench channels all covered) |
| Platform event `event_type` not used for layer classification | Enhanced `classifyCategory()` and `classifyOverlayLayer()` to check event_type first, covering all 12 event types |
| `CATEGORY_LAYER_MAP` missing `platform_risk`/`other` entries | Added fallback mappings for complete coverage |

---

## Missing-State Handling Rules

| Situation | Display |
|---|---|
| Value is `null` or `undefined` | `—` (em dash) or "Unavailable" |
| Value is `0` (actual zero) | `0` with appropriate unit |
| Sensor not available | "Sensor unavailable" |
| Setup geometry required | "Setup geometry required" |
| Vehicle mass required | "Vehicle mass required" |
| Track map required | "Track map required" |
| Tire data unavailable | "Tire data unavailable" |
| Weather unavailable | "Weather unavailable" |
| Proxy estimate unavailable | "Proxy unavailable — missing source channels" |

---

## TypeScript Type Locations

| Backend Model | TypeScript File | Type Name |
|---|---|---|
| `SessionSummary` | `types/telemetry.ts` | `SessionSummary` |
| `RunOverview` | `types/telemetry.ts` | `RunOverview` |
| `LapSummary` | `types/telemetry.ts` | `LapSummary` |
| `TelemetryEvent` | `types/telemetry.ts` | `TelemetryEvent` |
| `SetupSnapshot` | `types/telemetry.ts` | `SetupSnapshot` |
| `Recommendation` | `types/telemetry.ts` | `Recommendation` |
| `ChannelCatalogItem` | `types/telemetry.ts` | `ChannelCatalogItem` |
| `PlatformEventItem` | `types/telemetry.ts` | `PlatformEventItem` |
| `LapQualitySummary` | `types/laps.ts` | `LapQualitySummary` |
| `LapWindowSummary` | `types/laps.ts` | `LapWindowSummary` |
| `LapDegradationSummary` | `types/laps.ts` | `LapDegradationSummary` |
| `FastestLapGroup` | `types/laps.ts` | `FastestLapGroup` |
| `BestWindowGroup` | `types/laps.ts` | `BestWindowGroup` |
| `LapWindowsResponse` | `types/laps.ts` | `LapWindowsResponse` |
| `CompareResponse` | `types/compare.ts` | `CompareResponse` |
| `DeltaTraceResponse` | `types/compare.ts` | `DeltaTraceResponse` |
| `ComparisonInsightsResponse` | `types/compare.ts` | `ComparisonInsightsResponse` |
| `NotebookFinding` | `types/compare.ts` | `NotebookFinding` |
| `TestPlan` | `types/compare.ts` | `TestPlan` |
| `SetupMemorySummary` | `types/compare.ts` | `SetupMemorySummary` |
| `VerdictKind` | `types/compare.ts` | `VerdictKind` |

