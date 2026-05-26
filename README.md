# RaceLab Garage

RaceLab Garage is a local-first iRacing telemetry and setup-analysis desktop app. It turns `.ibt` telemetry into a clear test decision: which lap is useful, where speed was lost, what evidence supports the finding, and whether to keep, undo, or retest the setup change.

---

## Current MVP Features

- **Real .ibt ingestion** — binary parser for iRacing telemetry files with 275+ variables
- **Platform/Aero Workbench** — MoTeC-style stacked chart workbench with Platform/Rake, Speed/RPM, Drag/Scrub, and Tires presets
- **Compare Workbook** — baseline vs test lap comparison by lap percentage with verdict, whole-car index, four corners, tires, shocks, driver, and engine views
- **Delta Traces** — per-channel delta traces with target zone highlighting (Speed/Platform, Ride Height, Tire presets)
- **Insights Engine** — automated interpretation of comparison results with trace annotations, correlations, target zone classification, confidence-weighted verdicts, and sector intelligence
- **Notebook & Setup Memory** — save findings, edit notes/tags/status, duplicate detection, create test plans, copy Markdown export, view setup memory dashboard with per-car/track summaries
- **Local SQLite persistence** — imported runs, laps, events, setup snapshots, findings, and test plans stored locally
- **70+ calculated channels** — ride heights, rake, dynamic pressure, tire pressure gain, temp/wear spread, slip ratio proxy, shock velocity, motion g-conversions, platform pitch/roll estimates
- **Extrema-preserving downsampling** — CFS minimums and event peaks never lost in chart views

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
pytest
```

The Talladega acceptance tests use the default fixture at:
```text
C:\Users\Soulj\Documents\iRacing\telemetry\stockcars camarozl12018_talladega 2026-05-07 15-05-45.ibt
```

Override via:
```powershell
$env:RACELAB_TALLADEGA_IBT="C:\path\to\baseline.ibt"
pytest
```

---

## Core Workflow

1. **Import baseline .ibt** — via file picker or `POST /api/imports/ibt`
2. **Import test .ibt** — your experimental setup or driving change
3. **Open Platform Workbench** — inspect ride heights, rake, dynamic pressure, tire pressure/temp/slip
4. **Open Compare** — select baseline/test laps, run comparison
5. **Review Verdict** — keep/undo/retest with confidence score and evidence
6. **Explore Delta Traces** — see per-channel deltas by lap position with target zone highlight
7. **Save Finding** — persist the comparison result to the Notebook
8. **Edit Notes/Tags/Status** — add context, change confirmation status
9. **Create Test Plan** — define the next controlled test
10. **Setup Memory** — review the aggregate picture of what has worked

---

## API Endpoints

```
GET  /api/health
POST /api/imports/ibt (multipart upload; JSON {path} is dev/local-only)
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
```

---

## Known Limitations

- `.sto` setup file decoding is not yet implemented
- `.mt2` track map decoding is not yet implemented
- Aero/downforce/drag values are **proxy/relative only** — no exact force measurement exists in `.ibt`
- Tire wear/falloff conclusions require longer runs for confidence
- Tire temp/wear data may be unavailable on short runs
- No cloud sync — all data is local only
- Native Tauri file dialogs not yet implemented (uses browser file input)
- No setup editor or live setup comparison

---

## For AI Workers

See `docs/ENGINEERING_CONTRACTS.md` for:
- Channel classification rules (raw/calculated/proxy)
- Proxy wording requirements
- Compare contract (same-run identity, lap-percent alignment)
- Missing-data behavior
- Confidence tier definitions
- Notebook dependency rule: "Save comparison/insight payloads as-is. Do not recompute."
