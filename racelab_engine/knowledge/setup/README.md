# RacerZLab Setup Knowledge

This package is the local, deterministic setup-knowledge layer for RacerZLab.
It has no runtime AI dependency, no API keys, and no external calls. It does
not change telemetry formulas, import pipeline behavior, or public API schemas.

## Flow

1. Parse driver vocabulary into a canonical symptom and phase.
2. Apply car-family capability gates.
3. Rank internal setup-effect hypotheses by symptom, phase, evidence readiness,
   strength, risk, package archetype, and track-family context.
4. Return source metadata, effect/counter-effect wording, missing evidence, and
   ranking reasons to the canonical reasoning path.

This package never publishes setup authority. Public Dial-In strips direction,
increments, targets, and action language. Only P19 may bind one internal
candidate to an exact legal A/B/A2 mission or publish Keep/Undo/stop-testing.

## Files

- `schema.py`: typed Pydantic models for capabilities, symptoms, effects,
  setup areas, packages, evidence, platform rules, and shock interpretation.
- `loader.py`: loads every JSON data file and runs validation.
- `matcher.py`: deterministic parser, capability filter, ranker, and
  explanation assembler.
- `validator.py`: local consistency and safety checks.
- `data/*.json`: RacerZLab-owned seed knowledge.

## Data Philosophy

Setup effects are source hypotheses, not universal values or public tests. Each
effect keeps primary effects, counter-effects, evidence requirements, validation targets,
avoid/preferred conditions, and exact-value policy. Package-level levers such as
ARB diameter retain package-level metadata. Fine-tuning levers may retain an
internal small-swing template, but P19 must revalidate and rebuild any public
mission from current evidence and legal-option provenance.

Effect/counter-effect wording is part of the decision quality contract. A
candidate should say what symptom it is trying to help, which phase it applies
to, what can get worse, what evidence should support it, and what to validate
after the test. Strength and risk are separate: strength describes the size of
the setup lever, while coupling risk describes how many phases or systems the
lever can disturb.

Setup packages matter because a single garage value can be normal in one package
and wrong in another. The ranker can use package tags, preferred conditions, and
avoid conditions to keep crossweight, platform, ARB, tire, spring, and shock
hypotheses tied to the surrounding setup.

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
context. Static rake alone cannot support a ride-height, collar, or spring
action.

Shock histograms are evidence, not a command. Low-speed shock changes belong to
driver-input transitions such as braking, brake release, steering input, and
throttle pickup. High-speed shock changes belong to bumps, dips, curbs, banking
transitions, and sharp platform events. The Evidence Adapter now maps local
trace metadata into those evidence tags without changing the deterministic
setup logic.

## Validation and source inspection

```powershell
python -B scripts/validate_setup_knowledge.py
python -B scripts/query_guide_knowledge.py --setup-area ls_rebound --car-family next_gen
```

The guide query is offline source inspection. It does not read a run or
authorize a setup action. There is no standalone direct-action matcher command.

## Dial-In Driver Response

The Dial-In service and Dial-In workspace use this package as a deterministic
hypothesis source. Driver-facing output stays clean: interpreted complaint,
confidence/readiness, up to three non-directional control-area hypotheses,
mechanisms/counter-effects to verify, measurement needs, and validate/watch
signals. Backend evidence can be inspected
with explicit debug flags, but normal UI/API output hides raw evidence groups,
ranking scores, source IDs, and channel lists.

Clarification is part of the safety model. Generic complaints such as `loose`
or `tight` ask for phase before returning hypotheses. Unknown car family stays
conservative and does not unlock legacy-only levers.

## Milestones

Milestone 1 created the local schema, seed data, validator, matcher,
and tests. Milestone 2 enriched ranking with package context, evidence
readiness, clearer effect/counter-effect explanations, ARB specificity, and
Next Gen platform wording. The pre-3B quality pass tightened phase specificity,
package dependency notes, candidate diversity, and validation checks. Milestone
3B added the run-aware Evidence Adapter. Historical direct-query tools were
removed when P19 became the sole setup-authority path. Dial-In now exposes only
the strict non-authorizing public hypothesis projection.

## Example Output

The public response is deliberately non-directional:

```text
Hypothesis: Cross weight
Mechanism to verify: Does diagonal support contribute to the selected symptom?
Counter-effect to watch: protected-phase regression or driver-execution change
Evidence: measurement required
Authority: withheld until P19 verifies one exact mission
```

The run-context layer is now in place: the Evidence Adapter maps real local
telemetry, Compare observations, and setup snapshots into the
placeholder evidence tags this layer already understands. See
`docs/setup_evidence_adapter.md` for details.
