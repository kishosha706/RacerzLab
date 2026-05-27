# RaceLab Garage — Engineering Contracts

Last updated: 2026-05-26

---

## 0. Track Map (.mt2) Contract

### Source of truth
- `.mt2` files are MoTeCTrackV2 structured binary files.
- They provide centerline geometry (x, y, z, distance, heading) — NOT GPS coordinates.
- No left/right boundaries, track width, banking, or meaningful altitude variation.
- All `.mt2` geometry is relative to an arbitrary local origin, not real-world GPS.

### Import flow
- Frontend sends `.mt2` file bytes via `multipart/form-data` to `POST /api/imports/mt2`.
- Backend parses binary, extracts centerline points + markers + sections, caches parsed JSON.
- Parsed maps are indexed in `data/track_maps/track_map_index.json`.
- Folder import available at `POST /api/imports/mt2-folder` for bulk import.

### Track matching
- Track names are normalized via `normalize_track_key()` (removes suffixes, maps known aliases).
- Layout inferred via `infer_layout_key()` (oval/road/roval/dirt).
- Matching scored by track name (60pts) + layout (30pts) + filename bonus (10pts).
- Scores ≥80 = high confidence, ≥50 = medium, ≥20 = low.

### Overlay alignment
- All overlay markers align by `lap_pct` / `distance_ft`, never by sample index.
- Platform events are mapped to `.mt2` x/y via `interpolate_at_pct()`.
- Target zone is rendered as a highlighted path segment.
- If `.mt2` is unavailable, fall back to lap-distance event list (no spatial rendering).

### Missing data
- `.mt2` files without markers or sections still render centerline.
- Unknown/unsupported `.mt2` variants return `status: "unsupported"` with warnings.
- No GPS → `origin.gps_supported: false`.
- No boundaries → `has_boundaries: false`.
- No banking/width → warnings list explains limitations.

### Local-only
- `.mt2` files are saved to `data/imports/mt2/`.
- Parsed JSON cache saved to `data/track_maps/`.
- No external map tiles, CDN services, or GPS APIs.
- SVG rendering is local-only — no Mapbox, Google Maps, or OpenStreetMap.

---

## 1. Local-Only Rules

- App runs entirely on the user's machine.
- Backend bound to `127.0.0.1` only.
- No cloud sync, auth, analytics, telemetry upload, or external runtime APIs.
- `.ibt`, `.sto`, `.mt2`, setup snapshots, telemetry, and reports never leave the machine.
- Imported `.ibt` files are saved locally to `data/imports/ibt/<safe_name>`.

---

## 2. .ibt Import Contract

- Frontend sends actual file bytes via `multipart/form-data` to `POST /api/imports/ibt`.
- Backend saves to `data/imports/ibt/<sanitized_filename>`.
- Sanitization: `os.path.basename()`, reject path traversal, re-sub special chars, `.ibt` extension only.
- Non-`.ibt` files return HTTP 400: "Unsupported file type."
- Path-based import available at `POST /api/imports/ibt-path` for CLI/dev use only.

---

## 3. Channel Classification

### Raw channels
Direct copies from `.ibt` variable definitions. Example: `Speed` → `speed_mps`.

### Calculated channels
Derived from raw channels using a well-defined formula. Examples:
- `speed_mph = speed_mps * 2.23693629`
- `center_rake_fs_in = rear_avg_rh_in - cfs_ride_height_in`
- `dynamic_pressure_psf = 0.5 * air_density * speed² * PA_TO_PSF`
- `lf_pressure_gain = lf_pressure - lf_cold_pressure`

### Proxy channels
Estimates/heuristics based on available telemetry + assumptions. MUST be labeled `is_proxy: true`. Examples:
- `drag_scrub_suspicion` — heuristic composite score
- `slip_ratio_proxy` — derived from wheel speed vs vehicle speed
- `front_aero_proxy_n` — spring-load proxy, NOT direct force measurement
- `rear_downforce_proxy_n` — relative estimate only

### Classification rules
| Metric | Classification | Reason |
|---|---|---|
| `speed_mph` | Calculated | Direct unit conversion |
| `dynamic_pressure_psf` | Calculated | Physics formula from measured values |
| `dynamic_pressure_index` | Calculated, NOT comparable across runs | Lap-relative normalization |
| `pressure_gain` | Calculated | current − cold, measured sources |
| `slip_ratio_proxy` | Proxy | Depends on wheel speed accuracy, no true slip |
| `drag_scrub_suspicion` | Proxy | Heuristic composite scoring |
| Aero/load/force values | Proxy | No direct force channels in `.ibt` |

---

## 4. Proxy Wording Rules

All proxy channels MUST:
- Include "ESTIMATE", "proxy", or "relative" in description
- Have `is_proxy: true` in channel metadata
- Never claim exact downforce, drag, or tire normal force
- Display as dashed lines in UI charts
- Show "(proxy)" suffix in tooltips
- Carry confidence penalties for: missing motion ratios, high-G transients, high shock activity

---

## 5. Compare Contract

### Same-run/lap
`baseline_run_id == test_run_id` AND `baseline_lap == test_lap` → verdict `inconclusive`, reference comparison only.
Do NOT infer same-run from zero speed delta.

### Lap-percent alignment
All comparisons align by `lap_dist_pct_100`, never by sample index.

### Invalid laps
Invalid/junk/slowdown/partial laps are excluded from comparison by default.

### Missing channels
If requested channel is unavailable, return null/empty, never crash.

### Target zone
Default 55–70% unless user specifies otherwise.

---

## 6. Missing-Data Behavior

- Null/unavailable values display as "—" or "Unavailable".
- Missing critical channels reduce confidence.
- Missing optional channels do not block comparison.
- Empty `setup_changes` or `context_changes` arrays are valid.
- `tire_comparison` and `shock_comparison` may be `null` — UI handles gracefully.

---

## 7. Confidence Tiers

| Tier | Conditions |
|---|---|
| High | Clean data, steady-state, motion ratios available, no transients |
| Medium | Default for most comparisons with adequate data |
| Low | Missing motion ratios, elevated-G, short runs |
| Very Low | High-G transients, high shock activity, missing spring rates |
| Zero | Same-run comparison, invalid data |

---

## 8. Notebook Dependency Note

The Notebook should save existing comparison/insight payloads as-is from the API. Do not recompute, reinterpret, or re-derive comparison results. The backend is the single source of truth for math, verdicts, and confidence scores.

---

## 9. Key API Contracts

### POST /api/compare
- Returns `EnhancedComparisonSummary` dict
- Fields: `whole_car_index`, `platform`, `corner_matrix`, `tire_comparison` (nullable), `shock_comparison` (nullable), `driver_comparison`, `powertrain_comparison`, `verdict`, `setup_changes`, `context_changes`, `test_discipline`, `warnings`, `confidence_score`

### GET /api/compare/delta-traces
- Returns `DeltaTraceResponse` with per-channel delta arrays
- `missing_channels` list for unavailable channels
- Target zone highlighted via `target_zone_start_pct` / `target_zone_end_pct`
### POST /api/compare/insights
- Runs all 5 insight engines: trace annotations, correlations, target zone classification, confidence-weighted verdict, sector intelligence
- Returns `ComparisonInsightsResponse` with `annotations`, `correlations`, `target_zone_classification`, `confidence_weighted_verdict`, `sectors`, `summary_headline`, `key_takeaways`

### POST /api/imports/mt2
- Multipart file upload for `.mt2` track map files
- Returns `TrackMapIndexEntry` with points/markers/sections counts

### POST /api/imports/mt2-folder
- JSON body `{folder_path: string}` — bulk import all `.mt2` files from a directory
- Returns `{imported: number, entries: TrackMapIndexEntry[]}`

### GET /api/track-maps
- Lists all imported track maps from index

### GET /api/track-maps/{map_id}
- Returns full `TrackMap` with all points, markers, sections

### GET /api/runs/{run_id}/track-map-match
- Returns best matching track map for a run based on track name + layout scoring

### GET /api/runs/{run_id}/track-map-package
- Returns full map + overlays (platform events + target zone) for frontend rendering
- Supports `lap`, `target_zone_start_pct`, `target_zone_end_pct` query params
### GET /api/runs/{id}/trace
- `x` may be array or `x_by_name` object
- Channels may be arrays or `TraceChannelPayload` objects
- `downsample` and `preserve_extrema` control sampling

### POST /api/sessions
- Create a new RaceLab session. Optional `{name: string}` body.
- Returns `RaceLabSession` with `session_id`, `name`, `created_at`, `updated_at`, `status: "active"`.

### GET /api/sessions
- List active RaceLab sessions. `?include_archived=true` to include archived.
- Returns `RaceLabSession[]` ordered by `updated_at DESC`.

### GET /api/sessions/{session_id}
- Get a single session by ID. Returns 404 if not found.

### PATCH /api/sessions/{session_id}
- Update session fields: `name`, `track_name`, `car_name`, `last_opened_run_id`, `last_selected_lap`, `last_workspace`, `status`.

### DELETE /api/sessions/{session_id}
- Delete a session. Does **NOT** delete imported telemetry files. Returns `{deleted: true, session_id}`.

### POST /api/sessions/{session_id}/archive
- Archive a session (sets `status: "archived"`). Archived sessions hidden from default list.

### POST /api/sessions/{session_id}/runs
- Add a run to a session. Body: `{run_id: string}`. Duplicate run_ids are silently ignored.

### DELETE /api/sessions/{session_id}/runs/{run_id}
- Remove a run from a session. Does not delete telemetry data.

### GET /api/sessions/{session_id}/runs/{run_id}/laps
- Get full lap list for a run within a session context.
- Returns `RunLapList` with `laps: LapSummaryItem[]`, `best_lap_number`, `useful_lap_numbers`.

### GET /api/sessions/runs/{run_id}/laps
- Standalone lap list (no session required). Same response shape as session-scoped endpoint.

### Lap list response contract
- `LapSummaryItem` fields: `lap_id`, `run_id`, `lap_number`, `label`, `lap_type` (out/timed/in/unknown), `lap_time_s`, `lap_time_display` (M:SS.sss), `delta_s`, `delta_display` (+/-/BEST), `is_valid`, `is_useful`, `invalid_reasons`, `sample_count`, `distance_pct_min/max`, `has_telemetry`
- `lap_type` classification: first non-timed lap before first timed lap = "out", useful laps with lap_time = "timed", laps after last timed lap = "in", fallback = "unknown"
- `delta_display` shows "BEST" for the fastest useful lap, `+0:NNN.NNN` for slower laps, `-0:NNN.NNN` for faster laps (relative to best)

---

## 10. Aero Index & Drag/Scrub Physics Contract

### Aero index usage
- `dynamic_pressure_lap_index` — for within-lap visualization only. Lap-relative (0–1 scale). NOT comparable across runs.
- `dynamic_pressure_index` — alias for `dynamic_pressure_lap_index`. Kept for backward compatibility.
- `aero_load_index` — cross-run comparable aero reference. Ratio of current dynamic pressure to reference pressure at 180 mph sea level. Safe for Notebook comparisons across runs, tracks, weather, and sessions.
- `aero_load_index_180mph` — alias for `aero_load_index`.

### Drag/scrub physics
- `drag_scrub_suspicion` MUST use aero-normalized resistance (`decel_mph_s / dynamic_pressure_psf`), not raw deceleration alone.
- Aero-normalized resistance makes the index speed-independent: a car losing speed at 180 mph under high aero load scores lower than the same deceleration at 100 mph (which is more suspicious).
- The canonical formula lives in `racelab_engine/analysis/drag_scrub.py:compute_drag_scrub_index()`.
- All downstream consumers (segments, platform events, compare, notebook) MUST use this single formula.

### Slip ratio safety
- Denominator floors at `SLIP_RATIO_SPEED_FLOOR_MPS` (1.0 m/s) to prevent division-by-zero near zero speed.
- Values are clamped to ±`SLIP_RATIO_CLAMP_MAX` (2.0) to keep charts sane during pit lane, caution, starts, stops, and replays.

### Yaw-error scrub proxy
- `front_scrub_proxy` is a composite: slip mismatch (30%) + steering/lat (25%) + yaw error (45%).
- Yaw error = `max(0, theoretical_yaw_rate - actual_yaw_rate)` where theoretical comes from track curvature when available.
- When `.mt2` curvature data is available, the yaw-error component enables understeer detection.
- When curvature is unavailable, yaw error defaults to 0 and the proxy falls back to slip + steering components.

### Geometry estimates
- Platform pitch/roll from ride heights assumes 1:1 motion ratio unless setup motion-ratio data is available.
- All internal geometry math uses SI (meters, radians). Conversion to inches/degrees happens only for presentation channels.
- `racelab_engine/analysis/geometry.py` is the single source of truth for pitch/roll calculations.

---

## 11. Remaining Risks for Notebook Worker

1. Tire temp/wear data may be unavailable on short runs — Notebook should not save tire conclusions without a confidence caveat.
2. Aero proxy values are relative — Notebook must not present them as absolute forces.
3. Comparison payload may have `null` for tire/shock sections — Notebook must handle gracefully.
4. `dynamic_pressure_lap_index` is lap-relative — not safe for cross-run comparison in Notebook. Use `aero_load_index` instead.
5. Same-run comparisons are reference-only — Notebook should not treat them as actionable tests.
6. `drag_scrub_suspicion` is a proxy — do not present as exact drag force measurement.
