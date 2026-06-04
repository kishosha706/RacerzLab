# Shock Reader

Milestone 1 adds a Platform -> Shocks-only reader for live shock movement signatures.

The reader uses normalized shock velocity channels from the parquet cache and computes per-corner histogram zones:

- Rebound High: velocity below `-boundary_in_s`
- Rebound Low: velocity from `-boundary_in_s` to below `0`
- Bump Low: velocity from `0` through `boundary_in_s`
- Bump High: velocity above `boundary_in_s`

Compression/bump is shock shortening. Rebound is shock extending. Low-speed motion is driver input, body, and platform movement. High-speed motion is bumps, curbs, and sharp impacts.

## Guardrails

- No runtime AI, API keys, setup auto-editing, or Notebook memory.
- The reader does not change telemetry formulas or import behavior.
- Missing telemetry stays unavailable and is never treated as zero.
- Normal UI hides raw evidence internals.
- Recommendations are one shock/slope swing at a time.
- Numeric click guidance is limited to `+1` or `-1`, and only when the setup snapshot has a current value inside `1-10`.
- Slope recommendations require a high-speed pattern plus selected-zone and platform/contact/chatter context.
- The reader never says a histogram proves a setting is wrong.

## Endpoint

`GET /api/runs/{run_id}/shock-reader`

Query options:

- `lap`
- `lap_window`, formatted like `3-8`
- `phase`
- `boundary_in_s`, default `1.0`
- `include_debug`, default `false`

## CLI

```powershell
python -B scripts/query_shock_reader.py --run-id <run_id> --lap 5 --phase transition
```

Use `--json` for the stable response shape.
