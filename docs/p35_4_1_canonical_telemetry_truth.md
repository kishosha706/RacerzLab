# P35.4.1 Canonical Telemetry Truth Closure

P35.4.1 freezes the truth hierarchy beneath every vehicle diagnosis:

`source -> clock -> physical position -> context -> driver demand -> vehicle response -> measured time -> mechanism -> component -> setup family -> P19 test`

No downstream layer may repair, reinterpret, or infer around a failed upstream
identity. P19 remains the sole setup and Keep/Undo/Retest authority.

## Physical alignment

- Lap percentage/distance is the immutable base grid.
- Qualified GPS geometry or repeatable road-profile landmarks may corroborate a
  bounded physical correction.
- Brake, throttle, steering, yaw, ride height, and vehicle response cannot move
  physical position.
- Driver-event correspondence records its own position delta separately. A
  later brake release is evidence, not an alignment error to erase.

## Recording identity and independence

- One full source-file SHA-256 is one physical recording.
- New run/cache ownership uses `recording-<full sha256>`.
- Multipart upload storage is content-addressed and re-hashed before reuse.
- Legacy aliases remain readable for history, while session membership converges
  on one owner.
- Compare, A/B/A2, setup-response memory, P33, and P34 reason in source hashes,
  not filenames or run aliases.
- Missing or malformed recording identity fails closed. Legacy rows remain
  auditable, but cannot enter or re-enter recurrence, response summaries,
  fitted models, or setup-memory projection without a verified full SHA-256.

## Qualified clock

- A contiguous integer `SessionTick` plus the file-declared base rate owns
  canonical elapsed time.
- Raw `SessionTime`, duplicates, reversals, phase steps, residuals, and reset
  epochs remain preserved as corroboration.
- Simulator lap-time and delta-validity channels can corroborate the qualified
  clock but cannot replace it or create P32 time.
- A `SessionTime`-only clock may remain visible as degraded archive diagnostics,
  but it cannot make a lap eligible or make Overview/Engineer decision-ready.
- Genuine tick discontinuity, incomplete canonical coverage, sustained material
  clock disagreement, or material simulator-lap disagreement blocks timing.
- Count-as-time arrays retain their own effective sample rate and are not
  flattened into base records.

## Geometry provenance

- Missing wheelbase, track width, or rub-block geometry makes diffuser-dependent
  quantities unavailable.
- A future calculation requires one reviewed vehicle-profile source marker and
  content SHA plus every required constant.
- Even profile-backed output remains a calculated clearance-geometry proxy, not
  measured volume, downforce, load, or drag.
- Manifest schema v6 requires re-import because persisted nominal values cannot
  be relabeled safely.

## Typed engineering blockers

- Prose explains a limitation; typed fields decide its scope.
- Every blocker identifies `code`, `severity`, `scope`, blocked authority axes,
  evidence state, exact source artifacts/channels, physical scope, and recovery.
- Traffic exposure in a resistance window blocks mechanism/component/setup
  attribution for that scope. It does not block measured pace, platform, stint,
  map, or navigation evidence.
- Malformed or legacy untyped persistence blocks the run until re-import.

## Channel admission

Every audited raw channel receives one role:

- `admitted_analysis`
- `measurement_candidate`
- `corroboration`
- `pit_snapshot`
- `control_state`
- `integrity`
- `inventory_debug`

Per-corner tire-used/available counters are pit-boundary snapshots only.
Simulator lap clocks are corroboration only. Unknown future channels are archived
as inventory/debug until reviewed; file presence never creates runtime authority.

Learning Mode exposes this inventory as **Telemetry Capabilities**. A custom
channel may open one observation-only Platform lane. It cannot create a
mechanism, component, or setup decision.

## Continuous response producers

The first response layer remains observation-only and cannot authorize a cause,
component, setup family, or P19 action:

- Brake application records four-corner line-pressure, deceleration, and yaw
  onset/lag, gains, overshoot, settling, corrections, speed, phase, and exact
  physical scope.
- Brake release records four-corner pressure decay and yaw response separately
  from physical alignment.
- Throttle application records acceleration and yaw response on the qualified
  tick clock.
- Surface-disturbance episodes rebuild their clock from the exact ordered rows,
  retain original-file SHA and a separate telemetry-projection content SHA,
  and require repeated physical-lap position agreement before aggregation.
- Stint migration uses a fixed physical-position grid, splits at every junk,
  setup, pit, reset, recording, or clock boundary, withholds trends below ten
  uninterrupted laps, and admits tire inventory/state only as pit snapshots.

Repeated response evidence counts distinct verified laps, never raw rows,
renamed recordings, duplicate projections, or unrelated same-phase locations.
