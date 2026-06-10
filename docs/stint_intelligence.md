# Stint Intelligence

Stint Intelligence is RacerZLab's local, imported-data timing workstation inside Laps. It compares user stints, sustained average windows, falloff, consistency, and setup usefulness from data already imported into RacerZLab.

Version 1 remains offline:

- no runtime AI
- no API keys
- no live iRSDK dependency
- no telemetry formula changes beyond derived lap/stint display metrics
- no fake values or missing-to-zero fill

## My Stints Timing Sheet

Laps opens Stint Intelligence as **My Stints**. The subtitle is:

> Lap averages, falloff, and long-run pace from your imported runs.

Rows represent meaningful user stints. In imported-data v1, the current run/full-run row is acceptable as the primary stint because true pit-to-pit stint detection is a later milestone.

The default page is a single **My Stints** timing sheet. Best rolling averages stay in the main table so the page reads like a Stint Analyzer-style worksheet instead of two separate summaries.

Best-window cards are retained only as an advanced **Best Windows** section, collapsed by default.

The timing sheet columns are:

- Stint
- # Laps
- Last Lap
- Current Avg Lap
- Fastest Lap
- 3-Lap Avg
- 5-Lap Avg
- 7-Lap Avg
- 10-Lap Avg
- 15-Lap Avg
- 20-Lap Avg
- 25-Lap Avg
- 30-Lap Avg
- 40-Lap Avg
- 50-Lap Avg
- 60-Lap Avg
- Falloff
- Consistency
- Setup EV

Each average column is the best rolling average of that same length inside the stint/run. If a stint does not have enough valid laps for a window size, that cell stays unavailable instead of being faked or backfilled.

The sheet scrolls horizontally when needed. Key row identity columns remain sticky where practical so wide average columns do not collapse into a vertical layout.

## Average Windows

Stint Intelligence supports these best average sizes everywhere the stint contract exposes average windows:

`3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60`

A window average is available only when enough valid laps exist for that same window size. Out-laps, cooldowns, wrecks/spins, pit-road laps, invalid-speed laps, incomplete laps, non-useful laps, and missing/invalid lap times are excluded. RacerZLab does not bridge an average through an invalid lap and does not fill missing values with zero.

For short runs:

- fewer than 3 valid laps: no short-run average
- fewer than 10 valid laps: long-run read is limited
- fewer than 50 or 60 valid laps: 50/60-lap averages remain unavailable

## Best Highlights

The backend marks highlight metadata and the UI highlights the fastest eligible cells with restrained timing-sheet styling.

Highlighted categories:

- fastest lap
- best 3/5/7/10/15/20/25/30/40/50/60 average
- best long-run row
- highest Setup EV

Only eligible same-size values are compared. A 5-lap run cannot win a 20-lap average column, and unavailable values stay muted.

## Session Runs

Stint Intelligence shows only the current session's runs by default. The current imported run is visible and expanded by default. Other runs from the open session stay collapsed by default and load their stint data only when expanded.

If the user opens an older saved session from startup, Laps shows the runs that belong to that loaded session. Historical imported runs from other sessions stay hidden unless that session is explicitly loaded. Imported telemetry is retained on disk and in storage; this view only changes which runs are shown by default.

Collapsed session-run headers show available run context:

- setup/run short name
- track
- car
- date
- valid lap context when loaded
- best lap
- best 5, best 10, and best 20 when stint data is loaded

Expanded session runs can contribute stint rows/cards for graphing, baseline/test selection, the summary drawer, and the Test Basket. RacerZLab does not fetch every older stint table eagerly.

## Best-Window Cards

Best-window cards use the expanded average set:

`Best 3, Best 5, Best 7, Best 10, Best 15, Best 20, Best 25, Best 30, Best 40, Best 50, Best 60`

Unavailable card sizes are omitted rather than faked. The card strip is compact and horizontally scrollable. Cards can be selected for:

- graphing
- baseline
- test
- Test Basket
- summary drawer

The cards answer "What were my best 3/5/7/10/... lap windows?" but they are hidden behind the collapsed **Best Windows** section by default so the main page stays focused on the timing sheet.

## Progression Buckets

Progression buckets remain available for detail views and the Stint Summary drawer:

`L1-5, L6-10, L11-15, L16-20, L21-25, L26-30, L31-35, L36-40, L41-45, L46-50, L51-55, L56-60`

Each bucket is the average lap time for that exact segment of the run. If a bucket does not have enough valid laps, it stays unavailable instead of being faked or backfilled.

These buckets are no longer part of the default timing sheet.

## Chart And Selection

The timing sheet and advanced best-window section drive the chart. Selecting a row or card updates:

- selected row/card highlight
- graph source
- summary drawer target
- selected-stint toolbar actions

Graph Selected supports multiple selected stints as separate lines. Baseline/test selections can graph together inside Laps without restoring the standalone Compare workspace. Race-pace scaling keeps invalid/outlier handling from the current graph implementation.

## Field Compare

Field Compare is a separate collapsible section below My Stints. It is not mixed into the user stint sheet.

Title:

> Field Compare

Subtitle:

> Compare other drivers' best stint averages against your best equivalent stint.

Imported-data v1 usually has no other-driver stint source. The empty state is:

> Other-driver stint data is not available yet.

> Live iRSDK / imported shared stint data will unlock field comparison later.

Future Field Compare rows will use:

- Driver
- Stint
- # Laps
- Fastest Lap
- 3-Lap Avg
- 5-Lap Avg
- 7-Lap Avg
- 10-Lap Avg
- 15-Lap Avg
- 20-Lap Avg
- 25-Lap Avg
- 30-Lap Avg
- 40-Lap Avg
- 50-Lap Avg
- 60-Lap Avg
- Delta to My Best Equivalent
- Notes

Comparison discipline is same-length only: 10-lap vs 10-lap, 20-lap vs 20-lap, and never a 5-lap hot run against a 40-lap long run.

## Compare Behavior

Stint compare remains inside Laps. The standalone Compare workspace remains hidden from normal navigation.

The compare response keeps legacy overall deltas for the existing baseline/test panel, but also exposes same-length average metadata. When two selected stints have different lap counts, same-length overall average delta is unavailable and a warning explains the mismatch. Rolling deltas by size are keyed by the same expanded average sizes.

Positive time deltas mean the test stint is slower than baseline. Negative time deltas mean the test stint is faster.

## Limits And Future Work

Imported-data v1 can identify run-to-run and window-to-window pace differences, but it cannot infer live field position or shared-driver stint timing without a future data source. Future milestones can add live iRSDK/shared import support, persistent stint identities, deeper pit-to-pit detection, and richer same-position comparisons.

RaceLab setup guidance remains evidence-first: setup values must link back to telemetry events, short runs cannot support strong degradation conclusions, and aero/load values should be treated as proxies unless directly supported by measured channels and complete vehicle constants.
