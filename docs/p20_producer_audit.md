# P20 existing-producer audit

Status: **complete read-only audit; Slice B backend verified**

Audited commit: `143b1b4ef88b09d4d425502c9b4e1463b51753a5`

Audit date: 2026-08-09

This audit maps existing telemetry producers into the canonical P19 observation
and reasoning path before P20 adds any formula. Slice B closed the identified
fusion debt without promoting a producer, inventing a finding, or creating setup
authority.

## Canonical path and ownership

The production path is backend-owned:

`producer artifact -> MechanismObservation -> observation hypotheses -> P19 evidence graph -> ReasoningSnapshot`

`observation_intelligence_service` first adapts persisted telemetry events, then
performs one projected telemetry read for missing P3 mechanisms and merges by
exact `observation_id`. `run_intelligence_service` converts qualified observations
to hypotheses and asks `intelligence_service` to build the signed evidence graph
and canonical reasoning snapshot. P20 state frames and future episodes must remain
inputs to that path; they may not rank causes or authorize setup policy.

The P3 bridge preserves producer and artifact identity, every source run/setup,
run/lap identity, exact physical-position windows, phase, source channels,
evidence state, sample coverage, citations, sample count, repetition count, and
blocker reasons. Producer exceptions fail closed. Existing mechanism observations
suppress only their own missing-producer invocation, and report merging
deduplicates exact producer/artifact identity rather than mechanism kind.

## Producer map

| Mechanism family | Existing producer-owned artifact | Direct typed path into canonical reasoning | Current debt / Slice B disposition |
|---|---|---|---|
| `driver_execution` | `phase_engineering.analyze_phase_engineering_systems` -> `DriverLineReport` under `DRIVER_LINE_CONTRACT` | **Yes.** Same-setup eligible-lap pair, matched by physical track position, adapted by `p3_observation_bridge`. | Preserve the paired comparison and exact common-position scope. Do not treat two laps as two independent experiments. |
| `braking_response` | `braking_efficiency.analyze_braking_efficiency` -> `BrakingEfficiencyReport` under `BRAKING_EFFICIENCY_CONTRACT` | **Yes.** Direct single-producer bridge with integrity gate and exact selected-lap window. | No missing path found. Preserve producer blockers independently. |
| `corner_rotation` | `phase_engineering.analyze_phase_engineering_systems` -> `CornerRotationReport` under `CORNER_ROTATION_CONTRACT` | **Yes.** Same-setup eligible-lap pair, matched by physical track position, adapted by `p3_observation_bridge`. | Preserve distinct physical windows and driver-comparability blockers. |
| `tire_state` | `tire_state_energy.analyze_tire_state` -> `TireStateReport` under `TIRE_STATE_CONTRACT` | **Yes.** Direct single-producer bridge with explicit working-history repetition. | Retain P19 pit-snapshot/constant/unhealthy semantics. Constant carcass/wear values cannot become live trends. |
| `damper_response` | `damper_response.analyze_damper_response` -> `DamperResponseReport` under `DAMPER_RESPONSE_CONTRACT` | **Yes.** Direct single-producer bridge with minimum sample binding and integrity gate. | A response observation remains descriptive; a repeated bump alone cannot authorize a damper change. |
| `platform_response` | `phase_engineering.analyze_phase_engineering_systems` -> `AeroPlatformReport` under `AERO_PLATFORM_WINDOW_CONTRACT` | **Yes.** The paired phase producer now adapts platform evidence with both same-setup lap citations and the exact common-position scope. | Preserve proxy language and the producer's driver/integrity/attribution blockers. No new platform formula was added. |
| `resistance_scrub_like` | `relative_resistance.analyze_relative_resistance_aba` -> `RelativeResistanceReport` under the relative-resistance evidence contract | **Yes, controlled path only.** The controlled-producer adapter requires distinct server-verified A1/B/A2 run/setup/lap/window scopes and preserves all three citations. A single-run resistance-like proxy remains explicitly blocked. | Traffic, grade, integrity, compatibility, and isolated-change gates stay producer-owned. Never emit exact drag, CdA, or exact power loss. |
| `powertrain_response` | `powertrain_gearing.analyze_powertrain_gearing` -> `PowertrainGearingReport` under `POWERTRAIN_GEARING_CONTRACT` | **Yes.** Direct single-producer bridge with integrity and comparable-lap binding. | Preserve redline unavailability and compatibility blockers. Weight/power/build compatibility becomes explicit in Slice C. |
| `stint_trend` | `stint_strategy.analyze_stint_strategy` -> `StintStrategyReport` under `STINT_STRATEGY_CONTRACT` | **Yes.** The run bridge adapts qualified conclusions and cites every exact producer-used continuous-stint lap before row-level source-channel rebinding. | Traffic, fuel, weather, tire update semantics, short-run limits, and integrity remain producer blockers; another producer cannot clear them. |
| `sim_integrity` | `sim_integrity.build_sim_integrity_certificate` -> `SimIntegrityCertificate` under `SIM_INTEGRITY_CONTRACT` | **Yes.** The certificate publishes its own exact selected-lap typed state while continuing to gate every other producer independently. | A passing certificate is not a physical finding and cannot clear another subsystem. Failure evidence remains integrity state, not a setup cause. |

## Event-adapter boundary

`adapt_event_mechanism_observations` maps event type/subtype text to all ten
mechanism kinds. That is a useful compatibility path for already persisted events,
but it is not proof that each subsystem producer has a complete typed path. The
adapter may carry only the event's declared evidence and blockers. It must not be
used to manufacture a missing producer artifact or to reinterpret one subsystem's
success as another subsystem's success.

## Columnar and performance boundary

The current observation service makes one projected telemetry read using
`p3_observation_columns`, then runs deterministic producers on that projection.
Slice B must extend that projection once for the four missing paths; it must not
add repeated full-frame reads or make the row fallback the production default.
The vectorized normalizer remains authoritative, and exact row-path parity remains
the debug/fallback contract.

## Slice B conclusion

All ten families now have a typed producer-owned route to canonical P19 input.
Nine run-owned families share one projected telemetry read; controlled resistance
preserves its three independent stage scopes. Distinct same-kind physical windows
survive fusion, and only a true duplicate producer/artifact identity deduplicates.
No second ranker, telemetry formula, inferred missing value, or setup authority was
added.
