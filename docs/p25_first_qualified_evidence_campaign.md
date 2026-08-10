# P25 First Qualified Evidence Campaign

## Scientific result

**NO QUALIFIED SESSION EARNED — EXACT TRAFFIC DEBT IDENTIFIED.**

P25 exercised the real field-acquisition path without changing the frozen P23
protocol, thresholds, activation state, or P19/P20 authority. The selected owned
Next Gen recording proved source ownership and complete steering truth, but it
did not contain ten clean traffic-free laps. RacerZLab rejected it and admitted
no dataset.

- Protocol: `p23p-7039505728f07034d6f5`
- Protocol SHA-256:
  `7039505728f07034d6f58e78c65759e30f3ac7c7b87beb9186b64c0e699bb4dc`
- Activation: **NO ACTIVATION EARNED**
- Authority: `shadow_only`

## Real source and ownership

The current application API imported and then re-imported:

`stockcars chevycamarozl12022_atlanta 2022 oval 2026-07-08 19-39-01.ibt`

The prior protected Atlanta fixture and its legacy inventory record were not
promoted or rewritten.

| Identity | Verified value |
|---|---|
| Source SHA-256 | `37e380ebc4e70ca33190a0bace40c9a88508744fec4115177559083a7aeb50a7` |
| Source byte size | `68,957,139` |
| Run | `stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb` |
| Cache SHA-256 | `172f5dd83cc79d23179608e9779b7dc6a261d01470f58c4f4be55e0581da4c1c` |
| Schema fingerprint | `08261562f78d3b15b2c0bc5f1249a72b3dd2ae51664021edd94bc8010cd76ede` |
| Setup identity | `3b25b1051194598069c6318776da190a989c01f69f71c7382dc8bc14bbfc8bde` |
| Vehicle/profile identity | `8bef40591876f8e5a8dd00348d0da1643e545757b4df97e5ea019cb8ba870958` |
| iRacing build | `2026.06.24.02` |
| Track identity | `447` |

The P25 certificate now carries a typed `TelemetryOwnershipTruth`. Missing or
mismatched run, source hash, byte size, cache hash, or schema fingerprint is an
exact blocker. A rejected or admission-empty stored certificate is explicitly
refused by the dataset admission entry point.

## Ten-signal steering truth

Every frozen signal was present at full coverage and ready:

| Raw signal | Unit/type | Structure | Update behavior | Canonical role |
|---|---|---|---|---|
| `SteeringWheelTorque_ST` | N·m / float | six-value count-as-time array | continuous, varying | sub-tick torque measurement |
| `SteeringWheelTorque` | N·m / float | scalar | continuous, varying | normal-rate torque measurement |
| `SteeringWheelAngle` | rad / float | scalar | continuous, varying | steering-angle measurement |
| `SteeringWheelAngleMax` | rad / float | scalar | fixed, constant | steering-angle limit |
| `SteeringWheelMaxForceNm` | N·m / float | scalar | stable, constant | FFB configuration |
| `SteeringWheelUseLinear` | unitless / bool | scalar | stable, constant | FFB configuration |
| `SteeringWheelPctIntensity` | % / float | scalar | stable, constant | FFB configuration |
| `SteeringWheelPctSmoothing` | % / float | scalar | stable, constant | FFB configuration |
| `SteeringWheelPctDamper` | % / float | scalar | stable, constant | FFB configuration |
| `SteeringWheelLimiter` | % / float | scalar | stable, constant | FFB configuration |

All ten reported healthy channel state, no detected clipping or saturation, and
no scientific debt. Unitless declared booleans are accepted by declared type;
they are not mislabeled as unit failures.

## Sub-tick reconstruction

The result does not infer 360 Hz merely from an array length of six.

- `SessionTick` is present and declared as the record clock.
- Invalid ticks: 0.
- Duplicate transitions: 0.
- Reversed transitions: 0.
- Estimated dropped ticks: 0.
- `SteeringWheelTorque_ST` samples per record: 6.
- Base record rate: 60 Hz.
- Effective sub-tick rate: 360 Hz.
- Malformed arrays: 0; non-finite samples: 0.
- Sub-tick coverage: 1.0.
- Scalar relation: `last_consistent`; normalized error: 0.0.

The recording contains non-monotonic/gapped `SessionTime` observations, which
remain recorded facts. They do not invalidate the reconstruction because the
independent `SessionTick` sequence is complete and ordered.

## Exact FFB certificate

The immutable material fingerprint is:

`7d5868401be0d368ffdeef7651a9b1b0f4a037f2e255d123fdffaf6d06a1e207`

It binds MaxForce `97.14286041259766 N·m`, linear mode enabled, intensity `0.5`,
smoothing `0.0`, damper `0.0`, limiter `0.0`, and the exact Next Gen steering
conversion representation `73 mm/rev`. `SteeringWheelFFBEnabled` is not part of
the frozen ten-signal P23 material identity and is not fabricated when absent.

## Qualification and flight recorder

Certificate `p24c-36d0f278b166d6f8bb36` is content-addressed as
`36d0f278b166d6f8bb3656817b297fb19d6d9abe3d87531cf967a21bf326960e`.

- Qualification: `rejected`.
- Eligible admitted block: 0 laps; required: 10.
- Recorder: 33 exact lap entries.
- States: 32 excluded, 1 requested-state context boundary.
- Twenty-nine otherwise useful laps: nearby-car context contaminated or unknown.
- One incident lap, two incomplete/partial endpoints, and one requested pit-state
  boundary remain visible with their exact reasons.
- Dataset admissions: none.

Requested pit state remains distinct from an applied setup/control mutation.
Rejected laps and boundaries are never bridged into one clean block.

## Duplicate and re-import hostility

Source SHA-256 owns the statistical identity across path, filename, run/cache
reconstruction, and process restart. Campaign progress now selects one attempt
and at most one admitted collection kind per source SHA-256. Re-importing the
pilot after freezing the null card cannot reuse the reference source as the
future null observation.

An early duplicate probe exposed that reference-source reassessment could create
a second rejected audit certificate for the new null operation. The fix skips
that non-observation before certificate construction and the hostile regression
locks the behavior. The append-only rejected audit artifact remains in the local
history, but progress projects one source attempt and zero admitted evidence.

## Frozen null-session run card

Run card `p25n-4cb35044c911b200f334`, SHA-256
`4cb35044c911b200f334afa8f7d229f7bdd5991f641a5ece8bd86c949c628468`,
is frozen before any outcome.

**P23 STEERING WORKLOAD — NULL SESSION 01**

- Need: one warmup lap, then 10 uninterrupted eligible clean laps.
- Hold: exact car/build/profile, track, setup, FFB fingerprint, `73 mm/rev`
  steering conversion, tire compound `0`, and fuel band `40.7359–74.5360`.
- Avoid: applied brake-bias changes, pit/setup changes inside the clean block,
  reset fragments, FFB changes, traffic/context contamination, and telemetry
  faults.
- Target: no intentional steering-workload or handling intervention.
- Outcome: RacerZLab qualifies or rejects only after the new real file imports.

The card contains all ten telemetry requirements and the unchanged frozen P23
context requirements. Its observed run and observed qualification fields are
structurally `None`; it cannot be backfilled with an outcome.

## Counts and authority

- Historical exact-FFB sessions: **0 / 9**.
- Same-setup null stints: **0 / 10**.
- Negative controls: **0 / 8**.
- Covered subgroups: **0 / 9**.
- Steering/profile truth: **complete**.
- Prospective: **locked until historical validation passes**.
- P23 activation: **NO ACTIVATION EARNED**.
- P19/P20 authority: unchanged.

## Performance

Measured on the 63,657-record real pilot; all P25 work remains import-time or a
Learning/background projection:

| Work | Mean | Worst measured |
|---|---:|---:|
| First API import | 14,777 ms | 14,777 ms |
| API re-import plus qualification | 25,047 ms | 25,047 ms |
| Exact FFB fingerprint | 453.174 ms | 582.637 ms |
| Complete ten-signal truth audit | 547.836 ms | 559.986 ms |
| Flight recorder | 0.525 ms | 0.777 ms |
| Qualification certificate | 1.657 ms | 1.986 ms |
| Rejected-certificate admission guard | 2.601 ms | 3.866 ms |
| P23 campaign projection | 15.669 ms | 18.873 ms |
| Whole Learning Readiness projection after frozen-context reuse | 121.425 ms | 128.616 ms |

The whole Learning Readiness projection originally repeated a 63,657-row context
rebuild and measured 6,195.704 ms mean. It now reuses the immutable context
already frozen in the campaign operation. The projection is still fetched only
in Learning Mode; P25 adds no startup import or Race Mode work.

## Protected skips

No statistical model, optimizer, information-gain planner, setup authority,
cause ranker, P19/P20 authority path, P23 threshold, protocol field, or activation
route was added. Race Mode remains uncluttered. The legacy protected Atlanta
inventory was not retroactively relabeled as trusted evidence.

## Validation

- P21–P25 hostile suite: **94 passed**.
- Complete Python collection: **2,228 collected; 2,223 passed; five protected
  fixture skips**.
- Changed-file Ruff: passed.
- TypeScript: passed.
- Production UI build: passed; 2,189 modules transformed.
- Final duplicate API probe: certificate rows `2 → 2`, projected source attempts
  `1`, qualified attempts `0`, and historical/null counts `0 / 0`.
- Live Learning smoke: one P23/P25 card, verified ownership, ready signal/FFB
  truth, exact `0 / 10` blocker, no admissions, 12-of-33 recorder preview, all
  zero campaign counts, frozen null card, and no activation.
- Live Race smoke: zero P23/P25 acquisition cards.
- Synthetic tests are regressions only; only the named real re-import appears in
  this field result, and it was rejected rather than counted.
