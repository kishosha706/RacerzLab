# RaceLab Garage — MVP Status

**Date:** 2026-05-28

---

## Completed Systems

| System | Status | Notes |
|---|---|---|
| .ibt binary parser | **Complete** | 275 variables, header, session YAML, telemetry records |
| .mt2 track map parser | **Complete** | MoTeCTrackV2 binary parser, 36 maps imported, Atlanta: 1,911 pts, 8,014 ft, 4 markers, 4 sections |
| Track Map matching | **Complete** | 28 iRacing track name→slug mappings, layout inference, confidence-scored matching |
| Track Map UI | **Complete** | SVG centerline rendering, marker/event/target-zone toggles, honest warnings, nav "Map" tab |
| Track Map Identity | **Complete** | "Loaded Run" section (track/car/setup from .ibt), "Matched Map" section (.mt2 filename + confidence badge), telemetry-derived fallback messaging |
| SQLite persistence | **Complete** | Runs, laps, events, setup snapshots, notebook, test plans, RaceLab sessions |
| Telemetry normalization | **Complete** | 70+ calculated channels, unit conversions, g-projection |
| Platform/Aero Workbench | **Complete** | MoTeC-style charts, 5 presets (Platform/Rake, Speed/RPM, Drag/Scrub, Tires), CFS bands, extrema downsampling |
| Compare Workbook | **Complete** | Verdict, WCI, Four Corners, Tires, Shocks, Driver, Engine |
| Delta Traces | **Complete** | 3 presets, target zone highlighting, per-channel deltas |
| Insights Engine | **Complete** | Automated interpretation from comparison |
| Notebook & Setup Memory | **Complete** | Save findings, edit notes/tags/status, duplicate detection, test plans, setup memory dashboard |
| Session Manager | **Complete** | Create/list/get/update/delete/archive RaceLab sessions, add/remove runs, startup screen with New/Open/Delete, session-scoped lap lists |
| Lap Time Browser | **Complete** | Compact sidebar with out/timed/in classification, lap times (M:SS.sss), deltas (+/-/BEST), validity icons, selected lap highlight |
| Startup Flow | **Complete** | StartupScreen on launch with New Session button, Previous Sessions list, delete confirmation ("Telemetry files stay.") |
| Markdown Export | **Complete** | Copy finding as Markdown to clipboard |
| Channel Classification | **Complete** | raw/calculated/proxy with metadata, cross-run comparability |
| Proxy Honesty | **Complete** | All aero/load/slip values marked proxy with warnings |
| Same-Run Guard | **Complete** | Explicit run_id + lap identity, not zero-delta inference |
| Local-Only Audit | **Complete** | Backend 127.0.0.1, no remote APIs, no analytics |
| Circular Import Resolution | **Complete** | Moved serializer functions from `compare_math.py` to `comparison.py`, removed lazy import hack |
| SQLite WAL Mode | **Complete** | Enabled WAL journal mode for safer concurrent reads |
| Import Path Safety | **Complete** | JSON path import hardened with file-exists, is-file, .ibt-extension, and path-traversal checks |
| Codebase Gap Scan | **Complete** | Unused imports removed, dead `.bak` file deleted, missing TS contract fields added, null guards added, silent error handling improved |
| Vehicle Dynamics Engine | **Complete** | 6 new physics modules: estimate_confidence, physics_inputs, aero_coefficients, vehicle_dynamics, tire_dynamics, geometry. 50 new tests. |
| Vectorized Analysis Pipeline | **Complete** | Parallel Polars path (opt-in) with 7× speedup at 100k rows. Feature flag: RACELAB_ANALYSIS_ENGINE. |
| Channel Metadata Audit | **Complete** | 44 missing metadata entries added, formulas verified against actual code, dependencies corrected. |
| Pace Quality Scoring | **Complete** | Three-dimension scoring: Performance, Trust, Engineering Value. Percentage-based consistency/falloff thresholds. Caps for wreck/pit/<60%/draft. Deductions for missing data. |
| Lap Windows Analysis | **Complete** | Best consecutive windows, fastest individual groups, degradation/falloff analysis. Pace quality integrated into all window summaries. |
| Lap Scoring Stabilization | **Complete** | classify_pace_trust_relationship() helper. Master assertions doc. Future track-profile scaffolding doc. 63 tests. |
| Compare Basket | **Complete** | Persistent bottom-right drawer. Baseline/test slots with readiness state. Cross-session support. Validation warnings. Swap/clear/remove/Open Compare. |
| Laps Stint Map | **Complete** | Colored-block visualization per lap. 4 mode toggles (EV, delta, draft, falloff). Selected lap, best window, draft/invalid markers. |
| Clickable Evidence Chips | **Complete** | Evidence chips in OverviewTab open Platform/Setup. EvidenceCard clickable with Platform/Map actions. |
| Setup Diff Toggle | **Complete** | Current Setup / Diff vs Baseline toggle. Baseline → test value pairs with changed/unchanged styling. |
| Setup Focus Explicit/Inferred | **Complete** | Green Explicit badge ("Provided by event metadata"), amber Inferred badge ("Suggested from event type mapping"). |
| Trace markArea Event Bands | **Complete** | Translucent event annotation bands on PlatformTab charts, color-coded by severity. |
| Overview Zero-Event State | **Complete** | "No critical events detected" with Open Laps/Platform/Compare actions. |
| Raw Channels Pin-to-Workbench | **Complete** | Pin/copy/open-in-platform actions per channel. Pinned channels persist in sessionStorage. |
| Evidence Inspector Source Stack | **Complete** | Structured sections: Where, What, Evidence, Related Setup, Decision with action buttons. |
| Workspace Persistence | **Complete** | Last workspace saved to localStorage, restored on app load. |
| channelMeta confidenceLevel | **Complete** | getChannelConfidenceLevel() helper returning measured/calculated/estimate/proxy. |
| Cross-Session Compare Basket | **Complete** | date/session_name/has_setup_snapshot fields. Enhanced warnings for cross-session, setup, weather. Readiness state. |
| All Sessions / Baselines in LapsTab | **Complete** | Subview navigation: Current Run, Windows, All Sessions, Baselines, Basket. All Sessions lists runs with basket actions. Baselines shows recommended candidates. |
| CrewChiefSummary Controlled Collapse | **Complete** | Fully controlled React component via onToggle, no dual source of truth. |
| EvidenceInspector Memoization | **Complete** | Data coverage counts wrapped in useMemo. |

---

## Validation Status

| Check | Result |
|---|---|
| Backend tests | 489/489 pass |
| TypeScript | Clean (`npx tsc --noEmit`) |
| Local-only audit | Pass |
| Build | `npm run build` successful |

---

## Current Limitations

| Limitation | Impact |
|---|---|
| `.sto` decoding not implemented | Cannot diff setup files directly — relies on SQLite setup snapshots |
| `.mt2` decoding — partial/centerline only | No GPS, boundaries, banking, or track width. Centerline + markers + sections supported |
| Aero/downforce are proxy only | No exact force values — relative direction only |
| Tire wear/falloff confidence | Requires longer runs for reliable conclusions |
| No native file dialog | Uses browser file input for .ibt import |
| No cloud sync | All data local only (design choice) |
| No auto-updater | Manual install required |
| No setup editor | Cannot modify setups within app |
| No dynamic track-type weighting | Deferred until more .ibt variety collected |
| No global unit toggle | Deferred — high risk, needs architecture |
| No lazy-load for heavy tabs | Tabs use named exports, need default export conversion |

---

## Scaffold / Dead Code Candidates

The following files exist in the codebase but are **not currently wired** into any route or service.
They are preserved as scaffold for future features but should be reviewed before the next major release:

| File | Status | Notes |
|---|---|---|
| `racelab_engine/analysis/lap_classification.py` | Scaffold | `classify_laps()` defined but never called |
| `racelab_engine/analysis/dynamic_crew_chief.py` | Scaffold | `build_recommendations()` defined but never called |
| `racelab_engine/analysis/confidence.py` | Scaffold | `AnalyzerStatus` and `apply_confidence_penalty()` defined but never imported |
| `racelab_engine/analysis/drag_scrub.py` | Complete | Aero-normalized resistance, drag/scrub suspicion index, risk zone detection |
| `racelab_engine/analysis/vectorized_channels.py` | Complete (opt-in) | Parallel Polars analysis path, 7× speedup at 100k rows, full parity with row path |
| `racelab_engine/analysis/geometry.py` | Complete | SI-first pitch/roll with motion-ratio hooks |
| `racelab_engine/analysis/tire_dynamics.py` | Complete | Slip angles, understeer gradient, tire utilization, thermal origin |
| `racelab_engine/analysis/vehicle_dynamics.py` | Complete | Weight transfer, curvature/yaw math, brake energy, wheel power |
| `racelab_engine/analysis/aero_coefficients.py` | Complete | Air-relative dynamic pressure, CdA proxy, coastdown validity gating |
| `racelab_engine/analysis/estimate_confidence.py` | Complete | EstimateConfidence dataclass, confidence_from_missing() |
| `racelab_engine/analysis/physics_inputs.py` | Complete | VehiclePhysicsInputs with resolve_motion_ratio_corner() |

## Known Risks

- **Long .ibt import time** — 5-10 seconds for 6000-row files; test suite uses module-scoped fixture for caching
- **Memory on large files** — full telemetry rows kept in memory during import; may need streaming for endurance races
- **Tauri build not CI-tested** — build_desktop.ps1 verified manually
- **No telemetry streaming** — real-time iRacing data feed not supported

---

## Next Recommended Features

1. `.sto` setup file decoding for native setup diff
2. Native Tauri file picker for .ibt/.mt2 import
3. Dynamic track-type weighting for pace quality scoring
4. Global unit system toggle (imperial/metric/mixed)
5. Lazy-load heavy tabs via React.lazy (convert to default exports)
6. Setup impact analysis from long-term notebook findings
7. Real-time telemetry streaming from iRacing
8. Wire vectorized engine as default (after adoption checklist complete)
9. Frequency-domain shock analysis module
10. Aero map regression from telemetry

---

## Release Readiness Checklist

| Item | Status |
|---|---|
| Core product loop works | **Yes** |
| Import → Inspect → Compare → Save → Review | **Yes** |
| Smoke test documented | **Yes** (`docs/SMOKE_TEST_MVP.md`) |
| README accurate | **Yes** |
| SECURITY.md reflects local-only storage | **Yes** |
| Engineering contracts documented | **Yes** (`docs/ENGINEERING_CONTRACTS.md`) |
| Lap scoring master assertions documented | **Yes** (`docs/lap_scoring_master_assertions.md`) |
| Future track-profile plan documented | **Yes** (`docs/lap_scoring_track_profiles_future.md`) |
| Future UX improvements documented | **Yes** (`docs/future_ux_improvements.md`) |
| Test suite passes | **Yes** (489/489) |
| TypeScript clean | **Yes** |
| Local-only audit passes | **Yes** |
| Build succeeds | **Yes** |
| No external runtime dependencies | **Yes** |
| Backend binds 127.0.0.1 only | **Yes** |

---

**MVP Status:** Ready for local desktop use. Cross-session workflow, lap scoring, Compare Basket, and stint map fully integrated.
