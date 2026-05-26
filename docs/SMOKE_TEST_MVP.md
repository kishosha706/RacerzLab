# RaceLab Garage — MVP Smoke Test

Run through this workflow to verify the core product loop works end-to-end.

**Prerequisites:** Backend running, one baseline `.ibt` and one test `.ibt` imported.

---

## 1. Launch
```powershell
cd racelab-garage
.\scripts\start_desktop.ps1
```
- App window opens titled "RaceLab Garage"
- Backend health check passes at `http://127.0.0.1:8000/api/health`

## 2. Import Baseline Run
- Click "Import .ibt" or use the file selector
- Select a baseline `.ibt` file
- Verify: run appears in run list dropdown
- Verify: overview shows track, car, lap count

## 3. Import Test Run
- Import a second `.ibt` (the test/experimental run)
- Verify: two runs now appear in run selector
- Verify: both runs show car/track info

## 4. Select Useful Laps
- Verify: best useful lap is auto-selected for both runs
- Verify: run context bar shows track, car, lap

## 5. Platform Workbench — Platform/Rake Preset
- Navigate to "Platform" in the nav rail
- Select "Platform" preset from the chart dropdown
- Verify: 5 stacked chart rows render (Throttle/Brake, Center Rake, Side Rake, CFS+LF+RF, LR+RR)
- Verify: CFS threshold bands visible (scrape/critical/high/watch)
- Verify: tooltip shows distance, per-channel values, "(proxy)" for proxy channels

## 6. Platform Workbench — Tires Preset
- Select "Tires" preset from the dropdown
- Verify: Tire Pressure, Pressure Gain, Temp Spread, Slip Ratio Proxy rows
- Verify: each row has LF/RF/LR/RR series with corner colors
- Verify: proxy channels (slip ratio) show dashed lines

## 7. Compare
- Navigate to "Compare" in the nav rail
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

## 20. Persistence Restart Check
- Close the app
- Relaunch with `.\scripts\start_desktop.ps1`
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
