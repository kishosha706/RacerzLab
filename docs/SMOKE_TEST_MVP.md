# RaceLab Garage — MVP Smoke Test

Run through this workflow to verify the core product loop works end-to-end.

**Prerequisites:** Backend running, one baseline `.ibt` and one test `.ibt` imported.
**Last verified:** 2026-06-01 (step labels may need minor UI text refresh; treat any mismatch as needs verification, not failure of truth rules).

---

## 1. Launch
```powershell
cd racelab-garage
.\scripts\start_desktop.ps1
```
- App window opens titled "RaceLab Garage"
- Backend health check passes at `http://127.0.0.1:8010/api/health`

## 2. Startup Screen
- Verify: Startup screen appears with "New Session" button
- Verify: "No previous sessions" message shown on first launch
- Click "New Session"
- Verify: cockpit shell loads with empty state

## 3. Import Baseline Run
- Click the telemetry import action or use the file selector
- Select a baseline `.ibt` file
- Verify: run appears in run list dropdown
- Verify: overview shows track, car, lap count
- Verify: run is automatically added to the current RaceLab session

## 4. Import Test Run
- Import a second `.ibt` (the test/experimental run)
- Verify: two runs now appear in run selector
- Verify: both runs show car/track info

## 5. Select Useful Laps
- Verify: best useful lap is auto-selected for both runs
- Verify: run context bar shows track, car, lap

## 6. Lap Time Browser
- Click "Laps" in the toolbar
- Verify: sidebar opens showing lap list with out/timed/in classification
- Verify: lap times display as M:SS.sss format
- Verify: deltas show +0:NNN.NNN / -0:NNN.NNN / BEST
- Verify: green checkmark for useful laps, red X for invalid
- Verify: clicking a lap selects it and updates the trace
- Click "Laps" again to close sidebar

## 7. Import Track Map File
- Click the track map import action and select a track map file
- Verify: status shows the imported track map centerline point, marker, and section counts
- Verify: no crash for unsupported track map file variants (graceful warning)

## 8. Track Map View
- Navigate to "Map" in the nav rail
- Verify: "Loaded Run" identity section shows track name, car name, setup name from .ibt
- Verify: "Matched Map" section shows the imported map name with confidence badge (green=high, amber=medium)
- Verify: SVG centerline path renders
- Verify: markers toggle shows/hides imported map markers
- Verify: events toggle shows/hides platform event overlays
- Verify: target zone toggle shows/hides highlighted path segment
- Verify: warnings displayed for missing GPS/boundaries/banking

## 6b. Laps Workspace — Stint Map
- Navigate to "Laps" in the nav rail
- Verify: Stint Shape section shows colored blocks per lap
- Verify: mode toggles work (Eng Val, Δ Time, Validity, Falloff)
- Verify: selected lap highlighted with cyan outline
- Verify: best window outlined
- Verify: hover shows lap time and tags

## 6c. Laps Workspace — Performance/Trust/Engineering Value
- Verify: Best 10/20-Lap Avg cards show three badges
- Verify: Performance badge has tooltip
- Verify: Trust badge has tooltip
- Verify: Engineering Value badge has tooltip
- Verify: relationship label shown (e.g., "Strong clean pace")

## 6d. Laps Workspace — All Sessions / Baselines
- Click "All Sessions" subview
- Verify: all imported runs listed with car/track/setup/best-lap
- Verify: Set as Baseline and Set as Test buttons work
- Click "Baselines" subview
- Verify: recommended candidates shown (fastest clean lap, most recent run, best 10-lap EV)
- Verify: Add as Baseline buttons work

## 6e. Test Basket
- Add a lap as Test from Laps table (Gauge icon)
- Verify: Test Basket appears at bottom-right
- Verify: readiness badge shows (ready/caution/not_valid/reference_mode)
- Verify: warnings displayed for cross-session/missing-setup
- Verify: Swap and Clear buttons work
- Click Review in Laps
- Verify: Laps opens and baseline/test staging remains visible

## 7. Platform Workbench — Platform/Rake Preset
- Navigate to "Platform" in the nav rail
- Select "Platform" preset from the chart dropdown
- Verify: 5 stacked chart rows render (Throttle/Brake, Center Rake, Side Rake, CFS+LF+RF, LR+RR)
- Verify: CFS threshold bands visible (scrape/critical/high/watch)
- Verify: tooltip shows distance, per-channel values, "(proxy)" for proxy channels

## 8. Platform Workbench — Tires Preset
- Select "Tires" preset from the dropdown
- Verify: Tire Pressure, Pressure Gain, Temp Spread, Slip Ratio Proxy rows
- Verify: each row has LF/RF/LR/RR series with corner colors
- Verify: proxy channels (slip ratio) show dashed lines

## 7. Legacy Compare Engine
- Standalone Compare is hidden from the nav rail; use Laps and Stint Intelligence for baseline/test review
- Select baseline and test runs
- Click "Run Compare" if compare doesn't auto-load
- Verify: Verdict card shows keep_direction/undo/retest/inconclusive
- Verify: confidence score and evidence displayed

## 8. Compare — What Changed
- Click "What Changed" sub-tab
- Verify: setup changes grouped by category
- Verify: context changes with warnings

## 9. Compare — Whole Car Index
- Click "Index" sub-tab
- Verify: platform, driver, powertrain, discipline scores
- Verify: overall whole-car-index (0–100)

## 10. Compare — Four Corners
- Click "Four Corners" sub-tab
- Verify: LF/RF/LR/RR matrix with Ride Height, Shock Defl, Tire Pressure, Wheel Speed, Slip Ratio
- Verify: short-run confidence warning

## 11. Compare — Tires View
- Click "Tires" sub-tab
- Verify: per-corner pressure/wheel-speed/slip-ratio table
- Verify: corner-mini layout with ride height/shock/tire data

## 12. Compare — Driver View
- Click "Driver" sub-tab
- Verify: throttle, brake, steering averages with deltas

## 13. Delta Traces
- Click "Traces" sub-tab
- Verify: Speed/Platform Delta preset renders stacked traces
- Verify: target zone highlighted in green band
- Switch to "Four-Corner Ride Height Delta" preset
- Switch to "Tire Delta" preset (pressure gain, temp spread, slip ratio)
- Verify: target zone highlight persists across presets

## 14. Save Finding to Notebook
- In the Compare view, click "Save Finding"
- Verify: "Saving…" then "Finding saved to Notebook."
- Verify: button changes to "Save Duplicate" if clicked again (same comparison)
- Click "Save Duplicate" — verify a second finding is created

## 15. Open Notebook
- Navigate to "Notes" in the nav rail
- Verify: "Notebook & Setup Memory" header
- Verify: findings list shows date, car, track, verdict, confidence, headline, status
- Verify: car/track/verdict/status filter inputs work
- Click on a finding row
- Verify: detail view shows verdict, confidence, evidence, takeaways, sector summaries, setup changes

## 16. Edit Notes/Tags/Status
- In detail view, type notes in the textarea
- Type tags: "talladega, platform, 55-70"
- Change status to "Confirmed" via dropdown
- Click "Save Changes"
- Verify: "Changes saved." message
- Verify: status badge updates in findings list

## 17. Copy Markdown
- Click "Copy Markdown"
- Verify: "Markdown copied." message
- Paste into a text editor
- Verify: markdown includes verdict, confidence, target zone, takeaways, evidence, sectors, setup changes, warnings, next step, notes

## 18. Create Test Plan
- Click "Create Test Plan"
- Verify: "Test plan created." message
- Click "Test Plans" nav tab
- Verify: test plan appears in table with car, track, goal

## 19. Setup Memory
- Click "Setup Memory" nav tab
- Enter car and track filters, click Refresh
- Verify: dashboard cards show total findings, keep/undo/retest/inconclusive counts
- Verify: most common issue, best known target zone populated
- Verify: recommended next test from latest needs_retest finding

## 20. Session Persistence
- Close the app
- Relaunch with `.\scripts\start_desktop.ps1`
- Verify: Startup screen shows previous session in the list
- Verify: session name, track, car, and run count are displayed
- Click on the previous session
- Verify: cockpit loads with the last imported run

## 21. Session Management
- Click "New Session" on the startup screen
- Verify: fresh empty cockpit loads
- Go back to startup screen (restart app)
- Verify: both sessions appear in the list
- Click the trash icon on a session
- Verify: "Remove session? Telemetry files stay." confirmation appears
- Click "Remove"
- Verify: session is deleted from the list
- Verify: telemetry data still exists (import another session's run to confirm)

## 22. Notebook Persistence Restart Check
- Navigate to Notebook
- Verify: previously saved finding still appears
- Verify: notes/tags/status changes persisted
- Verify: test plan persisted
- Verify: Setup Memory counts are correct after restart

---

## Smoke Test Result

| Step | Expected | Actual |
|---|---|---|
| Launch | App window, health OK | |
| Import baseline | Run appears | |
| Import test | Two runs available | |
| Laps stint map | Colored blocks render | |
| Performance/Trust/EV badges | Three badges on Best 10/20 cards | |
| All Sessions | Runs listed with basket actions | |
| Test Basket | Drawer appears, readiness shown | |
| Platform preset | 5 rows render | |
| Tires preset | 4 rows render | |
| Compare verdict | Verdict card visible | |
| Four Corners | 5x4 matrix | |
| Delta Traces | Stacked with target zone | |
| Tire Delta | 8 rows with pressure/temp/slip | |
| Save Finding | Saved to Notebook | |
| Notebook detail | Verdict, evidence, takeaways | |
| Edit notes/tags/status | Persisted | |
| Test Plan | Created | |
| Setup Memory | Dashboard populated | |
| Restart persistence | Finding survives | |
