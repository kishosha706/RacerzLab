# Shock Reader

Platform -> Shocks includes a reader for live shock movement signatures and an inline damper worksheet.

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
- Recommendations are shown inline beside each corner setup value: `LS Comp`, `HS Comp`, `HS-S Comp`, `LS Reb`, `HS Reb`, and `HS-S Reb`.
- Top-level recommendations remain in the API for compatibility, but the normal UI uses the per-corner setup rows.
- Numeric click guidance is scaled from signal severity: weak `+/-1`, medium `+/-2`, strong `+/-3`, and extreme `+/-4` or `+/-5` only with strong cross-check context and room.
- Click guidance is bounded to `1-10`. If a target hits the range, the shown delta is clamped; if the requested direction cannot move, the row is blocked at the limit.
- If a setup value is missing, the row may still show semantic direction, but it does not show a current-to-target value.
- Slope recommendations require a high-speed pattern plus selected-zone and platform/contact/chatter context.
- The reader treats histogram signatures as guarded evidence, not proof that a setting is wrong.
- Pick one change and run clean laps before comparing the same window again.

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
