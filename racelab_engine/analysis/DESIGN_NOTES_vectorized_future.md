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
- **Slice 1**: Core conversions, dynamic pressure, slip ratios, speed derivatives
- **Slice 2**: Ride-height averages, CFS aliases, risk scores, g-values, wheel mismatch, shock conversions
- **Slice 3**: Stability scores, drag/resistance indices, platform compression, shock rolling aggregates

**Row path is the default. Vector path is opt-in only.**

### Feature Flag

A resolver is available in `vectorized_channels.py`:

```python
from racelab_engine.analysis.vectorized_channels import get_analysis_engine_mode

mode = get_analysis_engine_mode()                        # "row"
mode = get_analysis_engine_mode(override="vectorized")   # "vectorized"
```

Resolution order:
1. Explicit `override` argument (if valid)
2. `RACELAB_ANALYSIS_ENGINE` env var (if set and valid)
3. Default `"row"`

Invalid values log a warning and fall back to `"row"`.

### Comparison Helper

```python
from racelab_engine.analysis.vectorized_channels import compare_row_vs_vectorized

report = compare_row_vs_vectorized(rows)
# report["pass_fail"] -> bool
# report["max_abs_diff_by_channel"] -> dict
# report["mismatch_count_by_channel"] -> dict
```

Also available as a CLI script:
```
python scripts/compare_analysis_engines.py path/to/sample.json
```

### Known Differences from Row Path

1. **Shock rolling aggregates (warm-up window)**: The first 59 rows (window=60) differ between paths. The row path uses a growing Python list buffer; Polars rolling uses `min_samples=1`. After the window fills, results converge. The comparison helper exempts these rows from failure reporting.

2. **`drag_scrub_suspicion` UDF**: Uses `map_elements` with the shared `compute_drag_scrub_index` function. This is the one place a Python UDF is used. Performance impact is minimal but it prevents full vectorization of this channel.

3. **First-row `None` values**: Derivative-based channels (`speed_rate_*`, `platform_stability_score`, `full_throttle_resistance_index`, `drag_scrub_suspicion`, `platform_compression_index`) are `None` on the first row in both paths.

### Benchmark Results (Slices 1–3, 100k synthetic rows with shocks)

| Metric | Value |
|--------|-------|
| Row path | ~9.6s |
| Vector path | ~1.4s |
| Speedup | **~7×** |

### Adoption Checklist (Before Default Switch)

- [ ] Real .ibt data tested end-to-end through vector path
- [ ] `map_elements` UDF for `drag_scrub_suspicion` replaced with pure Polars expression
- [ ] Shock rolling aggregate warm-up difference documented for users
- [ ] Feature flag tested in CI with both modes
- [ ] `import_service` wired with `get_analysis_engine_mode()` dispatch
- [ ] Performance regression gate: vector path must be ≥3× faster at 10k rows

**Do not wire runtime usage until the checklist is complete.**
