# Stint Intelligence

Stint Intelligence is RacerZLab's imported-data view for comparing sustained pace windows, falloff, consistency, and setup usefulness. Version 1 is intentionally local and offline: it uses laps and windows that are already imported into RacerZLab.

## Scope

- No runtime AI, API keys, or live iRSDK bridge.
- No import pipeline changes.
- No telemetry formula changes beyond derived stint/window metrics.
- No missing values are treated as zero.
- No setup auto-editing.

## Stint Definitions

A stint row can represent:

- the full imported run when it has at least 5 valid laps and at least 60% of laps are valid
- best consecutive 5, 10, 20, 30, or 40 lap windows from the existing lap-window analysis

Invalid laps are excluded from calculations when they are incomplete, not useful, out laps, cooldown laps, pit road, wreck/spin laps, invalid speed events, or missing lap time.

## Rolling Averages

Each stint summary exposes:

- full stint average
- best 5-lap average
- best 10-lap average
- best 20-lap average
- best 30-lap average when enough laps exist
- early, middle, and late averages

Rolling averages are only populated when enough valid laps exist. Missing buckets remain unavailable.

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
- falloff delta
- consistency delta
- tire/platform/shock trend comparison
- a cautious verdict

Positive time deltas mean the test stint is slower than baseline. Negative time deltas mean the test stint is faster.

## Limitations

- Pit detection is not live-aware yet.
- Tire, platform, and shock trends depend on imported lap/window fields being populated.
- Compare currently operates on computed summary rows, not raw time-series overlays.
- Representative lap selection is preserved for downstream tabs, but Compare still primarily consumes run-level context.

## Future Work

Later milestones can reconcile imported `.ibt` stints with a live iRSDK bridge, persist stint identities across sessions, deepen raw-channel trend diagnosis, and connect live stint timing to the same table model.
