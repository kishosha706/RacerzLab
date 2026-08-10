# P22 Prospective Field Validation and Learning Operations

Status: **verified operational foundation; real campaigns and advanced authority
remain data-locked**.

P22 turns P21's scientific contracts into executable, restart-safe collection
work without changing the production intelligence path. P19 remains the sole
cause, measurement, setup-response, Keep/Undo, and stop-testing authority. P20
remains the sole whole-car state projection.

## Executable evidence campaigns

Each P21 campaign can be started as a content-addressed operation bound to its
campaign identity and a reference recording. The frozen contract records source
fingerprint, car, track, iRacing build, setup identity where required, fuel and
weather bands, traffic ceiling, and the clean-lap requirement. Lifecycle events
are append-only and permit only deterministic start, pause, resume, complete,
and abandon transitions.

Successful `.ibt` imports are assessed automatically against active operations.
Qualification uses canonical eligible laps only and rejects junk or partial laps,
unknown or excessive nearby-car exposure, out-of-band fuel or weather, setup or
identity mismatch, duplicate source telemetry, and material/requested control
mutations. Every accepted lap, rejected lap, and rejection reason is persisted.
Repeated assessment is idempotent and cannot double-count an independence unit.

Same-setup driver-noise and clean uninterrupted long-run recordings can be
promoted automatically to the corresponding P21 attempt. Controlled setup,
tire-semantic, geometry, control-workload, and null campaigns remain pending
until their required controlled workflow or external validation record exists;
mere lap count cannot satisfy those protocols. Geometry validation is explicitly
an external source-integrity campaign and is not misrepresented as driver-lap
work.

## Frozen prospective tests

A controlled-operation prediction can be frozen only before a B/A2 outcome
exists. The server captures the complete canonical P19 reasoning snapshot,
snapshot identity, runtime code hash, exact source session/run, proposed control
and direction, predicted mechanism response, predicted control response,
countereffects, and explicit success/failure criteria. The record is immutable,
prospective, non-ground-truth, and shadow-only.

After the canonical P19 A/B/A2 workflow is scored, P22 attaches an immutable
outcome derived from that saved workflow. Mechanism outcome, driver/control
response, countereffects, and Keep/Undo policy remain distinct fields. One
prediction can match one workflow outcome, and hindsight freezing or rematching
is rejected. P22 failures are isolated from P19 scoring so experimental
bookkeeping can never weaken production truth or policy.

## Evidence Acquisition Director

The Director ranks feasible collection options with an inspectable deterministic
heuristic:

`deficit fraction × rule-fit estimate × gates helped ÷ estimated laps`

This is collection guidance only. The rule-fit value is not a learned or
calibrated probability, and the result is not formal information gain. It cannot
choose a setup value, control a car, rank a production cause, stop a P19 mission,
or unlock a capability. Infeasible work remains visible with its blocker instead
of being silently assigned a low score.

## Learning Ledger and activation review

Smart Engineer Learning Mode now projects four evidence classes:

- **Proven guardrails** contain verified architecture and isolation guarantees.
- **In validation** contains exact campaign progress from qualified independent
  units, not laps or archive inventory.
- **Failed** contains immutable failed gate decisions.
- **Locked** contains capabilities whose frozen evidence gates are not satisfied.

The capability review evaluates the P22 gate set without preselecting a model.
No manual override exists. A future passing non-planner gate can become eligible
only for a separate bounded observation-overlay review; it does not activate a
production model. Formal information gain remains shadow-only, and Bayesian or
multi-control optimization cannot exceed shadow authority. Today, with no exact
qualified field population, all advanced capabilities remain locked.

## Failure and data-truth boundaries

- Import remains successful if P22 assessment fails; the failure is logged and
  no evidence is promoted.
- P19 workflow scoring remains authoritative if outcome attachment fails; the
  frozen prediction remains recoverable and unscored.
- Archive counts, duplicate files, synthetic tests, and adjacent laps cannot
  masquerade as independent real evidence.
- P22 creates no runtime draft logic, live manipulation, input automation, or
  setup authority.
- The UI is Learning Mode only; Race Mode remains decision-first and free of
  calibration operations.

The next real milestone is operational rather than architectural: run the frozen
campaigns with Next Gen `.ibt` recordings, accumulate qualified independent
units, score prospective outcomes, and let the pre-registered gates determine
whether any bounded observer has earned a later activation review.
