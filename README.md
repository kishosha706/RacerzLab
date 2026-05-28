# RaceLab Garage

RaceLab Garage is a local-first iRacing telemetry and setup-analysis desktop app. It turns `.ibt` telemetry into a clear test decision: which lap is useful, where speed was lost, what evidence supports the finding, and whether to keep, undo, or retest the setup change.

---

## Current MVP Features

- **Real .ibt ingestion** — binary parser for iRacing telemetry files with 275+ variables
- **.mt2 Track Map support** — MoTeCTrackV2 binary parser, centerline geometry, markers, sections, curvature derivation, distance-based interpolation, SVG rendering with platform event overlays and target zone highlighting
- **Track Map Cockpit** — two-panel layout (map + inspector), 16 data-aware layer toggles with live counts, heatmap modes (Normal/Density/Severity), section summary cards, mini event timeline, analysis summary panel, manual map association, 82 indexed maps
- **Track Map matching** — automatic track name normalization and scoring-based map-to-run matching with optional manual override
- **Session Manager** — create/list/get/update/delete/archive RaceLab sessions, add/remove runs, startup screen with New/Open/Delete
- **Lap Time Browser** — compact sidebar with out/timed/in lap classification, lap times (M:SS.sss), deltas (+/-/BEST), validity icons
- **Platform/Aero Workbench** — MoTeC-style stacked chart workbench (ECharts) with Platform/Rake, Speed/RPM, Drag/Scrub, Tires, Shocks, Grade/Pull subviews
- **Compare Workbook** — baseline vs test lap comparison by lap percentage with verdict, whole-car index, four corners, tires, shocks, driver, engine, and delta traces views
- **Did-It-Work Card** — standalone verdict component with evidence, test discipline score, target-zone/splitter/scrub deltas, warnings, setup changes, and action buttons (Save Finding, Create Test, Open Setup, Open Evidence)
- **Delta Traces** — per-channel delta traces with target zone highlighting (Speed/Platform, Ride Height, Tire presets)
- **Insights Engine** — automated interpretation of comparison results with trace annotations, correlations, target zone classification, confidence-weighted verdicts, and sector intelligence
- **Notebook & Setup Memory** — save findings, edit notes/tags/status, duplicate detection, create test plans, copy Markdown export, view setup memory dashboard with per-car/track summaries
- **Setup Relevance** — 16 event types mapped to related setup keys; fields highlight/dim on event selection
- **Learning/Race Mode** — toggle between short/direct (Race Mode) and verbose/coaching (Learning Mode) via L key or mode badge click. Mode-aware copy in Overview, Crew Chief, and inspector.
- **Keyboard Shortcuts** — Esc clear, M/P/O/C/N workspace nav, L mode toggle, ←/→ event navigation
- **Persistent Evidence Inspector** — right-side Crew Chief panel with event selection, evidence cards, setup linkage, and next-action buttons
- **Local SQLite persistence** — imported runs, laps, events, setup snapshots, recommendations, segments, notebook findings, test plans, and RaceLab sessions stored locally
- **112+ calculated channels** — ride heights, rake, dynamic pressure, tire pressure gain, temp/wear spread, slip ratio, shock velocity/activity/RMS, damper energy, motion g-conversions, platform pitch/roll estimates, kinematic slip angles, dynamic grade, aero load index, drag/scrub suspicion, platform compression, stability scores, rear scrape detection, platform balance classification
- **Vehicle Dynamics Engine** — 6 physics modules: aero coefficients, tire dynamics (slip angles, understeer gradient), vehicle dynamics (weight transfer, brake energy), geometry (pitch/roll with motion ratios), estimate confidence, physics inputs
- **Vectorized Analysis Pipeline** — parallel Polars path (opt-in via `RACELAB_ANALYSIS_ENGINE` env var) with 26× speedup at 10k rows, 111 core channels, full parity with row path across 38 synthetic tests + real Talladega validation. Row engine remains production default.
- **Engine Comparison Script** — `scripts/compare_analysis_engines.py` for validating vector vs row path on real data
- **Extrema-preserving downsampling** — CFS minimums and event peaks never lost in chart views
- **310+ tests** — unit, integration, parity, benchmarks; fast suite <1s

## Proxy Disclaimer

Aerodynamic load, downforce, drag, and diffuser values are **proxy estimates only** — not exact force measurements. The `.ibt` format does not include direct force channels. All aero/load values:
- Are labeled as "ESTIMATE" or "proxy"
- Display with dashed lines and "(proxy)" badge in charts
- Carry confidence penalties for missing motion ratios, high-G transients, and high shock activity
- Are relative and intended for comparison direction, not absolute values

Tire slip ratio is a proxy — no true slip measurement exists in `.ibt`.

---

## Desktop App

RaceLab Garage is intended to be used as a desktop app. Recommended launch:

```powershell
.\scripts\start_desktop.ps1
```

This starts the RaceLab Engine backend on `127.0.0.1:8000` and opens a native Tauri window. The backend remains bound to the local machine only.

Production desktop build:

```powershell
.\scripts\build_desktop.ps1
```

User `.ibt`, `.sto`, `.mt2`, reports, cache files, setup snapshots, Notebook findings, and SQLite data stay on this machine.

---

## Prerequisites

- Python 3.11+
- Node.js 20+ with npm
- Rust/Cargo from rustup
- Tauri system prerequisites for Windows

## Python Setup

```powershell
cd racelab-garage
.\scripts\setup_python.ps1
```

## Run Tests

```powershell
# Fast suite (<1s)
python -B -m pytest -m "not slow and not integration" -q

# Full suite including .ibt-dependent tests
pytest
```

See [TESTING.md](TESTING.md) for full details.

---

## Core Workflow

1. **Create or open a RaceLab session** — via the startup screen
2. **Import baseline .ibt** — via file picker or `POST /api/imports/ibt`
3. **Import test .ibt** — your experimental setup or driving change
4. **Import .mt2 track map** — via file picker or folder import for spatial overlays
5. **Browse laps** — open the Lap Time Browser to see classification, lap times, and deltas
6. **Open Platform Workbench** — inspect ride heights, rake, dynamic pressure, tire pressure/temp/slip via ECharts
7. **Open Track Map** — view centerline geometry with platform event markers, heatmaps, section cards, and layer toggles
8. **Open Compare** — select baseline/test laps, run comparison
9. **Review Verdict** — keep/undo/retest with confidence score, evidence, and Did-It-Work card
10. **Explore Delta Traces** — see per-channel deltas by lap position with target zone highlight
11. **Check Setup Relevance** — highlighted setup fields linked to selected event
12. **Save Finding** — persist the comparison result to the Notebook
13. **Edit Notes/Tags/Status** — add context, change confirmation status
14. **Create Test Plan** — define the next controlled test
15. **Setup Memory** — review the aggregate picture of what has worked

---

## Feature Flags

| Flag | Default | Description |
|---|---|---|
| `RACELAB_ANALYSIS_ENGINE` | `row` | Set to `vectorized` for Polars-accelerated channel calculations (26× faster at 10k rows). Opt-in only — default switch blocked pending road course validation. |

---

## API Endpoints

```
GET  /api/health
POST /api/imports/ibt (multipart upload; JSON {path} is dev/local-only)
POST /api/imports/mt2 (multipart upload)
POST /api/imports/mt2-folder (JSON {folder_path})
GET  /api/track-maps
GET  /api/track-maps/{id}
GET  /api/runs/{id}/track-map-match
GET  /api/runs/{id}/track-map-package
GET  /api/runs
GET  /api/runs/{id}/overview
GET  /api/runs/{id}/laps
GET  /api/runs/{id}/channels
GET  /api/runs/{id}/trace
GET  /api/runs/{id}/platform-events
GET  /api/runs/{id}/setup
GET  /api/runs/{id}/report
POST /api/compare
GET  /api/compare/preview
POST /api/compare/delta-traces
POST /api/compare/insights
POST /api/notebook/findings/from-comparison
GET  /api/notebook/findings
GET  /api/notebook/findings/{id}
PATCH /api/notebook/findings/{id}
POST /api/notebook/findings/{id}/test-plan
GET  /api/notebook/test-plans
PATCH /api/notebook/test-plans/{id}
GET  /api/notebook/setup-memory
POST /api/sessions (create RaceLab session)
GET  /api/sessions (list sessions)
GET  /api/sessions/{id} (get session)
PATCH /api/sessions/{id} (update session)
DELETE /api/sessions/{id} (delete session, keeps telemetry)
POST /api/sessions/{id}/archive (archive session)
POST /api/sessions/{id}/runs (add run to session)
DELETE /api/sessions/{id}/runs/{run_id} (remove run from session)
GET  /api/sessions/{id}/runs/{run_id}/laps (session-scoped lap list)
GET  /api/sessions/runs/{run_id}/laps (standalone lap list)
```

---

## Known Limitations

- `.sto` setup file decoding is not yet implemented
- `.mt2` decoding is partial/centerline only — no GPS, boundaries, banking, or track width
- Aero/downforce/drag values are **proxy/relative only** — no exact force measurement exists in `.ibt`
- Tire wear/falloff conclusions require longer runs for confidence
- Tire temp/wear data may be unavailable on short runs
- No cloud sync — all data is local only
- Native Tauri file dialogs not yet implemented (uses browser file input)
- No setup editor or live setup comparison
- Vectorized engine validated on Talladega oval only — road course and short-track real .ibt samples pending

---

## For AI Workers

See `AGENTS.md` for product rules (evidence first, no junk-lap conclusions, proxy honesty, one change at a time, draft vs solo separation).

See `racelab_engine/analysis/DESIGN_NOTES_vectorized_future.md` for the vectorized engine adoption plan and validation status.
