# Shock Reader

Platform -> Shocks includes a reader for live shock movement signatures and an inline damper worksheet.

The reader uses normalized shock velocity channels from the parquet cache and computes per-corner histogram zones:

- Rebound High: velocity at or beyond the negative high-speed boundary
- Rebound Low: negative velocity between the center deadband and the high-speed boundary
- Bump Low: positive velocity between the center deadband and the high-speed boundary
- Bump High: velocity at or beyond the positive high-speed boundary

The four moving zones use moving samples as their denominator. Samples within
`+/-0.05 in/s` are reported separately as center/deadband occupancy, so zero
velocity is never mislabeled as compression.

Compression/bump is shock shortening. Rebound is shock extending. Low-speed motion is driver input, body, and platform movement. High-speed motion is bumps, curbs, and sharp impacts.

## Guardrails

- No runtime AI, API keys, setup auto-editing, or Notebook memory.
- The reader does not change telemetry formulas or import behavior.
- Missing telemetry stays unavailable and is never treated as zero.
- Normal UI hides raw evidence internals.
- Recommendations are shown inline beside `LS Comp`, `HS Comp`, `Comp Slope`,
  `LS Reb`, `HS Reb`, and `Rebound Slope`.
- Top-level recommendations remain in the API for compatibility, but the normal UI uses the per-corner setup rows.
- Only one per-corner row may remain actionable in a test stage. Every competing
  row is explicitly held until the primary A/B/A2 test is complete.
- Every authorized shock test uses one adjacent option. The reader never invents
  a universal numeric range or target value for any car.
- A slope action is always one adjacent option, described as more linear or more
  digressive. The garage supplies the legal next option for the current car.
- If a setup value is missing, the row may still show semantic direction, but it does not show a current-to-target value.
- Slope recommendations require all of the following: a physical zone no wider
  than 20% of the lap, at least two eligible laps, at least 64 continuous samples
  and 0.75 seconds per lap, the same directional signature on both laps,
  repeated platform contact or packing in that zone, and a conclusion that stays
  stable when the analytical boundary moves by `+/-25%`.
- The server owns the high/low boundary. Next Gen uses the approximately
  `1.5 in/s` transition documented by iRacing. Cars without a verified
  car-specific transition remain descriptive and withhold slope actions.
- High activity is not called chatter unless a qualified oscillation analysis
  supports that label.
- The reader treats histogram signatures as guarded evidence, not proof that a setting is wrong.
- Pick one change and run clean laps before comparing the same window again.

## Endpoint

`GET /api/runs/{run_id}/shock-reader`

Query options:

- `lap`
- `lap_window`, formatted like `3-8`
- `phase`
- `zone_start_pct`
- `zone_end_pct`
- `include_debug`, default `false`

`boundary_in_s` is response metadata, not a client-controlled decision input.

## CLI

```powershell
python -B scripts/query_shock_reader.py --run-id <run_id> --lap-window 5-8 --zone-start-pct 20 --zone-end-pct 30
```

Use `--json` for the stable response shape.

## Technical references

- [iRacing NASCAR Next Gen User Manual](https://s100.iracing.com/wp-content/uploads/2024/03/NASCAR-NextGen-Cars-Manual-V2.pdf)
- [iRacing Shock Tuning User Guide](https://s100.iracing.com/wp-content/uploads/2021/08/Shock-Tuning-User-Guide.pdf)
