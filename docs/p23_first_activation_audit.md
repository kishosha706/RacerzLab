# P23 First Earned Adaptive Capability

Status: **NO ACTIVATION EARNED**.

Protected baseline: `abf8925` on `codex/setup-knowledge-foundation`.

P23 audited every P21/P22 candidate before selecting a protocol. The production
archive contains 13 runs across three saved sessions, but it contains zero
qualified evidence datasets, campaign attempts, evaluation artifacts,
prospective test predictions/outcomes, profile validations, or activation
decisions. Archive inventory is not scientific evidence.

## Ranked activation audit

All independent-unit, subgroup, historical, prospective, and negative-control
counts below are qualified real-world counts. They are zero for every candidate.

| Rank | Capability | Current authority | Required frozen gate | Qualified evidence available | Qualified evidence missing | Units | Negative controls | Historical | Prospective | Subgroups | Vehicle/profile prerequisites | Realistic collection cost | Earliest legitimate path |
|---:|---|---|---|---|---|---:|---|---|---|---|---|---|---|
| 1 | Steering workload envelope | P20 observation only; P23 shadow only | P23 `7039505728f0` | None | 9 historical sessions/90 laps; 10 prospective sessions/100 laps; 10 null stints | 0 | Not started; 8 required | Not started | Blocked until historical pass | 0/9 | Exact complete FFB fingerprint; steering conversion | About 19 sessions/190 clean laps | Control-workload + null campaigns, frozen held-out evaluation, then new prospective sessions |
| 2 | Driver-noise envelope | Shadow only | P22 `c53be251052f` | None | Driver-repeatability dataset; 3 sessions/30 laps; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 track types | None beyond exact context | At least 13 sessions/130 laps | Whole-session noise/null evaluation, then prospective validation |
| 3 | Steering/yaw transient calibration | P20 observation only | Not pre-registered | None | External yaw-delay reference; 30 sessions; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | Body axes; steering conversion | 30+ sessions plus external reference | Validate profile/reference semantics before freezing a later protocol |
| 4 | Change-point detection | Shadow only | P22 `8ad0105ba4d3` | None | Long-run + null datasets; 30 uninterrupted stints; 10 null stints; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | None | 30 long runs + 10 null stints | Pass localization and false-change controls in every subgroup, then prospective shadow |
| 5 | Geometry-corrected wheel disagreement | Shadow only | P22 `fb6daf1c38cd` | None | Profile + observer ground truth; 30 labeled events; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | Wheelbase; both track widths; wheel-speed semantics | Source geometry + 30 events + prospective units | Validate exact-build geometry first, then labeled slip/no-slip events |
| 6 | Bank/gravity compensation | Shadow only | P22 `8704953809dc` | None | Observer ground truth; 30 sessions; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | Body axes; gravity convention | 30 sessions plus external reference | Validate axes/convention, then reference-error evaluation |
| 7 | Setup response model | Descriptive/shadow only | P22 `a07d73b6b7b8` | None | Controlled A/B/A2 dataset; 30 workflows; 3 contexts; 6/factor; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | None | 30 restored workflows + prospective units | Pass held-out sign, contradiction, restoration, null, and subgroup gates |
| 8 | Causal control-family calibration | Shadow only | P22 `976f052fd7eb` | None | Controlled + null datasets; 30 workflows; 3 contexts; 6/factor; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | None | 30 restored workflows + nulls + prospective units | Pass placebo, direction, restoration, controls, and subgroups |
| 9 | Conformal uncertainty | Shadow only | P22 `ffcb5518fb5a` | None | Historical dataset; 30 sessions; separate calibration set; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | Separate calibration population | 30+ sessions plus held-out calibration | Earn only after its underlying target is itself validated |
| 10 | Hierarchical transfer | Shadow only | P22 `979a458aba87` | None | Historical dataset; 30 sessions; 3 tracks; 2 drivers; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | No-transfer baseline | 30+ sessions across drivers/tracks | Beat no-transfer without one failed transfer subgroup |
| 11 | Calibrated probabilities | Locked | P22 `2cc00b2bd2b2` | None | Controlled + null datasets; 100 graded predictions; 30 sessions; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | None | 100 graded outcomes | Pass skill, calibration, controls, and every subgroup prospectively |
| 12 | Body sideslip observer | Shadow only | P22 `04a34a38b3be` | None | External ground truth; 30 sessions; 10 prospective units | 0 | Not started | Not started | Not started | 0/3 | Body axes; steering conversion; wheelbase; bank/gravity treatment; frozen error target | 30 sessions plus external reference/profile work | Validate every prerequisite before observer error testing |
| 13 | Formal information gain | Locked; prospective shadow ceiling | P22 `e2fcf470cbeb` | None | Historical archive dataset; 30 prospective missions; deterministic comparator | 0 | Not started | Not started | Not started | 0/3 | Deterministic planner comparator | 30 prospective missions after comparator exists | Prove zero authority violations/false stops and no greater clean-lap cost |
| 14 | Bayesian optimization | Shadow ceiling | P22 `4391c4e23448` | None | 100 workflows; 3 contexts; 6/factor; countereffect/transfer/restoration/safety prerequisites | 0 | Not started | Not started | Not started | 0/3 | Safe/legal domain and validated dependencies | 100+ restored workflows | Remains shadow even if its current gate passes |
| 15 | Multi-control optimization | Shadow ceiling | P22 `8c1f6f09e9cd` | None | 100 workflows; 30 multi-factor experiments; validated single-control response | 0 | Not started | Not started | Not started | 0/3 | Safe/legal domain | 100 workflows + 30 multi-factor experiments | Remains shadow; single-control foundations must pass first |

## Why steering workload won

The winner is `steering_workload_envelope`, based on
`p20.steering_workload.v1`:

- it already has a deterministic, source-owned 360 Hz sub-tick producer;
- the ground claim is narrow: relative steering activity under one exact FFB
  fingerprint, not fatigue, tire force, rack work, or cause attribution;
- FFB mismatch, stable response, line/traffic mismatch, integrity failure,
  build/profile mismatch, and pit-boundary cases are strong negative controls;
- it requires no wheelbase, track width, body-sideslip, or gravity model;
- its maximum useful authority is a limited observation overlay, never setup or
  policy authority.

Driver-noise characterization is cheaper, but its reference semantics are less
direct. Yaw-response calibration is useful, but it depends on unvalidated body
axes/steering conversion and an external timing reference. Every response,
probability, transfer, planner, and optimizer candidate carries more authority
risk and substantially greater collection cost.

## Frozen protocol

- Protocol: `p23p-7039505728f07034d6f5`
- SHA-256: `7039505728f07034d6f58e78c65759e30f3ac7c7b87beb9186b64c0e699bb4dc`
- Formula: `p20.steering_workload.v1`
- Formula source SHA-256:
  `c30de28588830da0d3a080269fa85243960b23a12dfbdaeb61a7a82d0e172ddb`
- Baseline commit: `abf892533de65e850df4a7b17e8e5b51a8976c96`
- Independence unit: one unique source-file session; laps/windows are repeated
  observations inside that unit
- Historical requirement: 9 independent sessions, 90 eligible laps, at least
  3 sessions per short/intermediate/superspeedway track type
- Prospective requirement: 10 new independent sessions and 100 eligible laps,
  strictly after the unchanged protocol has passed historical evaluation
- Null requirement: 10 real same-setup/no-change stints
- Split: whole-session, source-fingerprint deduplicated, chronological historical
  train/evaluation, then a strictly later prospective partition

Primary passing thresholds:

- absolute 90% envelope-coverage gap <= 0.05;
- known workload-increase detection >= 0.80;
- negative-control false-positive rate <= 0.05;
- FFB mismatch block rate = 1.00;
- contamination acceptance rate = 0.00.

Required reporting covers short/intermediate/superspeedway, low/high track
temperature, short/long run, and low/high fuel subgroups. Aggregate success
cannot hide a failed subgroup. Global activation remains locked unless all
required groups pass; any later limited envelope must name only validated
contexts.

The thresholds are content-addressed and immutable. A threshold, model code,
formula, profile, or build change creates a new protocol/version and resets
prospective validation. New-build or context mismatch blocks publication.

## Scientific result

- Datasets used: none; no qualified real dataset exists
- Historical result: **not started (0 / 9 sessions)**
- Prospective result: **not started (0 / 10 sessions)**
- Negative controls: **not started (0 / 8)**
- Required subgroup groups: **not started (0 / 9)**
- Activation decision: **NO ACTIVATION EARNED**
- Authority envelope: none

P19 remains the only cause-ranking, measurement-planning, setup, and Keep/Undo
authority. P20 remains the only whole-car state projection. The selected
descriptor stays shadow-only for P23 evaluation, while its existing P20
single-window values retain their prior observation-only contract.

## Next collection missions

1. Run the P22 control-workload campaign for nine independent exact-FFB Next Gen
   sessions and at least 90 clean laps across all three oval track types.
2. Run ten real same-setup/no-change stints plus stable-response, FFB-mismatch,
   line, traffic, integrity, build/profile, and pit-boundary controls.
3. Validate steering-conversion state and every FFB fingerprint field for the
   exact car/build before session comparison.
4. Only after the unchanged historical gate passes, freeze predictions for ten
   new prospective source sessions before observing their outcomes.

No threshold was lowered, no eligibility rule was loosened, and no advanced
capability was activated.

## Validation and performance

- 26 focused hostile P21/P22/P23 regressions passed.
- The complete Python collection passed: 2,209 collected, 2,203 passed, and six
  protected fixture tests skipped.
- Whole-repository Ruff, TypeScript, the 2,189-module production build, and diff
  integrity passed.
- Live smoke verified that Race Mode remains uncluttered and Learning Mode shows
  the fail-closed P23 result without an activation control or P19/P20 drift.
- Against the real Talladega archive, the audit completed in 15.106 ms cold and
  14.564 ms warm mean. Full Learning Readiness completed in 62.397 ms cold and
  65.162 ms warm mean. These are Learning-only paths, not startup dependencies.
