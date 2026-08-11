# RaceLab Garage

RaceLab Garage is a local-first iRacing telemetry and setup-analysis desktop app. It turns `.ibt` telemetry into a clear test decision: which lap is useful, where speed was lost, what evidence supports the finding, and whether to keep, undo, or retest the setup change.

---

## Current MVP Features

- **Real .ibt ingestion** — binary parser for iRacing telemetry files with 275+ variables
- **Track Map File support** — track map file parser, centerline geometry, markers, sections, curvature derivation, distance-based interpolation, SVG rendering with platform event overlays and target zone highlighting
- **Track Map Cockpit** — two-panel layout (map + inspector), 16 data-aware layer toggles with live counts, heatmap modes (Normal/Density/Severity), section summary cards, mini event timeline, analysis summary panel, manual map association, 82 indexed maps
- **Track Map matching** — automatic track name normalization and scoring-based map-to-run matching with optional manual override
- **Session Manager** — create/list/get/update/delete/archive RaceLab sessions, add/remove runs, startup screen with New/Open/Delete
- **Laps Workspace** — lap table with stint map visualization, Stint Intelligence, Performance/Trust/Engineering Value scoring, and baseline/test subviews (Current Run, Windows, Stint Intelligence, All Sessions, Baselines, Test Basket)
- **Laps Stint Map** — compact colored-block visualization per lap with mode toggle (Engineering Value, Lap Time Delta, Validity, Falloff), selected lap highlight, best window outline
- **Pace Quality Scoring** — three-dimension system: Performance (speed/consistency/falloff/stress), Trust (validity/completeness/window/context), Engineering Value (combined). Percentage-based thresholds, caps for wreck/pit/<60% valid laps, deductions for missing data.
- **Test Basket** — persistent bottom-right drawer for collecting baseline/test laps, windows, and stints. Baseline/test slots with readiness state (ready/caution/not_valid/reference_mode), cross-session support, validation warnings, Swap/Clear/Review in Laps. Persists to localStorage across app restarts.
- **All Sessions / Baselines** — browse all imported runs with Add as Baseline/Test actions. Recommended baseline candidates (fastest clean lap, most recent run, best 10-lap EV window).
- **Platform/Aero Workbench** — stacked telemetry chart workbench (ECharts) with Platform/Rake, Speed/RPM, Drag/Scrub, Tires, Shocks, Grade/Pull subviews. Event markArea annotation bands.
- **Internal Compare Engine** — baseline vs test observation services and delta-trace tooling retained for Laps-owned review; policy authority remains in P19
- **Comparison review** — Laps-owned, observation-only comparison evidence; it cannot publish setup targets or policy decisions
- **Delta Traces** — per-channel delta traces with target zone highlighting (Speed/Platform, Ride Height, Tire presets)
- **Insights Engine** — automated observation of comparison traces, correlations, target zones, and sector evidence without setup authority
- **Notebook** — save evidence snapshots and edit notes/tags; notebook records cannot create setup policy, test plans, or setup memory
- **Setup Focus Mode** — 16 event types mapped to related setup keys; fields highlight/dim on event selection. Explicit/Inferred badges with tooltips. Diff vs Baseline toggle.
- **Evidence Inspector Source Stack** — structured observation sections with evidence navigation to Platform, Setup, and Map
- **Clickable Evidence Chips** — evidence chips in Overview open Platform/Setup. EvidenceCard clickable with Platform/Map actions.
- **Comprehensive UX Audit** — full page-by-page review completed (2026-05-28). P0-P3 priority matrix documented in `docs/future_ux_improvements.md`.
- **Learning/Race Mode** — toggle between short/direct (Race Mode) and verbose/coaching (Learning Mode) via L key or mode badge click. Both modes use the same server authority.
- **Evidence-gated Engineering Systems** — driver/line, braking, corner rotation, tire state, damper response, aero-platform, relative-resistance, powertrain/gearing, stint-strategy, and simulator-integrity analysis. Missing or incompatible evidence produces an explicit holdback instead of a fabricated answer.
- **Physical-position Comparison** — future runs are aligned by track position with coverage gaps, phase context, alignment quality, and empirical-noise reporting; sample index is never treated as track position.
- **P19 Controlled Workflow** — the sole public setup authority. Exact-session P19 reasoning must authorize and bind one adjacent setup target before an A/B/A2 workflow can be persisted; P19 also validates its Keep/Undo/retest result.
- **Keyboard Shortcuts** — Esc clear, M/P/O/C/N workspace nav, L mode toggle, ←/→ event navigation
- **Persistent Evidence Inspector** — right-side observation inspector with event selection, evidence cards, and setup linkage
- **Local SQLite persistence** — imported runs, laps, events, setup snapshots, segments, notebook observations, exact P19 workflow history, and RaceLab sessions stored locally
- **112+ calculated channels** — ride heights, rake, dynamic pressure, tire pressure gain, temp/wear spread, slip ratio, shock velocity/activity/RMS, damper energy, motion g-conversions, platform pitch/roll estimates, kinematic slip angles, dynamic grade, aero load index, drag/scrub suspicion, platform compression, stability scores, rear scrape detection, platform balance classification
- **Signal smoothing helpers** — Savitzky-Golay 5-point and centered SMA smoothing (opt-in, pure Python, zero-phase)
- **Vehicle Dynamics Engine** — 6 physics modules: aero coefficients, tire dynamics (slip angles, understeer gradient), vehicle dynamics (weight transfer, brake energy), geometry (pitch/roll with motion ratios), estimate confidence, physics inputs
- **Vectorized Analysis Pipeline** — default Polars path with parity coverage against row fallback, frame-native overview consumers, and no full-row materialization in the normal import path.
- **Engine Comparison Script** — `scripts/compare_analysis_engines.py` for validating vector vs row path on real data
- **Extrema-preserving downsampling** — CFS minimums and event peaks never lost in chart views
- **Adversarial regression coverage** — unit, integration, API-contract, frontend-contract, parity, and benchmark checks

## Proxy Disclaimer

Aerodynamic load, downforce, drag, and diffuser values are **proxy estimates only** — not exact force measurements. The `.ibt` format does not include direct force channels. All aero/load values:
- Are labeled as "ESTIMATE" or "proxy"
- Display with dashed lines and "(proxy)" badge in charts
- Carry confidence penalties for missing motion ratios, high-G transients, and high shock activity
- Are relative and intended for comparison direction, not absolute values

Tire slip ratio is a proxy — no true slip measurement exists in `.ibt`.

Draft detection/classification is removed from active runtime and product decisions.

---

## Desktop App

RaceLab Garage is intended to be used as a desktop app. Recommended launch:

```powershell
.\scripts\start_desktop.ps1
```

This starts the RaceLab Engine backend on `127.0.0.1:8010` and opens a native Tauri window. The backend remains bound to the local machine only.

Production desktop build:

```powershell
.\scripts\build_desktop.ps1
```

User `.ibt`, `.sto`, track map files, reports, cache files, setup snapshots, Notebook findings, and SQLite data stay on this machine.

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
# Fast suite (excludes tests explicitly marked slow or integration)
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
4. **Import a track map file** — via file picker or folder import for spatial overlays
5. **Browse Laps** — view lap table, stint map, Performance/Trust/Engineering Value badges
6. **Add to Test Basket** — set baseline/test from Laps, All Sessions, Baselines, or Stint Intelligence
7. **Open Platform Workbench** — inspect ride heights, rake, dynamic pressure, tire pressure/temp/slip via ECharts
8. **Open Track Map** — view centerline geometry with platform event markers, heatmaps, section cards, and layer toggles
9. **Review Stint Intelligence** — compare baseline/test stints inline from Laps
10. **Review comparison observations** — inspect physical-position evidence in Laps without treating it as a setup verdict
11. **Explore Delta Traces** — see per-channel deltas by lap position with target zone highlight
12. **Check Setup Relevance** — highlighted setup fields linked to selected event, Explicit/Inferred badges
13. **Ask Engineer** — review the canonical P19 report, competing causes, evidence, and best measurement
14. **Open Dial-In** — review observational hypotheses; exact direction and target remain hidden unless P19 authorizes them
15. **Start a controlled workflow** — bind the exact session, run, setup, build, laps, events, and P19 reasoning identity before persistence
16. **Run A/B/A2** — record three eligible cohorts while changing only the authorized control
17. **Review P19 outcome** — Keep/Undo/retest policy appears only after P19 validates the controlled result
18. **Save Notebook observation** — preserve evidence and user notes without creating setup authority

---

## Feature Flags

| Flag | Default | Description |
|---|---|---|
| `RACELAB_ANALYSIS_ENGINE` | `vectorized` | Use `row` only for forced/debug fallback and parity checks. Normal runtime remains vectorized + frame-native. |

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
GET  /api/runs/{id}/platform-events-report
GET  /api/runs/{id}/telemetry-capabilities
GET  /api/runs/{id}/shock-reader
GET  /api/runs/{id}/setup
GET  /api/runs/{id}/report
POST /api/runs/{id}/dial-in
POST /api/compare
GET  /api/compare/preview
POST /api/compare/delta-traces
POST /api/compare/insights
POST /api/compare/engineering-systems
POST /api/runs/relative-resistance/aba
GET  /api/runs/{id}/powertrain-gearing
GET  /api/runs/{id}/stint-strategy
POST /api/notebook/findings/from-comparison
GET  /api/notebook/findings
GET  /api/notebook/findings/{id}
PATCH /api/notebook/findings/{id}
GET  /api/runs/{id}/intelligence?session_id={session_id}
POST /api/engineering/workflows (requires exact session_id; server binds current P19 authority)
GET  /api/engineering/workflows
POST /api/engineering/workflows/{workflow_id}/stages/{stage}
POST /api/engineering/workflows/{workflow_id}/score
POST /api/engineering/workflows/{workflow_id}/cancel
POST /api/sessions (create RaceLab session)
GET  /api/sessions (list sessions)
GET  /api/sessions/{id} (get session)

Platform event visibility:
- `/api/runs/{id}/platform-events` keeps backend evidence events in the payload.
- Each platform event now carries `display_scope`, `is_visible_default`, `reason_for_hidden`, and `contributes_to_backend_evidence`.
- The default driver UI shows actionable/watch events only.
- Proxy/internal evidence can still be shown on demand and remains available to backend consumers such as Dial-In and evidence adapters.
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
- Track map decoding is partial/centerline only — no GPS, boundaries, banking, or track width
- Aero/downforce/drag values are **proxy/relative only** — no exact force measurement exists in `.ibt`
- Tire wear/falloff conclusions require longer runs for confidence
- Tire temp/wear data may be unavailable on short runs
- No cloud sync — all data is local only
- Native Tauri file dialogs scaffolded and wired for `.ibt` and track map file import; browser file input preserved as fallback
- No setup editor or live setup comparison
- Vectorized engine validated on Talladega oval only — road course and short-track real .ibt samples pending
- Dynamic track-type weighting deferred — insufficient .ibt variety for validation
- Global unit toggle deferred/design-only — high risk, needs architecture change
- Ghost lap proxy deferred/design-only — no implementation yet

---

## For AI Workers

See `AGENTS.md` for product rules (evidence first, no junk-lap conclusions, proxy honesty, one change at a time, telemetry-truth first).

Vectorized analysis is the default runtime path; row mode is retained as fallback/debug parity only.

Verification evidence is recorded in `ROADMAP.md` and `TESTING.md`; do not infer current authority from historical feature descriptions.

