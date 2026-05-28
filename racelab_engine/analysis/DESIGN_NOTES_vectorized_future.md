# Design Notes: Future Vectorized Modules

## Status

The first slice of the vectorized analysis path is complete and verified:
- `vectorized_channels.py` — core unit conversions, dynamic pressure, slip ratios, speed derivatives
- 16 parity tests pass with 1e-9 tolerance
- **7.5–15× speedup** over row-by-row path (1k–100k rows)
- Not wired into runtime yet — opt-in flag recommended after 2 more slices

---

## Future Module Designs

### 1. `frequency_domain_shocks.py`

**Purpose**: FFT-based shock analysis for damper tuning insight.

**Required inputs**:
- `lf_shock_vel_in_s`, `rf_shock_vel_in_s`, `lr_shock_vel_in_s`, `rr_shock_vel_in_s`
- `session_time` (for uniform sample rate check)

**Outputs**:
- Per-corner dominant frequency (Hz)
- Power spectral density per band (low/mid/high)
- Shock activity spectral centroid

**Confidence requirements**:
- `LOW` — spectral estimates from non-uniformly sampled telemetry are approximate
- Flag when sample rate varies >10%

**Safe first implementation**:
- Use `scipy.signal.periodogram` or `numpy.fft.rfft` on trailing window
- Polars `.group_by("lap")` + `map_groups` with numpy UDF
- Start with 1 corner (LF) before expanding to 4

**Tests needed**:
- Synthetic sine-wave shock velocity → known frequency output
- Uniform vs non-uniform time step handling
- Empty/missing data

---

### 2. `aero_map_regression.py`

**Purpose**: Fit a simple aero map (downforce vs. speed) from telemetry.

**Required inputs**:
- `speed_mps` (or `speed_mph`)
- `dynamic_pressure_pa` or `dynamic_pressure_psf`
- `front_load_proxy_n`, `rear_load_proxy_n` (from ride height deltas)
- `throttle_pct`, `brake_pct` (for gating steady-state)
- `long_accel`, `speed_rate_mps2` (for grade correction)

**Outputs**:
- Front and rear aero coefficient proxies (N/(m/s)²)
- Aero balance (% front) vs. speed
- R² goodness-of-fit per run

**Confidence requirements**:
- `MEDIUM` — coefficients are proxy-level, not wind-tunnel
- Gate on steady-state corners (constant throttle, low steering)
- Require minimum 50 data points per run

**Safe first implementation**:
- Linear regression: `load ~ dynamic_pressure` per axle
- Use `scipy.stats.linregress` or `sklearn.linear_model.LinearRegression`
- Polars `group_by("run_id")` + `map_groups`

**Tests needed**:
- Synthetic data with known aero coefficient → recovered within 10%
- Gate logic (throttle/brake/steering filters)
- Missing load proxy → graceful skip

---

### 3. `tire_load_model.py`

**Purpose**: Estimate per-corner vertical tire load using geometry, kinematics, and aero proxy.

**Required inputs**:
- `mass_kg`, `cg_height_m`, `wheelbase_m`, `front_track_width_m`, `rear_track_width_m`
- `front_axle_to_cg_m`, `rear_axle_to_cg_m`
- `lat_accel`, `long_accel`
- `front_aero_proxy_n`, `rear_aero_proxy_n`
- `lf_ride_height_mm`, `rf_ride_height_mm`, `lr_ride_height_mm`, `rr_ride_height_mm`
- `motion_ratio_front`, `motion_ratio_rear` (optional)

**Outputs**:
- Per-corner vertical load (N)
- Lateral load transfer distribution (%)
- Longitudinal load transfer (N)
- Jacking force estimate (if geometry available)

**Confidence requirements**:
- `MEDIUM` — relies on proxy aero loads and assumed CG height
- `LOW` for jacking force (requires anti-geometry not in iRacing telemetry)

**Safe first implementation**:
- Static weight distribution + lateral load transfer (simplified single-track)
- Add aero load distribution from `aero_map_regression.py`
- No suspension kinematics yet (use motion ratio only)

**Tests needed**:
- Static weight distribution at zero acceleration
- Lateral load transfer matches known roll stiffness distribution
- Aero load contribution scales with dynamic pressure

---

### 4. `thermal_origin_model.py`

**Purpose**: Estimate tire thermal origin (braking vs. cornering vs. camber) from carcass temps.

**Required inputs**:
- Per-corner inner/middle/outer carcass temps (`*tempCL`, `*tempCM`, `*tempCR`)
- Per-corner surface temps (`*tempL`, `*tempM`, `*tempR`)
- `lat_accel`, `long_accel`, `speed_mps`
- `brake_pct`, `steering_deg`

**Outputs**:
- Thermal origin classification per corner (braking/cornering/camber/cruise)
- Temperature gradient (inner-outer) as camber proxy
- Thermal cycle count (heat-cool cycles per lap)

**Confidence requirements**:
- `LOW` — iRacing tire model thermal physics are simplified
- Cross-run comparisons valid only for same car/track/weather

**Safe first implementation**:
- Simple heuristic: high brake + high outer temp → braking origin
- High lat_accel + high inner temp → cornering origin
- Large inner-outer spread → camber-related
- Polars `when/then/otherwise` expressions, no UDFs

**Tests needed**:
- Synthetic temp profiles with known origin → correct classification
- Missing carcass temp channels → graceful fallback to surface temps
- Edge case: cold tires, wet track

---

### 5. `sensor_fusion.py`

**Purpose**: Fuse GPS, accelerometer, and yaw rate into a unified state estimate.

**Required inputs**:
- `lat`, `lon` (GPS position)
- `speed_mps` (from wheel speed or GPS)
- `yaw_rate`, `lat_accel`, `long_accel`
- `yaw`, `pitch`, `roll` (inertial)
- `session_time`

**Outputs**:
- Fused position (m) — smooth, drift-corrected
- Fused velocity (m/s) — bias-corrected
- Track grade and banking estimates
- Sensor health flags (GPS dropout, accelerometer saturation)

**Confidence requirements**:
- `MEDIUM` for fused position/velocity
- `LOW` for grade/banking (requires accurate bias estimation)

**Safe first implementation**:
- Complementary filter: GPS position (low-pass) + IMU integration (high-pass)
- No Kalman filter yet — start with simple alpha-beta tracker
- Detect GPS dropout via `Lat`/`Lon` stasis

**Tests needed**:
- Synthetic straight-line data → position error < 1%
- Synthetic constant-radius turn → radius error < 5%
- GPS dropout → fusion maintains reasonable position for 1 second

---

## Feature Flag & Adoption Plan

### Current Status (May 2026)

All three slices are complete and verified:

- **Slice 1**: Core conversions, dynamic pressure, slip ratios, speed derivatives, g-values
- **Slice 2**: Ride-height averages, CFS aliases, risk scores, wheel mismatch, shock conversions, rear scrape, platform balance
- **Slice 3**: Stability scores, drag/resistance indices, platform compression, shock rolling aggregates
- **Final sweep**: Tire derived (pressure gain, temp spread, wear spread), scrub proxies, dynamic pressure lap index, dynamic grade, GPS projection

**111 CORE_CHANNELS produced. 38 synthetic parity tests pass. 20 track map tests pass.**

**Row path is the production default. Vector path is experimental opt-in.**

### Real-Data Validation

| Sample | Rows | Channels | Pass/Fail | Max Diff | Notes |
|--------|------|----------|-----------|----------|-------|
| Talladega (high-speed oval) | ~3,100 | ~110 | **PASS** | 7.74e-09 (GPS float) | Non-GPS channels: max diff 0.0 |
| Road course | — | — | **PENDING** | — | No sample available |
| Short track | — | — | **PENDING** | — | No sample available |

**Road course and short-track validation with real .ibt data is required before default switch.**

### Known Bug Fixes

- GPS projection: `lon_rad.cos()` → `lat0.cos()` (latitude, not longitude, for Mercator projection)
- Alias collision: pre-aliased data no longer causes `DuplicateError`
- First-row `full_throttle_resistance_index`: now `None` (not 0.0), matching row path
- **Tire derived channels** (May 2026): 12 channels (`lf_pressure_gain`, `lf_temp_spread`, etc.) were missing because the vector path's `_apply_aliases` didn't include tire column aliases. Fixed by adding `_TIRE_ALIAS_MAP` (24 entries).
- **Cascading import failure** (May 2026): `analysis/__init__.py` eagerly imported `vectorized_channels` → `polars`, breaking the whole analysis package when polars wasn't installed. Fixed with lazy `try/except ImportError` wrapper.

### Known Differences from Row Path

1. **Shock rolling aggregates (warm-up window)**: The first 59 rows (window=60) differ between paths. The row path uses a growing Python list buffer; Polars rolling uses `min_samples=1`. After the window fills, results converge. The comparison helper exempts these rows from failure reporting.

2. **`drag_scrub_suspicion` UDF**: Uses `map_elements` with the shared `compute_drag_scrub_index` function. This is the one place a Python UDF is used. Performance impact is minimal but it prevents full vectorization of this channel.

3. **First-row `None` values**: Derivative-based channels are `None` on the first row in both paths.

4. **`damper_work_proxy`**: Produced only by the vector path (as an alias of `damper_energy_proxy`). Not in `CORE_CHANNELS` since the row path doesn't produce it.

### Benchmark Results (Slices 1–3 + final sweep)

| Row count | Row path | Vector path | Speedup |
|-----------|----------|-------------|---------|
| 1,000 | 96 ms | 10 ms | **9.6×** |
| 10,000 | 973 ms | 37 ms | **26×** |

Vector path overhead is worthwhile above ~200 rows. Row path may be faster at tiny samples — acceptable for the targeted large-import/Compare/Notebook use case.

### Feature Flag

```python
from racelab_engine.analysis.vectorized_channels import get_analysis_engine_mode

mode = get_analysis_engine_mode()                        # "row" (default)
mode = get_analysis_engine_mode(override="vectorized")   # "vectorized"
```

Resolution order:
1. Explicit `override` argument (if valid)
2. `RACELAB_ANALYSIS_ENGINE` env var (if set and valid)
3. Default `"row"`

Invalid values log a warning and fall back to `"row"`.

### Comparison Script

```bash
python scripts/compare_analysis_engines.py path/to/sample.json
python scripts/compare_analysis_engines.py path/to/sample.jsonl
```

Exit code 0 = pass, 1 = fail. Exports sample data from existing imports:
```bash
python scripts/export_sample_json.py <run_id> --out sample.json
```

### pytest-benchmark

Benchmark tests in `tests/test_vectorized_parity.py::TestBenchmark` require `pytest-benchmark`:
```bash
pip install pytest-benchmark
python -B -m pytest -m slow tests/test_vectorized_parity.py
```

Without `pytest-benchmark`, the entire `TestBenchmark` class is skipped via class-level `pytest.importorskip`.

### Adoption Stages

1. **Sidecar only** — current (May 2026). Vector path exists alongside row path, not wired to runtime.
2. **Real sample parity** — in progress. Talladega oval passed. Road course + short track pending.
3. **Opt-in runtime flag** — `RACELAB_ANALYSIS_ENGINE=vectorized` for developer use. Available now.
4. **User-configurable experimental** — setting in UI or session config. Not yet.
5. **Default switch** — blocked until broad real-data validation.

### Adoption Checklist (Before Default Switch)

- [x] Talladega real .ibt data validated (110 channels, pass)
- [ ] Road course real .ibt data validated
- [ ] Short-track real .ibt data validated
- [x] `polars` dependency isolated (lazy import, doesn't break row path)
- [x] Feature flag tested with both modes
- [ ] `import_service` wired with `get_analysis_engine_mode()` dispatch
- [x] Performance regression gate: vector path ≥3× faster at 10k rows (26× actual)
- [ ] `map_elements` UDF for `drag_scrub_suspicion` replaced with pure Polars (nice-to-have)

**Do not switch default until road course and short-track real .ibt samples pass.**
