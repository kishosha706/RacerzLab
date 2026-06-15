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

The terminology remaster adds race-language vocabulary and display wording for
phrases such as `won't stay on bottom`, `RF is angry`, `nose is dragging`,
`won't take a set`, `aero wash`, `power oversteer`, and `curb instability`.
Normal output keeps software internals hidden and speaks in data-profile,
signals, goal/trade-off, and one-change-test language.

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

Recommendation title discipline matters:

- title = exact garage action
- effect = what that action should help
- counter-effect = what it may hurt
- one-change test = one small garage-side validation step

Avoid vague title wording such as `platform support`, `pressure trim`,
`rear toe stability`, or `shock control` when the real lever is known.

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

Diameter options are `1.375` and `2.000`. Arm positions are `P1` through `P5`: `P1` is softest/lowest/looser, `P5` is stiffest/tighter. Use a one-P arm move for a smaller tuning swing; use a diameter change only for a bigger package swing.
Diameter is a big package swing, arm position is a tuning swing, preload is a
load/detail swing that can mask ride-height or corner-weight problems, and
attach state is a procedure/diagnostic state rather than a normal race
recommendation.

## Platform And Shock Notes

Next Gen platform rules emphasize CFS/front ride-height platform, rear
ride-height platform, smooth rake, diffuser volume proxy, scrape, and speed
loss together. Diffuser proxy channels are derived geometry/proxy signals, not
force measurements. Front ride-height platform helps define diffuser feed. Rear
ride-height platform helps define outlet/expansion and scrape/choke behavior.
Rear height alone does not determine rear aero behavior, front higher than rear
is not automatically wrong, lower is not automatically faster, and static rake
sign does not decide if a setup is good.

Shock interpretation distinguishes bump/compression shortening, rebound
(extension), low-speed driver/platform movement, high-speed track/bump
movement, and selected-zone histogram evidence. A shock histogram is a movement
signature and evidence, not a setup command; it must agree with the complaint
phase, driver inputs, platform trace, and same-zone behavior before ranking a
shock swing high.

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
Validate: exit yaw, center speed, tire trend
Watch for: exit yaw, RF tire temp, center rotation
```

Driver-facing setup text should use the full setup term and explain confusing
relationships compactly. Cross weight is the LR + RF diagonal load
relationship. Tire pressure split guidance should name the axle, diagonal, or
tire pair where the matrix supports it, and UI/CLI display should format stable
internal IDs as readable labels for drivers.

Front and rear ride-height platform recommendations should name ride height or
shock collar offsets directly. When the move is through LF/RF or LR/RR collars,
the helper text should remind the driver that collar changes move ride height,
spring preload, and corner weight together.

For NASCAR-facing setup copy, use `rear end ratio` instead of `final drive`.
Diffuser/platform wording must stay on derived geometry proxy, front-feed,
rear-outlet, scrape/contact, and speed-trend language. It must not claim
measured downforce or universal exact setup values.

The next layer after source digestion is now implemented: the Evidence Adapter
translates local telemetry context, Compare run presence, setup snapshots, and
track-map availability into the evidence tags consumed by this deterministic
matcher. See `docs/setup_evidence_adapter.md`.
