# RaceLab Garage — Engineering Contracts

Last updated: 2026-05-26

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

### GET /api/runs/{id}/trace
- `x` may be array or `x_by_name` object
- Channels may be arrays or `TraceChannelPayload` objects
- `downsample` and `preserve_extrema` control sampling

---

## 10. Remaining Risks for Notebook Worker

1. Tire temp/wear data may be unavailable on short runs — Notebook should not save tire conclusions without a confidence caveat.
2. Aero proxy values are relative — Notebook must not present them as absolute forces.
3. Comparison payload may have `null` for tire/shock sections — Notebook must handle gracefully.
4. `dynamic_pressure_index` is lap-relative — not safe for cross-run comparison in Notebook.
5. Same-run comparisons are reference-only — Notebook should not treat them as actionable tests.
