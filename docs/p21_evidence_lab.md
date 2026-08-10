# P21 Evidence Lab, Calibration, and Shadow Intelligence

Status: **verified scientific infrastructure; advanced statistical authority remains locked**.

P21 creates the machinery needed to decide whether a future statistical method
has earned authority. It does not replace P19 reasoning, P20 whole-car awareness,
or the deterministic setup-policy path. No P21 model can rank a production cause,
authorize a setup change, change Keep/Undo, stop a P19 mission, or publish a
probability to the driver.

## Authority boundary

- P19 remains the sole production reasoning, measurement-planning, and
  mechanism/control/policy authority.
- P20 remains the sole production whole-car state projection.
- P21 datasets, evaluations, campaigns, predictions, outcomes, and activation
  decisions are immutable or append-only scientific records.
- Candidate methods run offline or prospectively in shadow. Their output is
  structurally rejected if it contains production-authority fields.
- Formal information gain, calibrated probability, body-sideslip estimation,
  gravity compensation, geometry-corrected wheel observation, response-model
  authority, Bayesian optimization, and multi-control optimization remain locked.

## Existing evidence audit

The read-only production archive contained 13 runs across three saved sessions,
626 laps, 602 complete laps, and 506 laps carrying the existing useful marker.
It contained no protocol-valid controlled workflow, no frozen prospective
prediction population, and no field-confirmed Next Gen geometry profile. These
archive counts are inventory only: they are not qualified independent evidence
and do not unlock any gate. The locked-feature matrix and remaining deficits are
recorded in `docs/p21_locked_feature_audit.md`.

## Immutable evidence registry

`racelab_engine/evaluation/dataset_registry.py` defines content-addressed dataset,
artifact, unit, split, qualification, and manifest records. Dataset identity binds
source fingerprints, car/track/build/profile/setup context, analysis artifacts,
qualification state, independence units, and split assignment. Persistence rejects
identity mutation instead of silently revising a scientific population.

`split_policy.py` freezes group, workflow, session, driver, track, build,
chronological, and prospective split policies. `leakage.py` fails closed on:

- duplicate source telemetry under different run IDs;
- shared workflow, artifact, lineage, or source across train and evaluation;
- A/B/A2 stages split across partitions;
- adjacent windows promoted into independent experiments;
- synthetic-only populations used for real-world activation.

## Reproducible evaluation artifacts

`metric_evaluation.py` binds every result to code hash, dataset hash, split-policy
hash, configuration hash, vehicle-profile hash, frozen metric definitions,
thresholds, subgroup requirements, and negative controls. Re-evaluation creates a
new artifact rather than overwriting history. Reports remain inspectable and label
historical, held-out, and prospective evidence distinctly.

The harness includes:

- probability calibration: Brier score, log loss, reliability bins, and shadow
  interval coverage;
- change-point candidates: robust thresholding and CUSUM, with a blocked PELT
  contract and no evaluation-set tuning;
- setup-response evaluation with target metric, mechanism response, policy
  verdict, and countereffect kept separate;
- protocol-valid controlled-effect evaluation requiring complete A/B/A2,
  one-control intervention, placebo survival, and successful restoration;
- negative-transfer comparison against an explicit no-transfer baseline;
- shadow planner comparison against the deterministic P19 planner, with any
  authority violation or unsafe false stop invalidating the candidate.

## Evidence collection campaigns

Seven content-addressed campaign contracts define the missing work instead of
pretending the archive is sufficient:

1. same-setup driver-noise characterization;
2. controlled one-change A/B/A2 response history;
3. tire-channel update-semantic validation;
4. matched-context long-run degradation and migration;
5. source-backed vehicle geometry validation;
6. steering/FFB control-workload validation;
7. null and known-no-change false-positive measurement.

Attempts are append-only and progress counts unique declared independence units,
not laps or duplicated run identifiers. Each contract names required context,
telemetry, setup snapshots, controlled variables, allowed variation, acceptance
criteria, stop criteria, and recovery behavior.

## Proxy and profile validation

Eight P20 proxy contracts now state the allowed claim, forbidden claim, ground
truth, reference semantics, error metric, valid operating envelope, and known
failure modes. Snapshot tire channels cannot qualify a live-trend model, and an
FFB/control mismatch cannot qualify steering-workload transfer. Raw rear wheel
disagreement remains geometry-contaminated until the required geometry is confirmed.

Vehicle-profile validation is field-level and exact-car/build scoped. Records may
be unvalidated, source-only, empirically confirmed, stale, or failed. A profile
hash or vehicle identity does not imply that wheelbase, track widths, steering
ratio, mass properties, motion ratios, or sign conventions have been validated.

## Shadow intelligence and activation gates

Shadow contracts, predictions, outcomes, and evaluations are durable and
prospective. A prediction is frozen before its outcome can be attached. Research
contracts for sideslip, gravity compensation, and wheel geometry declare their
missing prerequisites; no hidden fallback upgrades their authority.

Thirteen content-addressed activation gates declare required datasets, minimum
independent counts, frozen split policy, metrics, thresholds, subgroup coverage,
negative controls, prospective requirements, and maximum permitted authority.
Decisions must match the exact dataset, code, split, capability, and review
eligibility identity. There is no client or manual boolean override.

Current production states are intentionally conservative:

- probability calibration, sideslip, information-gain planning, Bayesian
  optimization, and multi-control optimization: **locked**;
- response modeling: **descriptive only**;
- change-point candidates: **shadow**;
- all advanced models together: **shadow only**, with P19/P20 authoritative.

## Learning Mode projection

`GET /api/evaluation/learning-readiness` reads only archive metadata and P21
registries; it does not scan telemetry or run a candidate model. The projection is
bound to exact run and optional session scope and reports qualified counts,
vehicle-profile status, capability states, collection campaigns, and scientific
debt. Stale or mismatched responses are discarded by the client.

The card appears only in Smart Engineer Learning Mode, including fail-closed
recovery states. Race Mode has no calibration clutter. The card says which system
retains production authority and never presents archive inventory as qualified
evidence.

## Verification

- 2,182 Python tests passed; six protected fixture-dependent tests skipped.
- Whole-repository Ruff passed.
- TypeScript passed.
- Production Vite build passed (2,189 modules).
- `git diff --check` passed.
- Focused P21 hostile tests cover duplicate-source leakage, adjacent-window
  pseudoreplication, workflow split contamination, synthetic activation denial,
  snapshot/live-trend mismatch, FFB mismatch, incomplete A/B/A2, failed A2
  restoration, mechanism/policy separation, planner authority violations,
  false-stop invalidation, gate identity, and client override denial.
- A fresh temporary database measured Learning Readiness at 18.051 ms cold and
  15.735 ms mean warm. It is Learning-only and not a cockpit-startup dependency.
- Live local browser smoke confirmed the exact archive deficits and `Shadow only`
  state in Learning Mode, zero Learning Readiness headings in Race Mode, and no
  console errors.

Synthetic signals were used only to test mechanics and hostile failure behavior.
No real proxy, causal effect, calibration model, or statistical setup authority was
validated by P21. Real-world campaigns and prospective scoring remain required.
