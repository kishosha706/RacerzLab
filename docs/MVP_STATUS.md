# RaceLab Garage — MVP Status

**Date:** 2026-05-26

---

## Completed Systems

| System | Status | Notes |
|---|---|---|
| .ibt binary parser | **Complete** | 275 variables, header, session YAML, telemetry records |
| .mt2 track map parser | **Complete** | MoTeCTrackV2 binary parser, 36 maps imported, Atlanta: 1,911 pts, 8,014 ft, 4 markers, 4 sections |
| Track Map matching | **Complete** | 28 iRacing track name→slug mappings, layout inference, confidence-scored matching |
| Track Map UI | **Complete** | SVG centerline rendering, marker/event/target-zone toggles, honest warnings, nav "Map" tab |
| SQLite persistence | **Complete** | Runs, laps, events, setup snapshots, notebook, test plans |
| Telemetry normalization | **Complete** | 70+ calculated channels, unit conversions, g-projection |
| Platform/Aero Workbench | **Complete** | MoTeC-style charts, 5 presets (Platform/Rake, Speed/RPM, Drag/Scrub, Tires), CFS bands, extrema downsampling |
| Compare Workbook | **Complete** | Verdict, WCI, Four Corners, Tires, Shocks, Driver, Engine |
| Delta Traces | **Complete** | 3 presets, target zone highlighting, per-channel deltas |
| Insights Engine | **Complete** | Automated interpretation from comparison |
| Notebook & Setup Memory | **Complete** | Save findings, edit notes/tags/status, duplicate detection, test plans, setup memory dashboard |
| Markdown Export | **Complete** | Copy finding as Markdown to clipboard |
| Channel Classification | **Complete** | raw/calculated/proxy with metadata, cross-run comparability |
| Proxy Honesty | **Complete** | All aero/load/slip values marked proxy with warnings |
| Same-Run Guard | **Complete** | Explicit run_id + lap identity, not zero-delta inference |
| Local-Only Audit | **Complete** | Backend 127.0.0.1, no remote APIs, no analytics |
| Circular Import Resolution | **Complete** | Moved serializer functions from `compare_math.py` to `comparison.py`, removed lazy import hack |
| SQLite WAL Mode | **Complete** | Enabled WAL journal mode for safer concurrent reads |
| Import Path Safety | **Complete** | JSON path import hardened with file-exists, is-file, .ibt-extension, and path-traversal checks |
| Codebase Gap Scan | **Complete** | Unused imports removed, dead `.bak` file deleted, missing TS contract fields added, null guards added, silent error handling improved |

---

## Validation Status

| Check | Result |
|---|---|
| Backend tests | 101/101 pass |
| Codebase gap scan | 11 issues found and fixed |
| TypeScript | Clean (`npx tsc --noEmit`) |
| Local-only audit | Pass |
| Build | `npm run build` successful |

---

## Current Limitations

| Limitation | Impact |
|---|---|
| `.sto` decoding not implemented | Cannot diff setup files directly — relies on SQLite setup snapshots |
| `.mt2` decoding — partial/centerline only | No GPS, boundaries, banking, or track width. Centerline + markers + sections supported. See `docs/TRACK_MAP_STRATEGY.md` |
| Aero/downforce are proxy only | No exact force values — relative direction only |
| Tire wear/falloff confidence | Requires longer runs for reliable conclusions |
| No native file dialog | Uses browser file input for .ibt import |
| No cloud sync | All data local only (design choice) |
| No auto-updater | Manual install required |
| No setup editor | Cannot modify setups within app |

---

## Scaffold / Dead Code Candidates

The following files exist in the codebase but are **not currently wired** into any route or service.
They are preserved as scaffold for future features but should be reviewed before the next major release:

| File | Status | Notes |
|---|---|---|
| `racelab_engine/analysis/lap_classification.py` | Scaffold | `classify_laps()` defined but never called |
| `racelab_engine/analysis/dynamic_crew_chief.py` | Scaffold | `build_recommendations()` defined but never called |
| `racelab_engine/analysis/confidence.py` | Scaffold | `AnalyzerStatus` and `apply_confidence_penalty()` defined but never imported |
| `racelab_engine/analysis/drag_scrub.py` | Partial | Functions exist but may overlap with `calculated_channels.py` drag/scrub logic |

## Known Risks

- **Long .ibt import time** — 5-10 seconds for 6000-row files; test suite uses module-scoped fixture for caching
- **Memory on large files** — full telemetry rows kept in memory during import; may need streaming for endurance races
- **Tauri build not CI-tested** — build_desktop.ps1 verified manually
- **No telemetry streaming** — real-time iRacing data feed not supported

---

## Next Recommended Features

1. `.sto` setup file decoding for native setup diff
2. Native Tauri file picker for .ibt/.mt2 import
3. Shocks preset in Platform Workbench (shock velocity, activity index)
4. Engine/Pull preset in Platform Workbench (RPM, fuel, manifold)
5. Setup impact analysis from long-term notebook findings
6. Track map overlay refinement — event click → cursor sync, delta trace overlays
7. Real-time telemetry streaming from iRacing

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
| Test suite passes | **Yes** (101/101) |
| TypeScript clean | **Yes** |
| Local-only audit passes | **Yes** |
| Build succeeds | **Yes** |
| No external runtime dependencies | **Yes** |
| Backend binds 127.0.0.1 only | **Yes** |

---

**MVP Status:** Ready for local desktop use.
