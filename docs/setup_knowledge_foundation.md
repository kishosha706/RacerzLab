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

The pre-3B quality pass tightened decision quality before the Evidence Adapter:
candidate diversity, package dependency wording, phase-specific shock/platform
language, stricter validator checks, and query examples for common garage
complaints.

Milestone 3B adds the Evidence Adapter: a local run-context layer that inspects
available evidence, detects conservative car/track family hints, and feeds real
evidence flags into the deterministic matcher.

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

Effect/counter-effect wording is not filler. It tells the future assistant what
the swing is trying to help, what can get worse, which phase to judge, what
evidence should support the call, and what to validate afterward. Strength is
the lever size: `5` is a major package lever, `4` is a strong balance/platform
lever, `3` is a medium phase-specific lever, `2` is fine tuning, and `1` is
driver feel or polish. Risk describes coupling: low is localized, medium is
phase/system-sensitive, and high can move multiple phases or the full package.

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
force measurements. Front ride-height platform helps define diffuser feed. Rear
ride-height platform helps define outlet/expansion and scrape/choke behavior.
Rear height alone does not determine rear aero behavior, front higher than rear
is not automatically wrong, lower is not automatically faster, and static rake
sign does not decide if a setup is good.

Shock interpretation distinguishes compression/shortening, rebound/extending,
low-speed body-motion regions, high-speed bump/impact regions, and selected-zone
histogram evidence. A shock histogram is evidence, not a setup command; it must
agree with the complaint phase, driver inputs, platform trace, and same-zone
behavior before ranking a shock swing high.

Setup packages are first-class context. Crossweight, platform, spring, shock,
ARB, toe, tire-pressure, and tire-protection candidates can be right or wrong
depending on the package they live in. The matcher keeps package tags and
preferred/avoid conditions available so the Evidence Adapter can feed package
context without adding new setup logic.

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
Candidate 1: Add a little cross weight
Strength: 4 / strong balance lever
Risk: high
Effect: Can calm entry-to-drive-off balance by adding cross weight diagonal support.
Counter-effect: May bind the center or add scrub if the car was already loaded too tightly.
Evidence: missing key evidence
One-change test: Try one small swing: Add a little cross weight...
Validate: exit_yaw, center_speed, tire_trend
Watch for: tight_center, tight_exit, drag_scrub
```

Driver-facing setup text should use the full setup term and explain confusing
relationships compactly. Cross weight is the LR + RF diagonal load
relationship. Tire pressure split guidance should name the axle, diagonal, or
tire pair where the matrix supports it, and UI/CLI display should format stable
internal IDs as readable labels for drivers.

The next layer after source digestion is now implemented: the Evidence Adapter
translates local telemetry context, Compare run presence, setup snapshots, and
track-map availability into the evidence tags consumed by this deterministic
matcher. See `docs/setup_evidence_adapter.md`.
