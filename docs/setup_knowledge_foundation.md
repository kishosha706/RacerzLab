# Setup Knowledge Foundation

RacerZLab setup knowledge lives under `racelab_engine/knowledge/setup`. It is a
local deterministic foundation for later Dial-In Assistant, setup guide, quiet
memory, and crew-chief responses.

## Purpose

The knowledge layer turns driver language into structured, car-aware setup test
candidates:

Driver complaint -> vocabulary parser -> canonical symptom -> car capability
filter -> setup-effect ranking -> evidence readiness -> effect/counter-effect
explanation -> one-change test plan.

It does not build a chat UI, call external AI, add API keys, alter telemetry
math, change imports, or change public API schemas.

## Milestone History

Milestone 1 established the local foundation: schema, loader, validator, matcher,
seed JSON data, query CLI, docs, and tests.

Milestone 2 added richer effect/counter-effect detail, phase-aware ranking,
package archetype context, evidence readiness, expanded vocabulary, Next Gen
platform rules, ARB specificity, JSON output, and clearer one-change test
language.

## Schema And Data

Core schema sections:

- `CarCapability`
- `PhaseDefinition`
- `SymptomVocabularyEntry`
- `SetupArea`
- `SetupEffect`
- `PackageArchetype`
- `EvidenceRequirement`
- `NextGenPlatformRule`
- `ShockInterpretationRule`

Seed data files cover capabilities, phase vocabulary, setup areas, setup
effects, package archetypes, evidence requirements, Next Gen platform rules,
and shock interpretation rules.

## Query Intelligence

The matcher ranks candidates with:

- symptom and phase match
- car capability availability
- evidence readiness from placeholder evidence tags
- effect strength and coupling risk
- package archetype and track-family tags
- avoid/preferred conditions
- ambiguity and clarification questions

Readiness labels are `ready`, `partially_ready`, and
`missing_key_evidence`. Missing evidence lowers confidence but does not hide a
useful candidate.

## Capability Gates

Next Gen disables:

- `track_bar`
- `truck_arm_mount`
- `bump_stop`
- `packer`

Those areas remain in legacy oval knowledge and can appear for
`legacy_oval_generic` when relevant.

Next Gen ARB model:

- `front_arb_diameter`
- `front_arb_arm`
- `front_arb_preload`
- `front_arb_attach`
- `rear_arb_diameter`
- `rear_arb_arm`
- `rear_arb_preload`
- `rear_arb_attach`

Diameter options are `1.375` and `2.000`. Arm positions are `P1` through `P5`.
Diameter is a big package swing, arm position is a tuning swing, preload is a
load/detail swing, and attach state is a setup/procedure state.

## Platform And Shock Notes

Next Gen platform rules emphasize CFS/front ride-height platform, rear
ride-height platform, smooth rake, diffuser volume proxy, scrape, and speed
loss together. Diffuser proxy channels are derived geometry/proxy signals, not
force measurements.

Shock interpretation distinguishes compression/shortening, rebound/extending,
low-speed body-motion regions, high-speed bump/impact regions, and selected-zone
histogram evidence.

## Examples

```powershell
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off"
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "tight center"
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "draggy" --evidence setup_snapshot,platform_trace
python -B scripts/query_setup_knowledge.py --car-family legacy_oval_generic --symptom "tight center" --show-disabled
python -B scripts/query_setup_knowledge.py --car-family next_gen --symptom "loose off" --json
```

Example text output:

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

Next milestone: Evidence Adapter. It should translate local telemetry, Compare
results, setup snapshots, and notebook context into the evidence tags consumed
by this deterministic layer.
