# RacerZLab Setup Knowledge

This package is the local, deterministic setup-knowledge layer for RacerZLab.
It has no runtime AI dependency, no API keys, and no external calls. It does
not change telemetry formulas, import pipeline behavior, or public API schemas.

## Flow

1. Parse driver vocabulary into a canonical symptom and phase.
2. Apply car-family capability gates.
3. Rank setup effects by symptom, phase, evidence readiness, strength, risk,
   package archetype, and track-family context.
4. Return effect/counter-effect wording, missing evidence, ranking reasons,
   and one-change test language.

## Files

- `schema.py`: typed Pydantic models for capabilities, symptoms, effects,
  setup areas, packages, evidence, platform rules, and shock interpretation.
- `loader.py`: loads every JSON data file and runs validation.
- `matcher.py`: deterministic parser, capability filter, ranker, and
  explanation assembler.
- `validator.py`: local consistency and safety checks.
- `data/*.json`: RacerZLab-owned seed knowledge.

## Data Philosophy

Setup effects describe candidate tests, not universal values. Each effect keeps
primary effects, counter-effects, evidence requirements, validation targets,
avoid/preferred conditions, and exact-value policy. Package-level levers such as
ARB diameter are treated as reference/package tests. Fine-tuning levers can be
shown as small-swing tests when explicitly marked.

Effect/counter-effect wording is part of the decision quality contract. A
candidate should say what symptom it is trying to help, which phase it applies
to, what can get worse, what evidence should support it, and what to validate
after the test. Strength and risk are separate: strength describes the size of
the setup lever, while coupling risk describes how many phases or systems the
lever can disturb.

Setup packages matter because a single garage value can be normal in one package
and wrong in another. The ranker can use package tags, preferred conditions, and
avoid conditions to keep crossweight, platform, ARB, tire, spring, and shock
suggestions tied to the surrounding setup.

Next Gen disables `track_bar`, `truck_arm_mount`, `bump_stop`, and `packer`.
Those areas remain available for legacy oval knowledge when the selected car
family supports them.

Next Gen ARB constraints:

- Diameter: `1.375`, `2.000`
- Arm positions: `P1`, `P2`, `P3`, `P4`, `P5`
- Diameter, arm, preload, and attach state are separate setup areas.

Diffuser/platform wording treats proxy channels as derived comparison signals,
not force measurements. Front ride-height platform helps define diffuser feed.
Rear ride-height platform helps define outlet/expansion and scrape/choke
context. Ride-height, collar, or spring changes should not be suggested from
static rake alone.

Shock histograms are evidence, not a command. Low-speed shock changes belong to
driver-input transitions such as braking, brake release, steering input, and
throttle pickup. High-speed shock changes belong to bumps, dips, curbs, banking
transitions, and sharp platform events. The Evidence Adapter now maps local
trace metadata into those evidence tags without changing the deterministic
setup logic.

## Commands

```powershell
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off"
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "draggy" --evidence setup_snapshot,platform_trace
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off" --json
```

## Dial-In Driver Response

The Dial-In service and Setup tab panel use this package as a deterministic
setup brain. Driver-facing output stays clean: interpreted complaint,
confidence/readiness, up to three setup swings, effect/counter-effect,
one-change test, and validate/watch targets. Backend evidence can be inspected
with explicit debug flags, but normal UI/API output hides raw evidence groups,
ranking scores, source IDs, and channel lists.

Clarification is part of the safety model. Generic complaints such as `loose`
or `tight` ask for phase before returning setup swings. Unknown car family stays
conservative and does not unlock legacy-only levers.

## Milestones

Milestone 1 created the local schema, seed data, validator, matcher, query CLI,
and tests. Milestone 2 enriched ranking with package context, evidence
readiness, clearer effect/counter-effect explanations, ARB specificity, and
Next Gen platform wording. The pre-3B quality pass tightened phase specificity,
package dependency notes, candidate diversity, and validation checks. Milestone
3B added the run-aware Evidence Adapter and run-context query CLI. The Dial-In
milestone added the clean service contract, API route, CLI, and read-only Setup
tab panel.

## Example Output

Text output is designed to be readable in PowerShell:

```text
Candidate 1: Add a little cross weight
Strength: 4 / strong balance lever
Risk: high
Effect: Can calm entry-to-drive-off balance by adding diagonal support.
Counter-effect: May bind the center or add scrub if the car was already loaded too tightly.
Evidence: missing key evidence
One-change test: Try one small swing: Add a little cross weight...
Validate: exit_yaw, center_speed, tire_trend
Watch for: tight_center, tight_exit, drag_scrub
```

The run-context layer is now in place: the Evidence Adapter maps real local
telemetry, Compare output, setup snapshots, and notebook context into the
placeholder evidence tags this layer already understands. See
`docs/setup_evidence_adapter.md` for details.
