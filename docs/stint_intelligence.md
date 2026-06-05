# Stint Intelligence

Stint Intelligence is RacerZLab's imported-data view for comparing sustained pace windows, falloff, consistency, and setup usefulness. Version 1 is intentionally local and offline: it uses laps and windows that are already imported into RacerZLab.

## Scope

- No runtime AI, API keys, or live iRSDK bridge.
- No import pipeline changes.
- No telemetry formula changes beyond derived stint/window metrics.
- No missing values are treated as zero.
- No setup auto-editing.

## Stint Definitions

A stint table row can represent:

- the full imported run when it has at least 5 valid laps and at least 60% of laps are valid

Invalid laps are excluded from calculations when they are incomplete, not useful, out laps, cooldown laps, pit road, wreck/spin laps, invalid speed events, or missing lap time.

The default Laps view is curated on purpose. It shows meaningful stint rows only, so imported-data v1 usually has one full-run row. The best consecutive 5, 10, 20, 30, or 40 lap windows are compact summary cards above the timing sheet instead of repeated table rows. Alternate rolling windows can be exposed separately, but they stay collapsed by default.

Selecting either a full-run row or a best-window card drives the toolbar actions for baseline, test, compare basket, and Platform focus. The timing sheet itself does not include a default Actions column.

## Laps Workspace

Laps renders Stint Intelligence directly. The former Evidence, Windows, Stint Intelligence, All Sessions, Baselines, and Basket sub-tabs are not part of the normal Laps surface.

Useful behavior from those older views now lives inline:

- best-window cards sit above the timing sheet
- baseline/test buttons live on stint cards, the selected-stint toolbar, and loaded history rows
- run history is embedded below the timing sheet and loads older runs lazily
- Test Basket actions are available from stint cards and the selected-stint toolbar

The standalone Compare workspace remains hidden from normal navigation. Baseline/test review for this workflow stays in Laps.

## Stint Summary Drawer

Click or double-click a full-run row, best-window card, history stint, or graphed stint to open the Stint Summary drawer. The drawer shows:

- run/setup, track, car, stint label, and lap range
- valid lap count, best lap, average lap, falloff, consistency, and setup usefulness
- tire, platform, and shock trend labels
- lap-by-lap rows with lap number, stint lap, lap time, delta to best, rolling 5, valid status, invalid reason, speed fields, and fuel when present

Unavailable values are shown as missing. RacerZLab does not fill missing speed, fuel, tire, platform, or shock fields with zero.

## Lap-Time Graph

Laps owns the stint and lap-time workflow. The Stint Intelligence view includes a selected-stint graph panel:

- default graph: current full-run lap-time curve
- selectable graph sources: full-run row, best-window cards, and loaded history stints
- graph modes: lap time, delta to best, or rolling 5-lap average
- invalid laps are excluded by default and remain flagged in the source lap points
- baseline/test selections are graphed together without reopening the standalone Compare workspace

The graph uses lap-summary data only. It does not load full telemetry traces, use runtime AI, or invent missing lap-time points.

The default chart scale is `Race pace`. That scale is based on valid race-pace lap values and ignores invalid, pit, cooldown, out, wreck/spin, and extreme statistical outlier laps for y-axis domain purposes. This prevents one 40-second pit/cooldown lap from flattening a real 15-second Bristol stint into an unreadable line.

Excluded laps are not hidden from the truth model. When invalid/outlier laps are shown, RacerZLab renders them muted or marked at the chart boundary with tooltip text explaining why they were excluded from the pace scale. `Include outliers in scale` expands the y-axis to the full selected data range when the driver wants to inspect the raw spike.

The graph includes hover details for each plotted point, fastest valid lap markers, a selected-lap marker, selected stint/window range shading, and muted invalid points when invalid laps are shown. Brush/zoom selection is intentionally deferred until the chart needs deeper lap-range inspection.

## Run History

The Stint Intelligence view also includes collapsible imported-run history:

- current run is expanded by default
- older runs are collapsed by default
- history headers show setup/run context, track, car, lap count, best lap, and best loaded window averages
- expanding an older run lazily fetches that run's existing `/api/runs/{run_id}/stints` data
- expanded history stints and best-window cards can be graphed or assigned as baseline/test inside Laps

Older run details are loaded on demand so the app does not fetch every stint table or lap series up front.

Compact filters keep the screen manageable:

- current run only
- same car/track only
- graphed only
- hide invalid/caution laps
- collapse all older runs
- expand current run
- pin/unpin the selected run

Filters do not eagerly fetch older run details. Older runs still load lazily when expanded.

## Session Cleanup Boundary

RacerZLab may clean up temporary RaceLab session containers, but only when they are clearly session records. Cleanup must never delete imported runs, raw `.ibt` files, cached telemetry, setup snapshots, generated notebooks, reports, or source guide data.

The current backend model stores RaceLab sessions separately from durable imported runs. `DELETE /api/sessions/{session_id}` removes the session row and does not delete telemetry files or run records. There is not yet a distinct `ephemeral` session flag, so no automatic expiration or bulk cleanup is enabled for this milestone.

## CSV Export

`Export Selected CSV` writes the currently graphed stints, or the selected stint when nothing is graphed, to a browser-generated CSV file. The export contains lap/stint summary rows only:

- run and setup metadata
- stint id and label
- lap number and stint lap
- lap time, delta to best, rolling 5, valid status, and invalid reason
- optional speed and fuel fields when present
- stint-level tire, platform, and shock labels

Raw telemetry traces are not exported from this workflow.

## Rolling Averages

Each stint summary exposes:

- full stint average
- best 5-lap average
- best 10-lap average
- best 20-lap average
- best 30-lap average when enough laps exist
- early, middle, and late averages

Rolling averages are only populated when enough valid laps exist. Missing buckets remain unavailable.

## Bucket Averages

The Stint Intelligence table also exposes fixed 5-lap timing buckets:

- L1-5
- L6-10
- L11-15
- L16-20
- L21-25
- L26-30
- L31-35
- L36-40

Each bucket is the average of valid laps inside that slice of the stint/window. RacerZLab only shows a bucket value when all 5 laps in that bucket are valid. Limited or missing buckets remain unavailable, so there is no fake precision.

The fastest available bucket in each row is highlighted. Later buckets that fall away meaningfully are marked with a restrained warning color.

## Falloff Classifications

The first version labels trend, not root cause. Labels include:

- strong short-run / poor long-run
- stable long-run
- late falloff
- early fade
- inconsistent / noisy
- insufficient laps

Classification uses falloff per lap, early vs late average, lap-time standard deviation, valid lap count, pace quality, and setup usefulness.

## Trend Labels

Compact trend labels are shown only when data exists:

- tire stable, RF tire work rising, tire data limited
- platform stable, front contact rising, platform data limited
- shock activity stable, shock activity rising, shock data limited

If source fields are not populated, RacerZLab reports limited data instead of inventing a value.

## Compare Behavior

The compare panel reports:

- average delta
- best lap delta
- best 5/10/20 average deltas
- L1-5/L6-10/L11-15/L16-20 bucket deltas
- falloff delta
- consistency delta
- tire/platform/shock trend comparison
- a cautious verdict

Positive time deltas mean the test stint is slower than baseline. Negative time deltas mean the test stint is faster.

Compare remains inside Laps for this workflow. The standalone Compare workspace is still hidden from normal navigation.

## Limitations

- Pit detection is not live-aware yet.
- Tire, platform, and shock trends depend on imported lap/window fields being populated.
- Compare currently operates on computed summary rows, not raw time-series overlays.
- Representative lap selection is preserved for downstream tabs, but Compare still primarily consumes run-level context.
- Run history stints are fetched lazily; collapsed older runs may show only run-list metadata until expanded.
- Lap-range brush/zoom is not implemented yet; the current graph focuses on hover, selection, and mode switching.

## Future Work

Later milestones can reconcile imported `.ibt` stints with a live iRSDK bridge, persist stint identities across sessions, deepen raw-channel trend diagnosis, and connect live stint timing to the same table model.
