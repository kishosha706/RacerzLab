# RaceLab Garage - MVP Status

Date: 2026-06-01

This status file is a current-state checkpoint, not a historical changelog.

## Verified Current State

- Columnar decoder is the default import mode.
- Vectorized analysis is the default runtime mode.
- Normal import path is frame-native and avoids full row materialization.
- Row analysis path remains available for fallback/debug parity.
- Draft detection/classification is removed from active runtime and product decisions.
- Notebook revisit actions use internal SPA workspace navigation (no internal `window.open(...)`).
- Compare subviews are grouped navigation (Verdict / Platform / Systems / Detail).
- Laps includes inline Compare Basket actions (Set Baseline / Set Test / Open Platform) where evidence is sufficient.
- Proxy/estimate badges are unified through shared badge styling/component usage.

## Truth Rules (Must Stay Visible)

- No fake values.
- No missing telemetry converted to zero.
- No fake setup diffs.
- Measured/derived/proxy labeling remains explicit and truthful.

## Needs Verification

The following require fresh code/test profiling verification before being called fully complete in docs:

- Exact backend test counts and durations.
- Exact frontend build module count/time snapshots.
- Large-fixture import timing baselines (including Charlotte large file run).
- Remaining UX audit P0/P1 checklist completion percentages.

## Known Limitations (Still Applicable)

- `.sto` decoding is not implemented.
- Track map support is centerline-focused and partial.
- Aero/downforce/drag values are proxy/relative only.
- No cloud sync (local-first by design).

## Documentation Hygiene Notes

- Historical roadmap/deferred notes should live in future/research docs.
- Contract docs should mark unresolved claims as "needs verification" instead of hard completion language.

Last verified: 2026-06-01.
