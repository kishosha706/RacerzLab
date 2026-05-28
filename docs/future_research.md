# Future Research Notes

This document captures design notes for systems that are **not implemented** in the current pass.
These are research topics — do not implement without profiling or data justification.

---

## 1. WebGL Traces

**Status:** Not implemented. ECharts is sufficient.

**When to consider:**
- Profiling shows ECharts is a bottleneck for >10 simultaneous trace panels
- Canvas 2D rendering causes frame drops during zoom/pan
- User reports lag on large multi-row trace layouts

**Current state:**
- ECharts uses `sampling: "lttb"`, `showSymbol: false`, `animation: false`
- Trace endpoint uses `downsample: "auto"` with `preserveExtrema: true`
- Typical trace has ~1,200 points after downsampling
- No performance complaints in current testing

**If needed:**
- Replace ECharts with uPlot (lightweight, WebGL-ready via canvas)
- Keep ECharts for tooltip-rich interactive panels
- Use uPlot for dense multi-row delta traces only

---

## 2. EKF Sensor Fusion

**Status:** Not implemented. Not justified without additional sensors.

**What EKF would provide:**
- Fuse GPS, accelerometer, wheel speed, steering into a unified state estimate
- Better curvature estimation (yaw rate + GPS vs steering-based)
- Grade estimation without surveyed elevation
- Side-slip angle estimation

**Why deferred:**
- iRacing .ibt already provides high-quality telemetry channels
- No IMU bias or GPS dropout to correct
- EKF tuning is track/car-specific and requires validation data
- Would add SciPy dependency for matrix operations

**If needed:**
- Implement as optional analysis mode (not default)
- Add `racelab_engine/analysis/ekf_fusion.py`
- Require GPS + yaw rate + wheel speed channels
- Validate against known track geometry

---

## 3. pybind11 / C++ Extensions

**Status:** Not implemented. Python is fast enough.

**When to consider:**
- .ibt import takes >5 seconds for a single file
- Segment building or trace downsampling is CPU-bound
- Vectorized engine (Polars) is insufficient

**Current state:**
- .ibt import: ~0.5-1.5 seconds for typical files
- Trace downsampling: <100ms
- Segment building: <200ms
- No performance bottleneck identified

**If needed:**
- Profile with `cProfile` first
- Extract hot loops to C++ via pybind11
- Keep Python API unchanged; C++ is internal optimization

---

## 4. Tire Degradation Model

**Status:** Not implemented. Requires multi-lap/stint data.

**What a tire model would provide:**
- Grip falloff vs lap count
- Optimal pressure window
- Wear rate vs track temperature
- Camber wear pattern confirmation

**Why deferred:**
- Current test data is single-lap or short-run only
- No multi-stint iRacing data available for validation
- Tire model would be speculative without stint-length telemetry
- Short-run warning already exists in UI

**When to consider:**
- After importing 10+ lap runs with consistent setup
- After collecting tire temperature trends across a stint
- When comparing setup changes over full fuel runs

---

## 5. Canvas Heatmap Layer (Track Map)

**Status:** Not implemented. SVG is sufficient.

**When to consider:**
- Track map with >10,000 points causes SVG rendering lag
- Heatmap overlay is too slow with SVG elements
- Profiling shows SVG rendering as a bottleneck

**Current state:**
- Track map uses SVG with ~3,000 points (typical)
- Section coloring uses SVG path elements
- No performance complaints

---

## 6. Machine Learning Classification

**Status:** Not implemented. Rule-based is preferred.

**What ML would provide:**
- Automated setup change recommendation
- Lap classification (draft vs solo) with higher accuracy
- Anomaly detection in telemetry

**Why deferred:**
- Rule-based classification is transparent and debuggable
- No labeled dataset for training
- ML would add dependencies (scikit-learn, ONNX)
- Current draft detection uses deterministic rules
