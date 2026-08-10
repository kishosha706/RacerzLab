# P24 Evidence Acquisition Operations

## Scientific status

P24 adds collection infrastructure only. The frozen P23 candidate remains
`shadow_only`, the protocol and thresholds are unchanged, and no activation is
earned by this implementation.

- Protocol: `p23p-7039505728f07034d6f5`
- Protocol SHA-256:
  `7039505728f07034d6f58e78c65759e30f3ac7c7b87beb9186b64c0e699bb4dc`
- Historical sessions: **0 / 9**
- Same-setup null stints: **0 / 10**
- Frozen negative controls: **0 / 8**
- Required subgroups: **0 / 9**
- Steering/profile validation: **incomplete**
- Prospective sessions: **locked until the historical gate passes**
- P23 activation: **NO ACTIVATION EARNED**

The saved runs remain inventory. They are not silently promoted into P23
evidence.

## Existing systems reused

The P24 audit found that P21-P23 already provide the durable scientific spine:

- P21 owns immutable datasets, session-level independence, split/leakage checks,
  negative-control evaluation, and activation gates.
- P22 owns campaign operations, append-only lifecycle events, import-time coarse
  qualification, prospective prediction freezing, deterministic acquisition
  ranking, and the Learning Ledger.
- P20 owns exact FFB fingerprints, requested-versus-applied control semantics,
  control-boundary detection, and the descriptive steering workload formula.
- P23 owns the selected capability, frozen formula/code identity, fixed metrics,
  fixed thresholds, subgroups, controls, and authority ceiling.

The missing layer was one immutable decision record binding the source file,
steering truth, lap/context timeline, exclusions, independence decision, and
dataset admission. P24 adds that layer without creating another evaluator,
planner, ranker, or authority path.

## Session qualification certificate

`CampaignQualificationCertificate` is content-addressed and append-only. It
binds:

- P22 campaign and operation identity;
- frozen P23 protocol identity and hash;
- source-file SHA-256, run, source session, car, track, build, profile, setup,
  and FFB identity;
- steering configuration and source-validated ratio/pinion representation;
- requested and applied control-state boundaries without conflation;
- eligible and excluded laps with exact reasons;
- steering signal truth audit, channel health, sub-tick coverage, and clock
  integrity;
- one source-file-session independence identity and duplicate-source result;
- negative-control expectation, subgroup memberships, exact qualification
  state, blockers, and authorized dataset admission rules;
- explicit P19/P20 unchanged and P23 `shadow_only` authority.

Qualification states are `qualified`, `rejected`, `partial`, and
`inventory_only`. Rejected or partial evidence is preserved. Only a stored
qualified certificate can authorize dataset construction.

The dataset builder consumes certificate facts directly. It does not reopen the
telemetry and reinterpret eligibility later. The certificate itself is the
registered dataset artifact, and a separate immutable admission record binds
its hash to the resulting dataset hash.

## Campaign flight recorder

Each certificate carries a deterministic per-lap timeline. Every lap is one of:

- `qualified`;
- `excluded` with canonical junk/context reasons;
- `context_boundary` with exact requested or applied mutation identities; or
- `inventory` when outside the qualifying block.

The timeline retains setup and FFB fingerprints, nearby-context state, sample
continuity, sub-tick coverage, and separate requested/applied mutation IDs. It
never bridges a control boundary or turns adjacent laps into independent
sessions.

## Executable collection templates

P24 exposes five protocol-bound templates:

1. Historical exact-FFB source sessions: 9 sessions, at least 10 clean laps per
   source session.
2. Same-setup null stints: 10 source-qualified null stints.
3. Frozen negative controls: expected outcome recorded before the observed run.
4. Steering signal/profile validation: units, signs, sampling, array timing,
   scalar/sub-tick relationship, configuration stability, and steering
   conversion.
5. Prospective source sessions: hard-locked until frozen historical validation
   passes.

The pre-run checklist reports only facts known from the selected reference run.
It never claims live observation. Post-import facts such as clean laps, traffic,
control continuity, and sample integrity remain unknown until the recording is
qualified.

## Steering Signal Truth Audit

The audit explicitly examines:

- `SteeringWheelTorque_ST`
- `SteeringWheelTorque`
- `SteeringWheelAngle`
- `SteeringWheelAngleMax`
- `SteeringWheelMaxForceNm`
- `SteeringWheelUseLinear`
- `SteeringWheelPctIntensity`
- `SteeringWheelPctSmoothing`
- `SteeringWheelPctDamper`
- `SteeringWheelLimiter`

It records manifest unit agreement, signed/unsigned semantics, coverage,
variation, declared count-as-time ordering, base/effective rate, samples per
record, malformed/non-finite evidence, sample-clock health, and the empirically
best mean/first/last relationship between 60 Hz and sub-tick torque.

Admission requires a healthy complete FFB fingerprint, source-validated
steering ratio/pinion representation, at least 95% sub-tick coverage, healthy
sample continuity, declared sub-tick ordering/rate, and a consistent scalar to
sub-tick relationship. Missing or contradictory semantics become explicit
scientific debt and block the affected campaign.

The current Atlanta archive fails closed because its original immutable cache
ownership cannot be proven. The checklist requests re-import and leaves profile
status incomplete; it does not infer the missing steering truth from old
metadata.

## Negative-control operations

Recipes cover unchanged exact-FFB comparison, MaxForce, linear mode, smoothing,
damper, steering conversion, sample clock, sub-tick integrity, and build/profile
mismatch. `NegativeControlExpectation` contains no observed run or result and is
persisted before the outcome. A later immutable result binds the expectation to
the qualification certificate and passes only when the expected outcome and
expected blocker class are both observed.

Progress counts the eight frozen P23 protocol-control identities, not recipe
variants. MaxForce, linear, smoothing, damper, and ratio mismatch recipes all
exercise `ffb_config_changed` and therefore cannot inflate control coverage.

A negative-control rejection may qualify as negative-control evidence while
remaining forbidden from historical positive-evidence admission.

## Duplicate and independence protection

One immutable source-file SHA-256 identifies one P23 source-session unit.
Renaming, copying, re-importing, changing the run ID, or rebuilding a derived
cache cannot increment P23 progress. A duplicate attempt remains visible as a
rejected or partial inventory certificate. Laps and windows stay within the
single session unit.

## Product surface

Learning Mode now shows:

- four accessible progress meters for historical, null, negative-control, and
  subgroup gates;
- qualified-versus-recorded attempt counts and steering truth/profile status;
- the hard prospective lock and typed deterministic next collection class;
- the latest certificate decision and a bounded lap-flight-recorder preview;
- a truthful empty state before the first qualification certificate exists; and
- the certificate-owned, unique-session, shadow-only authority statement.

Race Mode remains unchanged and contains no P24 collection clutter.

Certificate history is bounded to the latest 50 records on the public API. The
Learning Readiness projection carries at most 12 lap decisions plus the full
count and an explicit truncation flag; the immutable certificate endpoint
remains the source for the complete recorder. Dataset admission now retrieves
its exact certificate identity directly rather than scanning campaign history.

The 13 negative-control recipe variants are also exposed as typed,
expectation-only templates. Their catalog makes protocol-control identity,
expected blocker class, and expected outcome inspectable before a campaign
freezes an experiment. The variants still collapse to the same eight frozen
P23 control identities for progress.

## Performance

Measured on the local workstation:

- flight-recorder construction, 10-lap fixture: **0.045 ms mean**;
- qualification-certificate construction, 10-lap fixture: **0.239 ms mean**;
- immutable dataset/campaign admission: **20.198 ms**;
- complete post-import audit/certificate/admission path: **43.639 ms**;
- warm P23 acquisition progress: **3.764 ms mean**, **4.704 ms max**;
- full Learning Readiness on the saved Atlanta run: **87.976 ms cold**,
  **78.453 ms warm mean**, **79.928 ms warm max**.

Qualification is invoked only after import and cannot delay cockpit opening.
No cache keyed by mutable run wording or filenames was introduced.

## Validation

- 91 focused P21-P24 campaign, dataset, leakage, prediction, activation, API,
  and UI regressions passed after the polish pass; 16 directly exercise P24.
- The complete Python collection passed: **2,225 collected, 2,219 passed, and
  six protected fixture tests skipped**.
- Ruff passed for every file changed by P24 polish; TypeScript, the 2,189-module
  production build, and `git diff --check` passed. A repository-wide Ruff audit
  currently reports 1,026 inherited findings outside this slice, so P24 does
  not claim a clean whole-repository lint baseline.
- Live smoke found zero P24 content in Race Mode and exactly one card in
  Learning Mode. The card rendered four accessible meters, actual zero counts,
  the signal-truth requirement, prospective lock, typed next mission, honest
  no-certificate state, and shadow-only authority at the working viewport.

## Authority boundary

P24 may increase qualified evidence counts only through immutable certificates.
It cannot change P19 cause rank, planning, Keep/Undo, or setup authority; P20
awareness authority; the frozen steering workload formula; probability or
optimization authority; or P23 activation state. There is no activation button,
manual override, client-owned admission boolean, or prospective bypass.
