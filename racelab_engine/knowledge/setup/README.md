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

Next Gen disables `track_bar`, `truck_arm_mount`, `bump_stop`, and `packer`.
Those areas remain available for legacy oval knowledge when the selected car
family supports them.

Next Gen ARB constraints:

- Diameter: `1.375`, `2.000`
- Arm positions: `P1`, `P2`, `P3`, `P4`, `P5`
- Diameter, arm, preload, and attach state are separate setup areas.

Diffuser/platform wording treats proxy channels as derived comparison signals,
not force measurements. Ride-height, collar, or spring changes should not be
suggested from static rake alone.

## Commands

```powershell
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off"
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "draggy" --evidence setup_snapshot,platform_trace
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off" --json
```

## Milestones

Milestone 1 created the local schema, seed data, validator, matcher, query CLI,
and tests. Milestone 2 enriched ranking with package context, evidence
readiness, clearer effect/counter-effect explanations, ARB specificity, and
Next Gen platform wording.

## Example Output

Text output is designed to be readable in PowerShell:

```text
Candidate 1: Add a little cross
Strength: 4 / strong balance lever
Risk: high
Effect: Can calm entry-to-drive-off balance by adding diagonal support.
Counter-effect: May bind the center or add scrub if the car was already loaded too tightly.
Evidence: missing key evidence
One-change test: Try one small swing: Add a little cross...
Validate: exit_yaw, center_speed, tire_trend
```

The next milestone is the Evidence Adapter: mapping real local telemetry,
Compare output, setup snapshots, and notebook context into the placeholder
evidence tags this layer already understands.
