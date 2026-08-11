# Shock Reader

Platform -> Shocks includes a reader for recorded shock-movement signatures and
the current damper settings captured with the run.

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
- The response contains no setup direction, target, delta, click instruction,
  Keep/Undo verdict, or test policy. Exact setup authority remains with P19.
- Current `LS Comp`, `HS Comp`, compression-slope, `LS Reb`, `HS Reb`, and
  rebound-slope values are recorded context only.
- A selected observation zone is limited to 20% of the lap so a broad histogram
  cannot masquerade as a localized finding.
- A qualified repeated shape needs eligible laps, at least 64 continuous samples,
  at least 0.75 seconds per lap, the same shape on two laps, and stability when
  the analytical boundary moves by `+/-25%`.
- The server owns the high/low boundary. Next Gen uses the approximately
  `1.5 in/s` transition documented by iRacing. Cars without a verified
  car-specific transition use a descriptive `1.0 in/s` boundary.
- High activity is not called chatter unless a qualified oscillation analysis
  supports that label.
- The reader treats histogram signatures as guarded observations, not proof that
  a setting is wrong or permission to change it.
- Junk laps remain visible only as blocked context and cannot support causal
  attribution.

## Endpoint

`GET /api/runs/{run_id}/shock-reader`

Query options:

- `lap`
- `lap_window`, formatted like `3-8`
- `phase`
- `zone_start_pct`
- `zone_end_pct`

`boundary_in_s` is response metadata, not a client-controlled decision input.
The response sets `setup_authority` to `withheld` and rejects deprecated action
fields through strict current contracts.

## CLI

```powershell
python -B scripts/query_shock_reader.py --run-id <run_id> --lap-window 5-8 --zone-start-pct 20 --zone-end-pct 30
```

Use `--json` for the stable response shape.

## Technical references

- [iRacing NASCAR Next Gen User Manual](https://s100.iracing.com/wp-content/uploads/2024/03/NASCAR-NextGen-Cars-Manual-V2.pdf)
- [iRacing Shock Tuning User Guide](https://s100.iracing.com/wp-content/uploads/2021/08/Shock-Tuning-User-Guide.pdf)
