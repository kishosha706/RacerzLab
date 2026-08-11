# Setup Knowledge Foundation

RacerZLab setup knowledge lives under `racelab_engine/knowledge/setup`. It is a
local deterministic foundation for internal candidate generation and the setup
guide. It is not a public setup-authority surface.

## Purpose

The knowledge layer turns driver language into structured, car-aware mechanism
and control-area hypotheses:

Driver complaint -> vocabulary parser -> canonical symptom -> car capability
filter -> internal setup-effect hypothesis ranking -> evidence readiness -> effect/counter-effect
explanation -> internal candidate -> P19 revalidation.

It does not build a chat UI, call external AI, add API keys, alter telemetry
math, change imports, or change public API schemas.

Directional effects, exact garage actions, and one-change templates in this
knowledge package stay internal. Public Dial-In responses strip direction and
exact values. Only the exact-session canonical P19 report may authorize and bind
one target into a controlled A/B/A2 workflow or publish Keep/Undo/retest policy.

## Milestone History

Milestone 1 established the local foundation: schema, loader, validator,
matcher, seed JSON data, docs, and tests. Its historical direct-query command is
not a current product interface.

Milestone 2 added richer effect/counter-effect detail, phase-aware ranking,
package archetype context, evidence readiness, expanded vocabulary, Next Gen
platform rules, ARB specificity, JSON output, and clearer one-change test
language.

The pre-3B quality pass tightened decision quality before the Evidence Adapter:
candidate diversity, package dependency wording, phase-specific shock/platform
language and stricter validator checks for common garage complaints.

Milestone 3B adds the Evidence Adapter: a local run-context layer that inspects
available evidence, detects conservative car/track family hints, and feeds real
evidence flags into the deterministic matcher.

The terminology remaster adds race-language vocabulary and display wording for
phrases such as `won't stay on bottom`, `RF is angry`, `nose is dragging`,
`won't take a set`, `aero wash`, `power oversteer`, and `curb instability`.
Normal public output keeps software internals hidden and speaks in data-profile,
signals, mechanism, counter-effect, and measurement language until P19 earns a
controlled test.

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

Effect/counter-effect wording is not filler. It tells the reasoning layer what
the hypothesis is trying to explain, what can get worse, which phase to judge, what
evidence should support the call, and what to validate afterward. Strength is
the lever size: `5` is a major package lever, `4` is a strong balance/platform
lever, `3` is a medium phase-specific lever, `2` is fine tuning, and `1` is
driver feel or polish. Risk describes coupling: low is localized, medium is
phase/system-sensitive, and high can move multiple phases or the full package.

Internal readiness labels are `ready`, `partially_ready`, and
`missing_key_evidence`. They order hypotheses only. `ready` does not mean setup
authorized, and missing evidence can only increase measurement debt.

Internal hypothesis-record discipline matters:

- title/change metadata = source knowledge retained for P19 validation, never
  copied directly into the public hypothesis projection
- garage_lever = the setup page lever or supported garage adjustment
- effect = the mechanism the source says the control can influence
- counter-effect = what it may hurt
- one-change test metadata = a candidate mission template that P19 must rebuild
  against current telemetry, legal options, history, and exact identity

Public Dial-In may name the control area and measurement needed, but it must not
publish the catalog's direction, increment, target, or `Change this` text.

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
attach state is a procedure/diagnostic state rather than a normal race action.

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

## Validation and source inspection

```powershell
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_guide_knowledge.py --setup-area ls_rebound --car-family next_gen
```

`query_guide_knowledge.py` is offline source inspection. It does not read a run,
authorize a setup action, or replace P19.

The public Dial-In shape is deliberately non-directional:

```text
Hypothesis: Cross weight
Mechanism to verify: Does diagonal support contribute to the selected symptom?
Counter-effect to watch: protected-phase regression or driver-execution change
Evidence: measurement required
Authority: withheld until P19 verifies one exact mission
```

When P19 authorizes a controlled mission, driver-facing setup text should use
the full setup term and explain confusing relationships compactly. Cross weight
is the LR + RF diagonal load relationship. Tire-pressure split guidance should
name the axle, diagonal, or tire pair where the matrix supports it, and UI
display should format stable internal IDs as readable labels for drivers.

Internal front/rear ride-height hypothesis records must retain the relevant ride
height or shock-collar semantics. Public hypotheses remain non-directional.
When P19 later authorizes a collar mission, it must state that collar changes
move ride height, spring preload, and corner weight together.

For NASCAR-facing setup copy, use `rear end ratio` instead of `final drive`.
Diffuser/platform wording must stay on derived geometry proxy, front-feed,
rear-outlet, scrape/contact, and speed-trend language. It must not claim
measured downforce or universal exact setup values.

The next layer after source digestion is now implemented: the Evidence Adapter
translates local telemetry context, Compare run presence, setup snapshots, and
track-map availability into the evidence tags consumed by this deterministic
matcher. See `docs/setup_evidence_adapter.md`.
