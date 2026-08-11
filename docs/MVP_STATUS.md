# RaceLab Garage - MVP Status

Date: 2026-08-10

This status file is a current-state checkpoint, not a historical changelog.

## Verified Current State

- Columnar decoder is the default import mode.
- Vectorized analysis is the default runtime mode.
- Normal import path is frame-native and avoids full row materialization.
- Row analysis path remains available for fallback/debug parity.
- Draft detection/classification is removed from active runtime and product decisions.
- Notebook is an observation API/archive, not a primary workspace. It stores no
  setup verdict, setup change, next step, test plan, or setup memory.
- Standalone Compare is hidden from main navigation; compare engine internals remain available for embedded tools.
- Laps includes inline Test Basket actions (Set Baseline / Set Test / Open Platform) where evidence is sufficient.
- Proxy/estimate badges are unified through shared badge styling/component usage.

## Truth Rules (Must Stay Visible)

- No fake values.
- No missing telemetry converted to zero.
- No fake setup diffs.
- Measured/derived/proxy labeling remains explicit and truthful.
- P19 is the sole setup-direction, exact-target, Keep/Undo, and stop-testing
  authority. Overview, Compare, Platform, Shock Reader, public Dial-In, and
  Notebook remain observation/measurement-only.

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

Last contract review: 2026-08-10. Exact regression and build counts belong to
the release evidence for the tested tree.
