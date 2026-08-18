# RaceLab Garage - MVP Status

Date: 2026-08-18

This status file is a current-state checkpoint, not a historical changelog.

## Verified Current State

- Columnar decoder is the default import mode.
- Vectorized analysis is the default runtime mode.
- Normal import path is frame-native and avoids full row materialization.
- Row analysis path remains available for fallback/debug parity.
- Decoder/engine provenance and any expected row fallback reason are persisted
  in the telemetry manifest and exposed in Learning Mode.
- Current bounded alpha decision scope is NASCAR Next Gen oval telemetry.
  Unsupported car/build/track contexts remain archival and fail closed.
- Draft detection/classification is removed from active runtime and product decisions.
- Notebook is an observation API/archive, not a primary workspace. It stores no
  setup verdict, setup change, next step, test plan, or setup memory.
- Standalone Compare is hidden from main navigation; compare engine internals remain available for embedded tools.
- Laps includes inline Test Basket actions (Set Baseline / Set Test / Open Platform) where evidence is sufficient.
- Proxy/estimate badges are unified through shared badge styling/component usage.
- The shell uses one canonical cached next move; supporting views are explicitly
  navigation-only. Opening a run does not cold-build full intelligence.
- Continuous lap playback, returning-session resume, per-run/lap zoom
  persistence, evidence-debt grouping, and character-shortcut disablement are wired.
- Windows packaging owns one single desktop/backend instance and verifies the
  sidecar through an exact per-process identity.

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

- Exact definitive backend test counts and durations for the final commit.
- Large-fixture import timing baselines (including Charlotte large file run).
- The full cold Engineer construction remains explicit performance debt even
  though run-open shell construction is now compact and non-building.
- P23/P36 field evidence remains unearned until real source-owned sessions pass
  the frozen historical, null, negative-control, and subgroup gates.

## Known Limitations (Still Applicable)

- `.sto` decoding is not implemented.
- Track map support is centerline-focused and partial.
- Aero/downforce/drag values are proxy/relative only.
- No cloud sync (local-first by design).

## Documentation Hygiene Notes

- Historical roadmap/deferred notes should live in future/research docs.
- Contract docs should mark unresolved claims as "needs verification" instead of hard completion language.

Last contract review: 2026-08-18. Exact regression and build counts belong to
the release evidence for the tested tree.
