# RacerZLab Evidence-Driven Engineering Roadmap

> Source: the telemetry-evolution blueprint supplied on 2026-08-03.
> This is the repository's living execution checklist. Update it in the same
> change that completes an item, and include the verification evidence.
> `AGENTS.md` remains authoritative when a roadmap idea conflicts with a project rule.

## Product north star

RacerZLab should operate as a local race-engineering system:

**lossless telemetry -> capability truth -> evidence qualification -> precise
time-loss diagnosis -> one controlled setup experiment -> causal comparison ->
persistent learning**

The differentiator is not another configurable telemetry viewer. The product
must determine whether data is trustworthy, explain where time was lost,
separate plausible causes, prescribe the smallest useful test, verify the
result, and remember only what the evidence supports.

## How to use this roadmap

- `[x]` means implemented and verified with evidence recorded below.
- `[ ]` means incomplete, even if scaffolding or an early approximation exists.
- `BLOCKED` means a current repository rule or missing prerequisite prevents work.
- Never check an item solely because code exists. Verify its behavior with tests
  and, where applicable, a real `.ibt` fixture.
- Do not allow a later phase to weaken an earlier trust gate.
- Every recommendation feature must link setup values to telemetry evidence.
- Prefer one small, testable setup change at a time.

## Current phase status

| Phase | Status | Exit condition |
|---|---|---|
| P0 - Universal Telemetry Foundation | Verified | Every file-declared signal is preserved and truthfully described |
| P1 - Evidence Eligibility | Verified for implemented engines | Every implemented conclusion is contract-gated and fail-closed |
| P2 - Alignment and Time | Verified backend and comparison UI | Time loss is measured at matched physical track positions |
| P3 - Engineering Systems | Verified backend slice | Ten phase-aware, contract-gated engineering systems are implemented |
| P4 - Controlled Test Director | Verified production workflow | Server-derived A/B/A2 execution, scoring, persistence, rollback, and certificate are wired |
| P5 - Crew-Chief Recommendation Engine | Verified production assembly | Server-derived evidence assembles the packet end to end |
| P6 - Setup Response Memory | Verified guarded response learning | Only controlled, provenance-complete effects become durable knowledge |
| P7 - Advanced Experimentation | Offline engine verified; activation LOCKED | No real controlled dataset has met the production unlock threshold |
| P8 - Unified Recommendation Intelligence | Production slice verified; calibration remains data-locked | One evidence authority ranks one context-aware next decision and explains its basis |
| P9 - Whole-App Performance | Verified import/frame-native foundation; full cold Engineer vectorization remains open | Run open, archive, trace, and warm intelligence avoid duplicate full-row work while cold decision access is measured explicitly |
| P10 - Evidence Integrity and Resilience | Verified | Hostile context, cache, persistence, and stale-UI paths fail closed without losing evidence |
| P11 - Decision-First Desktop UX | Verified | Race Mode exposes the next trustworthy decision first; Learning Mode preserves the complete evidence trail |
| P12 - Internal Engineering Intelligence | Verified | One evidence-bound Smart Engineer explains the decision, best next measurement, memory, and uncertainty without creating new setup authority |
| P13 - Cross-Tab Decision Broadcasting | Verified | Every workspace and shell signal shares exact scope, authority, recovery, and handoff truth |
| P14 - Evidence Compounding and Adaptive Engineering | Verified deterministic slice; statistical activation remains data-locked | Repeated observations, session history, recording health, and workflow state improve the next move without inventing probability or setup authority |
| P15 - Premium Race Engineering Experience | Verified | The whole app communicates one trustworthy next move with clear hierarchy, honest recovery, exact scope, and keyboard-safe responsive interaction |
| P16 - Premium Telemetry Visualization | Verified | Charts preserve raw signal, gap, unit, scope, selection, and proxy truth in a responsive open-canvas system |
| P17 - Oval Driver Operating System | Verified | An oval driver can read clean-run readiness, corner-cycle evidence, loaded-side tire context, setup identity, and one trustworthy next step without junk-lap or continuity overclaim |
| P18 - Deterministic Reasoning and Controlled Learning | Verified deterministic slice; statistical activation remains data-locked | Smart Engineer ranks independent evidence, learns exact controlled outcomes, explains falsification criteria, and blocks unsupported or repeated setup authority everywhere |
| P19 - Engineering Truth, Experiments, and Durable Memory | Verified closed-loop deterministic foundation; statistical activation remains data-locked | One canonical reasoning snapshot separates mechanism, control response, and policy; exact mission attempts and durable cross-session memory reconstruct safely across restart and unreadable history |
| P20 - Engineering State Awareness and Whole-Car Mechanism Fusion | Verified deterministic production slice; shadow observers and statistical activation remain data-locked | Exact state, context, temporal episodes, producer blockers, P19 authority, and stale-safe whole-car projection reach existing workspaces without a second reasoning path |
| P21 - Evidence Lab, Calibration, and Shadow Intelligence | Verified scientific infrastructure; advanced statistical authority remains locked | Immutable datasets, leakage-safe evaluation, collection campaigns, proxy/profile validation, prospective shadow records, and identity-bound activation gates expose exact learning debt without changing P19/P20 authority |
| P22 - Prospective Field Validation and Learning Operations | Verified operational foundation; real campaigns and advanced authority remain data-locked | Frozen campaign operations, automatic qualification, prospective P19 predictions/outcomes, deterministic collection guidance, and the Learning Ledger survive restart without granting setup or statistical authority |
| P23 - First Earned Adaptive Capability | No activation earned | Steering-workload protocol is frozen, but no qualified historical, prospective, negative-control, subgroup, or profile evidence exists |
| P24 - Evidence Acquisition Operations | Verified collection infrastructure; P23 evidence collection ongoing | Protocol-bound certificates, flight recorders, steering truth audits, and certificate-owned admission make real collection auditable without changing authority |
| P25 - First Qualified Evidence Campaign | Verified acquisition pilot; no qualified session earned because traffic contamination blocked every eligible lap | One source-owned Next Gen re-import proved immutable ownership, ten-signal/sub-tick/FFB truth, certificate-owned rejection, duplicate resistance, and a frozen future null-session card without changing P23 authority |
| P26 - Vehicle Systems Intelligence and Crew-Chief Component Graph | Verified deterministic Next Gen foundation | Source-backed component contracts, typed interactions, explicit observability debt, one-physical-factor experiments, P19/P20 runtime projection, grounded component tools, and compact Setup/Engineer surfaces enrich reasoning without creating setup authority |
| P27 - Autonomous Crew Chief Executive | Verified deterministic production foundation | One immutable, revision-bound executive schedules existing evidence inspections and mirrors only exact current P19 terminal authority |
| P28 - Trackside Mission Control | Verified deterministic production foundation | A hard Success Contract and junk/context-aware Run Sentinel govern mission progress without creating policy authority |
| P29 - Component Response Atlas and Driver Intelligence | Verified guarded production foundation | Exact-context controlled history and complaint/context-only driver memory persist separately with operational effectiveness counts |
| P30 - Adaptive Experimentation Research | Infrastructure seam verified; activation DATA-LOCKED | Production remains one-factor P19 A/B/A2 until P21/P22 held-out and prospective activation gates truly pass |
| P31 - Truthful Crew Loop | Implemented; release validation recorded below | Telemetry, experiment, evidence, Crew, Compare, P26, caching, and UI trust share exact identity while every authority lock remains intact |
| P32 - Lap-Time Mechanics and Speed Intelligence | Verified after P32.1 truth closure | Qualified driver demand, vehicle response, measured elapsed time, origin/carry, track demand, P20/P26 context, and exact P19 next move form one non-causal performance projection |
| P32.1 - Performance Truth Closure | Verified | Traffic and context lead attribution, signed gain/loss truth survives, controlled memory restarts exactly, and every rendered performance claim fails closed |
| P33 - Engineering Learning Flywheel | Verified deterministic attention-only foundation; adaptive authority remains locked | Immutable qualified experience improves recurrence retrieval and investigation order while current evidence and P19 retain all truth and setup authority |
| P33.1 - Driver-Facing Truth and Interface Sharpening | Verified | Race Mode stays decision-first, mission progress distinguishes screening from contract acceptance, and narrow layouts preserve a usable evidence-first workspace |
| P34 - Earned Investigation Adaptation | Verified shadow evaluation infrastructure; no attention activation earned | Frozen baseline-versus-memory pairs test bounded investigation order on identical pre-outcome truth while P19 remains sole authority and production remains deterministic baseline |
| P35 - Next Gen Oval Vehicle Dynamics Intelligence | Verified deterministic mechanical-intelligence foundation | One reviewed, build-applicable physics graph connects driver demand, vehicle response, tire/platform state, candidate mechanisms, and measured P32 time without gaining component, cause, or setup authority |
| P35.1 - Unified Dial-In Knowledge Spine | Verified deterministic engineering-knowledge foundation | One content-addressed projection connects exact P32 time, P20 state, P35 mechanisms, P26 components, all 92 Dial-In effects, P19/P33 history, bounded discriminators, and exact P19 authority without turning education into advice |
| P35.2 - Semantic Precision and Release Trust | Verified locally; remote SHA validation awaits the next push | Direction, experiment factor, component relevance, semantic roles, runtime evidence, physical scope, client trust, and normal CI gates are exact without changing P19 authority |
| P35.3 - Inner Crew Chief Cognitive Closure | Verified locally; remote SHA validation awaits the next push | Reachability-aware planning, exact cause state, typed inspection traces, bounded critic outcomes, driver-answer semantics, and post-open consumption counts close the deterministic investigation loop without changing P19 or frozen P34 authority |
| P35.4 - Phase-Resolved Vehicle Response and Setup Diagnosis | Verified deterministic response foundation; additional controls remain evidence-locked | Phase-resolved observations and qualified continuous response signatures describe driver demand and vehicle response without gaining cause, component, setup, or P19 authority |
| P35.4.1 - Canonical Telemetry Truth Closure | Verified locally | Source identity, tick clock, physical position, geometry provenance, typed blocker scope, and channel admission fail closed before any diagnosis or learned recurrence |
| P35.4.2 - Response-to-Mechanism Operational Integration | Verified locally; field evidence remains unearned | Qualified dynamic, repeated-disturbance, and ten-lap stint signatures refine P35 mechanism inspection without gaining support, cause, component, setup, or P19 authority |
| P35.5 - Field-Ready Alpha Hardening | Verified local release slice; field evidence remains unearned | One honest Next Gen oval alpha opens quickly, exposes one canonical move, packages as one owned desktop instance, and ships only after semantic real-file, dependency, contract, UI, and lifecycle gates pass |
| P36 - Prospective Investigation Evidence Campaigns | Planned; evidence collection remains data-locked | Qualified prospective campaigns produce the independent recurrence, controls, subgroups, and observable comparisons required before learned investigation ordering can earn promotion |

---

## P0 - Universal Telemetry Foundation

Nothing outranks P0 because every later conclusion depends on knowing what was
actually measured.

### Complete and verified

- [x] Decode every variable definition declared by the imported `.ibt` header.
- [x] Archive all declared raw sample columns instead of limiting storage to
  `HIGH_VALUE_RAW_CHANNELS`.
- [x] Keep calculated-channel work restricted to an intentional analysis subset.
- [x] Preserve scalar, array, and `count_as_time` sub-tick values.
- [x] Preserve both raw channel identity and additive canonical aliases.
- [x] Add canonical aliases for current high-value omissions:
  four brake-line pressures, tire odometers, steering torque, sub-tick steering
  torque, ABS state, nearby-car distance, surface material, driver marker,
  race/class position, pit/tow-service state, incident/pace state, tire-set usage,
  reset state, CPU/memory, and communication latency.
- [x] Add a machine-readable per-run telemetry capability manifest.
- [x] Add a stable file-schema fingerprint derived from the `.ibt` declaration.
- [x] Record raw name, canonical name, raw unit, type, offset, element count,
  sub-tick status, base rate, effective rate, and provenance.
- [x] Discover and label registry-unmapped channels without discarding them.
- [x] Record baseline channel health: cached state, null coverage, distinct-value
  count, constant/varying state, and observed numeric range.
- [x] Surface manifest health/provenance fields through the channel catalog.
- [x] Expose `GET /api/runs/{run_id}/telemetry-capabilities`.
- [x] Preserve column-pruned read paths so the larger archive does not make
  Compare load every channel.

### P0 verification evidence

- Real local Next Gen `.ibt`: 277 declared channels and 277 cached channels.
- `SteeringWheelTorque_ST`: six samples per 60 Hz record, preserved as a list
  with an effective 360 Hz rate.
- Real Atlanta import observed on 2026-08-03: 26,556 records, approximately
  4.0 seconds decode/normalization time, 539 intentional raw/canonical/calculated
  Parquet columns, and no redundant `raw__*` columns.
- Compare reads 94 decision-relevant columns rather than the full archive,
  including weather, tire-state, setup-context, and nearby-car evidence.
- Full Python suite passed with four environment-dependent skips.
- Ruff and `git diff --check` passed.
- Primary implementation:
  `racelab_engine/io/ibt_reader.py`,
  `racelab_engine/io/telemetry_manifest.py`,
  `racelab_engine/analysis/channel_registry.py`, and
  `racelab_engine/services/import_service.py`.

### Remaining P0 hardening

- [x] Add explicit canonical mapping kinds: exact alias, unit-converted alias,
  derived fallback, incompatible similarly named channel, and unknown.
- [x] Add car identity, iRacing car version, track configuration/version,
  iRacing build, and session type to the compatibility fingerprint.
- [x] Detect clipping, saturation, impossible ranges, timestamp discontinuities,
  dropped ticks, and malformed fixed-length arrays.
- [x] Add an import invariant that fails promotion if any declared channel lacks
  an archived sample column.
- [x] Add fixture coverage for mixed scalar/array/string/bitfield declarations,
  unknown future channels, malformed definitions, and schema changes.
- [x] Decide and document cache-version migration/re-import behavior for runs
  imported before the universal archive.
- [x] Add a compact UI capability summary; keep the full catalog intentional and
  out of Race Mode unless the driver asks for it.

### P0 architectural rule

**Archive everything. Calculate selectively. Display intentionally.**

---

## P1 - Evidence Eligibility

Every analysis must own a contract. Channel presence alone never establishes
that a conclusion is valid.

### Shared evidence vocabulary

- [x] Add typed evidence states to backend contracts and UI:
  `measured`, `calculated`, `estimated_proxy`, `observed_correlation`,
  `controlled_test_effect`, `unavailable`, `blocked_by_context`, and
  `needs_confirmation`.
- [x] Make proxy status structural data, not tooltip-only wording.
- [x] Require every conclusion to identify its evidence state and source channels.

### General eligibility gates

- [x] Validate complete flying-lap coverage.
- [x] Exclude out-laps, cooldowns, pit-road laps, wrecks, spins, cautions,
  slowdowns, invalid-speed laps, partial laps, and reset fragments.
- [x] Detect sample gaps, clock discontinuities, invalid rates, and simulator
  integrity problems.
- [x] Match car, track configuration, session context, weather range, fuel,
  tire age, and setup snapshot.
- [x] Score driver-input similarity and racing-line similarity.
- [x] Enforce one unrelated setup change per controlled comparison.
- [x] Add analysis-specific blockers and confidence caps.
- [x] Prevent short runs from supporting strong degradation or cooling claims.
- [x] Prevent missing telemetry from being converted to zero.

### Analysis contract framework

- [x] Define a reusable contract schema containing required channels, preferred
  channels, operating conditions, hard blockers, allowed outputs, forbidden
  outputs, minimum repetitions, and confidence rules.
- [x] Return blocker reasons and the exact measurement needed to unblock analysis.
- [x] Implement the first contract for relative high-speed resistance.
- [x] Forbid that contract from emitting measured CdA, exact drag force, or exact
  horsepower loss.

### Nearby-car context policy

- [x] Archive `CarDistAhead` and `CarDistBehind` and expose them as context.
- [x] Withhold causal setup attribution when nearby-car context is inside the
  configured 1.5 s ahead / 0.5 s behind windows or is unavailable, while
  preserving the lap and measured speed and never claiming an aerodynamic force.
- BLOCKED: draft detection/classification, clean-air certification, tow labels,
  and side-draft classification are removed from runtime/product decisions by
  `AGENTS.md`. Do not implement those labels unless the repository rule is
  explicitly changed. A safe evidence gate may say that nearby-car context is
  too uncertain for a resistance conclusion.

### P1 exit criteria

- [x] No implemented recommendation engine can bypass canonical eligibility.
- [x] Every blocked analysis explains why it is blocked.
- [x] Junk laps cannot drive setup recommendations in default operation.
- [x] Contract tests cover both allowed and prohibited outputs.

---

## P2 - Alignment and Time

The primary metric is time. Speed traces are supporting evidence.

### Engineering phase engine

- [x] Retain fixed percentage bins only for coarse navigation/storage.
- [x] Detect straight, lift, brake application, threshold braking, brake release,
  turn-in, entry, center, apex region, initial throttle, full-throttle exit,
  following-straight carry, transition, bump/curb, pit, and reset phases.
- [x] Use curvature, yaw rate, lateral acceleration, steering rate, brake
  application/release, throttle state/derivative, speed derivative, position,
  GPS line, shock motion, and vertical acceleration.
- [x] Make symptom interpretation phase-specific.
- [x] Prevent a single transient maximum from dominating a large coarse segment.

### Layered lap alignment

- [x] Compare future runs by physical track position, never sample index.
- [x] Implement primary lap-percentage/timing-boundary alignment.
- [x] Add GPS/track-coordinate geometric alignment.
- [x] Add yaw/heading curvature alignment.
- [x] Add road-profile alignment from shock deflection/velocity, ride height, and
  vertical acceleration.
- [x] Add local anchors for braking onset, apex curvature, and repeatable bumps.
- [x] Produce a local alignment-uncertainty map and prohibit extrapolation across
  missing coverage.

### Cumulative time delta

- [x] Integrate distance-aligned reciprocal-speed differences into cumulative
  time delta.
- [x] Report phase time, entry loss, center loss, exit gain, following-straight
  carry, gain persistence, gain origin, and surrender point.
- [x] Separate theoretical opportunity from repeatable opportunity.
- [x] Add synchronized overlays, cursor statistics, and honest missing-data gaps.

### Driver-specific noise floor

- [x] Learn same-setup variability by driver, car, track, setup, tire age, fuel
  range, weather range, run type, and phase.
- [x] Use paired lap differences, trimmed means, median phase effects, lap-level
  bootstrap intervals, A/B/A consistency, persistence, and contradiction scores.
- [x] Never treat thousands of 60 Hz rows as independent setup experiments.
- [x] Replace global display deadbands as the sole significance test.

### P2 exit criteria

- [x] Every engineering comparison includes local alignment confidence.
- [x] Time gains/losses are tied to physical location and phase.
- [x] Significance is based on lap/run repetition, not sample count.

---

## P3 - Engineering Systems

Each engine must be phase-aware, evidence-contract gated, aligned by track
position, and explicit about measured versus proxy outputs.

### 1. Driver input and racing-line efficiency

- [x] Measure line deviation, steering demand for achieved curvature,
  correction count, throttle commitment, brake release, coasting distance,
  minimum-speed position, and driver repeatability.
- [x] Block setup attribution when driver execution changed materially.

### 2. Braking efficiency and dynamic brake balance

- [x] Analyze four brake-line pressures, pedal/raw pedal, wheel speeds,
  longitudinal acceleration, yaw, steering, ABS intervention, tire state, and phase.
- [x] Derive pressure buildup/release, effective front/rear ratio, left/right
  balance, incipient-lock timing, ABS duration, and matched deceleration efficiency.
- [x] Separate setup brake-bias evidence from pedal-technique evidence.
- [x] Never label the efficiency proxy as a friction coefficient.

### 3. Corner balance and rotation

- [x] Calculate expected yaw from speed and geometric curvature.
- [x] Analyze sustained yaw error, sideslip proxies, steering efficiency,
  rotation response, correction demand, and phase-specific balance.
- [x] Build repeatable phase signatures instead of one-sample loose/tight labels.

### 4. Tire state and tire energy

- [x] Build a per-corner state vector from cold/running pressure, surface and
  carcass profiles, gradients, wear, tire distance, wheel slip, brake input,
  phase, and load context.
- [x] Classify pressure-driven heating, shoulder load, surface scrub, carcass
  heat, braking heat, traction heat, camber bias, aging, saturation, and falloff.
- [x] Require working history and repeated laps before pressure recommendations.
- [x] Never use a universal "middle hot means lower pressure" rule.

### 5. Damper and suspension response

- [x] Add shock-velocity/displacement histograms, recorded-sign split,
  low/high-speed regime occupancy, RMS/peaks, zero crossings, settle time,
  oscillation count, bump maps, cross-corner coherence, and PSD.
- [x] Gate damper recommendations by measured shaft-velocity regime occupancy.
- [x] Build a track-response fingerprint for bumps, alignment, and repeatability.
- [x] Never claim measured damper force without a force channel/model.

### 6. Aero-platform operating window

- [x] Analyze ride-height distributions by speed, percentiles, near-contact duty,
  front/rear response versus dynamic pressure, rake hysteresis, settling,
  steady/transient compression, lap consistency, and left/right asymmetry.
- [x] Evaluate speed/time gain against platform-risk and tech-risk countereffects.
- [x] Keep load/force outputs explicitly labeled as proxies.

### 7. Relative resistance and scrub diagnosis

- [x] Compare tightly matched speed, RPM, gear, throttle, steering/line proxy,
  weather, proximity context, tire state, and wind on a common position grid.
- [x] Add measured grade/elevation matching before ranking grade as a specific cause.
- [x] Separate platform/aero-related resistance, tire scrub, steering, wheel-speed
  mismatch, brake-drag suspicion, powertrain, grade/wind, proximity context,
  and unknown residual cause buckets.
- [x] Add a repeatable relative coastdown test mode with A/B/A confirmation.
- [x] Output equivalent road-load acceleration-residual ranges only under a valid contract.
- [x] Never output exact aerodynamic drag force or coefficient from `.ibt`.

### 8. Powertrain and gearing

- [x] Analyze RPM occupancy, near-redline occupancy/limiter evidence, shift loss,
  speed/RPM, acceleration by RPM bin, pull consistency, and gearing headroom.
- [x] Add explicit engine-temperature, fuel-mass, and gear-mismatch diagnostics.
- [x] Require repeatable context and report expected countereffects of gearing changes.

### 9. Stint, tire, and strategy intelligence

- [x] Add fuel prediction, fuel-normalized pace, tire-state history, stabilization,
  stint degradation, tire-set accounting, and repair context.
- [x] Add explicit tire-life curves and a production pit-window recommendation.
- [x] Connect short-run gains to long-run tire/thermal countereffects.
- [x] Require adequate clean, continuous stint length before degradation conclusions.

### 10. Simulator and data integrity

- [x] Validate frame rate, CPU/GPU, memory faults, communication latency/quality,
  clock skew, sample continuity, and dropped-tick patterns.
- [x] Attach a Sim Integrity Certificate to each controlled comparison.
- [x] Reduce or block confidence when simulator integrity could explain input changes.

### P3 exit criteria

- [x] Every implemented engine declares and enforces its contract.
- [x] Every evidence-bearing output names supporting and contradicting evidence.
- [x] No implemented engine silently turns a proxy into a measurement.

Verification evidence (2026-08-04): 113 focused P3 contract/API tests pass; the
expanded normalization/session suite passes 226 tests. Hostile
fixtures cover file-declared meter-unit grade sources, map identity, constant/bad
altitude, matched-position grade disagreement, sparse/implausible temperature and
fuel channels, absolute thermal trend, sustained pointwise gear mismatch, client
redline rejection, compound/set/per-corner tire resets, right-censored distance-based
wear curves, replicated tire sets, active-stint burn variability, current-session YAML
selection, server-derived race horizon, recent pit-rule state, latest fuel recency,
matched-position measured pit loss, and the damper endpoint runtime path. Production
pit advice is emitted only when every race prerequisite passes. Otherwise the report
returns a non-actionable fuel-exhaustion bound, exact blockers, and a measurement
mission; no strategy recommendation is exposed.

---

## P4 - Controlled Test Director

- [x] Define the baseline procedure, eligible warm-up, required flying laps,
  matched fuel/tire context, setup snapshot, target phase, and rollback state.
- [x] Generate one-hypothesis test cards using the smallest useful legal step.
- [x] Specify expected mechanism, success metrics, countereffects, and rollback rule.
- [x] Make A/B/A2 the default setup-development protocol:
  baseline A, one-change test B, restored baseline A2.
- [x] Score test quality from setup delta, context match, driver match, empirical
  noise, phase time, expected mechanism, countereffects, and replication.
- [x] Detect `DriverMarker` and create timestamped evidence bookmarks.
- [x] Detect `EnterExitReset`, group section attempts, and prevent reset attempts
  from becoming full laps.
- [x] Use Active Reset attempts as a repeatability laboratory.

### Measurement Missions

- [x] When evidence is insufficient, generate a concrete measurement mission
  instead of stopping at "inconclusive."
- [x] Mission output must include purpose, procedure, required laps/passes,
  controlled variables, target phase, acceptance thresholds, and stop rule.
- [x] Adapt missions to current repository policy: use conservative nearby-car
  exclusion/uncertainty gates, not draft or clean-air classification labels.

### P4 exit criteria

- [x] A driver can execute a complete A/B/A2 workflow from the app.
- [x] The app knows whether the requested test was actually performed correctly.

Production status: the server owns opportunity selection, setup identity and legal
option provenance, eligible lap cohorts, event linkage, context, driver match, and
simulator integrity. Persisted A/B/A2 stages are scored fail-closed. Dial-In exposes
the decision first and a reproducible Markdown test certificate with exact run,
setup, lap, effect, noise, guardrail, code/config, and learning-admission evidence.

---

## P5 - Crew-Chief Recommendation Engine

Every recommendation should be a complete Kaizen evidence packet.

- [x] Identify the primary opportunity by track position and phase.
- [x] Quantify repeatable observed time loss.
- [x] Resolve the complaint into canonical symptom vocabulary.
- [x] List supporting evidence and contradictory evidence.
- [x] Rank cause buckets but expose only one primary setup test by default.
- [x] Hold secondary alternatives back unless the primary test is blocked or fails.
- [x] Recommend one of the approximately 15 driver-changeable setup controls only.
- [x] Use the smallest supported increment and explain whether it is small,
  medium, or large for that control/car context.
- [x] Explain the expected mechanism in plain language.
- [x] State what the change may hurt and what must not change.
- [x] Define success metrics, rollback rule, and keep/undo/retest criteria.
- [x] Show confidence, evidence state, blockers, and confirmation needs.
- [x] Make Race Mode decision-first and Learning Mode explanatory.
- [x] Be comfortable returning: "No setup change is justified yet. Run this
  measurement mission."

### P5 exit criteria

- [x] No constructed packet contains multiple unrelated major changes.
- [x] Every constructed setup value links back to telemetry events and experiment context.
- [x] Every constructed claim is understandable without hidden notebook knowledge.

Production status: packet construction and public workflow routes use server-derived
opportunity, symptom, candidates, exact setup values, eligibility, context, driver,
and integrity evidence. A complaint/phase mismatch blocks the setup cause instead
of attaching a plausible but physically unrelated recommendation.

---

## P6 - Setup Response Memory

- [x] Persist a response graph linking context, exact setup delta, hypothesis,
  observed phase effects, countereffects, verdict, and confidence.
- [x] Key context by driver, car, track/configuration, car/track versions,
  weather, tire distance, fuel, run type, and package archetype.
- [x] Learn which controls matter, where they matter, strength, cost elsewhere,
  nonlinearity, interactions, and driver-specific response.
- [x] Separate qualifying, long-run, tire-saving, stability, and confidence objectives in the context key.
- [x] Invalidate learned confidence when iRacing physics/build identity changes by exact context-key isolation.
- [x] Record the observed legal and tech-passing setup envelope without inferring
  universal limits from a single setup.
- [x] Admit only controlled, eligible comparisons into durable memory.
- [x] Preserve contradictory experiments instead of hiding them.

### P6 exit criteria

- [x] Generic setup-guide priors cannot override stronger controlled local evidence.
- [x] Driver improvement cannot be learned as a chassis response.
- [x] Every memory edge can be traced back to source runs and evidence packets.

---

## P7 - Advanced Experimentation

P7 remains deferred until P0-P6 produce a sufficiently large, clean, labeled,
controlled response history.

- [x] Define the minimum dataset and validation threshold required to unlock DOE.
- [x] Add gated fractional-factorial test-plan generation.
- [x] Add deterministic response-surface and parameter-interaction feature generation.
- [x] Add deterministic sequential design-row selection.
- [x] Add uncertainty-aware parameter search.
- [x] Add multi-objective Pareto analysis for explicit supplied objectives and uncertainty.
- [x] Present multiple explicit objective profiles--including qualifying, long-run,
  driver-confidence, and highest-confidence compromise--rather than one universal
  "best setup."
- [x] Consider contextual Bayesian optimization only after deterministic evidence
  contracts and clean response memory are proven.

Activation status: **LOCKED**. The repository contains fail-closed deterministic
DOE, Pareto, response-surface, interaction, and uncertainty-aware contextual search
engines. The contextual Bayesian optimization ADR deliberately limits operation to
offline, deterministic, one-next-test proposals. No real controlled-response
dataset has satisfied the production unlock audit, so no production optimization
route is enabled and no fitted optimum is claimed.

---

## P8 - Unified Recommendation Intelligence

Dial-In must distinguish understanding the driver's words from proving the
physical mechanism. Static knowledge may propose a hypothesis, but only
server-qualified evidence may approve a controlled setup test.

### Implemented and verified

- [x] Separate telemetry capability from observed-mechanism evidence. Channel
  presence alone cannot make a candidate test-ready.
- [x] Require observed mechanism events to be eligible, tuning-valid,
  provenance-complete, blocker-free, and above the server-owned confidence gate.
- [x] Treat event source channels as provenance, not automatic mechanism proof.
  Mechanism flags now come from conservative event semantics; ambiguous channel
  bundles and broad intervals fail closed.
- [x] Expose structured evidence strength as `unavailable`, `capability_only`, or
  `observed_mechanism`, with readiness, source event IDs, and controlled-test need.
- [x] Remove list-position scoring from the verified workflow. Candidate order is
  based on inspectable event linkage, mechanism coverage, readiness,
  countereffect margin, blockers, and qualified personal response history.
- [x] Carry selected track zone, selected phase, objective, and driver priority
  from Dial-In into the server-owned opportunity and learning context.
- [x] Bind every verified candidate to its own eligible event IDs, required
  mechanism flags, exact setup control, selected lap/phase, and fully contained
  track window; broad or multi-control associations cannot silently authorize a
  narrower test.
- [x] Use qualified exact-context control-response models only inside the
  observed delta and absolute-control envelopes, exact target window, and exact
  surrounding setup fingerprint; suppress a generic direction when controlled
  personal history predicts the wrong sign beyond uncertainty.
- [x] Revalidate immutable A/B/A2 workflows at scoring time: source and A must
  match, B must contain exactly the planned one-control change, and A2 must
  restore A before any result can enter setup memory.
- [x] Freeze each stage's three-lap measurement cohort after two declared
  warm-up laps at attachment time; scoring cannot include warm-up transients or
  select a different eligible subset later. The five-lap block must be one
  consecutive fuel/tire/setup stint with immutable recording-time provenance.
- [x] Require at least three qualified within-baseline comparisons for the noise
  floor, preserve all six A/B/A2 lap-level effects, and fail closed when any
  non-target phase has partial alignment coverage.
- [x] Preserve each recommendation's physical trade-off and score control-owned
  telemetry guardrails: front/rear platform margin for ride height and springs,
  coolant/oil temperature for tape, limiter context for gearing, and absolute
  braking-yaw response for brake bias. Missing guardrail telemetry produces a
  retest; a measured failure produces an auditable rollback/undo result.
- [x] Persist and visibly restore decision context in Dial-In. If the selected
  zone, lap, phase, objective, or priority changes, stage attachment and scoring
  remain disabled until a new server-verified plan is built.
- [x] Turn long-run, tire-conservation, tire-life, and driver-confidence requests
  into purpose-sized measurement missions instead of certifying them from a
  generic three-lap sample.
- [x] Preserve the decision context, ranking basis, and score components in the
  reproducible controlled-test certificate.
- [x] Distinguish measurement missions, exploratory tests, and controlled-test
  supported fix recommendations in the product language.
- [x] Limit Learning Mode to three unverified hypotheses while Race Mode retains
  one server-verified next decision.

### Data-locked and future intelligence

- [ ] Calibrate evidence-strength scores against held-out real A/B/A2 outcomes.
  Until then every score remains explicitly ordinal, not a probability.
- [ ] Add formal competing-cause contradiction matrices and information-gain
  test selection after enough labeled mechanism outcomes exist.
- [x] Add producer-owned typed observed-mechanism roles plus qualified yaw,
  brake, RPM/gear, tire, and driver-correction event detectors. Unsupported
  actions still produce measurement missions instead of borrowing meaning from
  raw provenance channels.
- [ ] Add validated context-distance and hierarchical transfer models without
  allowing broad priors to override exact controlled local evidence.

### P8 exit criteria

- [x] Capability-only telemetry cannot authorize a setup test.
- [x] A driver-selected zone or phase cannot silently fall back to an unrelated
  opportunity; missing repeated evidence produces a measurement mission.
- [x] Qualified negative personal history can block a generic recommendation.
- [ ] Confidence calibration and information-gain selection remain intentionally
  open until real controlled datasets satisfy their validation contracts.

---

## P9 - Performance and responsiveness

Performance work must reduce waiting and memory pressure without weakening an
evidence contract, dropping a declared channel, changing a canonical API shape,
or turning an extrema/event-preserving trace into a visually convenient fiction.

### Implemented and verified

- [x] Keep the production `.ibt` overview path frame-native. Materialize only
  the explicit row evidence required by row-only detectors, retain the complete
  lossless archive as columns, and release duplicate decoded buffers early.
- [x] Compute scalar telemetry-manifest health with native column reductions.
  Preserve exact null, non-finite, impossible-range, clipping, saturation, and
  channel-health output parity with the row implementation.
- [x] Bound projected telemetry caching by file signature, lap, projection,
  entry count, per-entry bytes, and total bytes. Return mutation-safe rows and
  invalidate both data and schema caches on app-owned writes.
- [x] Avoid repeated schema/migration work on warm database opens, assemble run
  lists in one query, build overviews through one connection, and add targeted
  read-path indexes.
- [x] Replace whole-grid nearest-position scans with deterministic binary search
  while preserving lower-position and start/finish tie behavior. Reuse the
  already interpolated baseline frame during phase classification.
- [x] Keep track-map decoding and index reads cached without exposing mutable
  cached objects. Use allocation-light serialization and reuse the canonical
  cached platform-event result in the render package.
- [x] Keep canonical channel and track-map API payloads backward-compatible.
  Use explicit compact render projections only on app requests, retaining every
  selected channel extremum and telemetry-event anchor.
- [x] Split heavyweight cockpit surfaces into intent-preloaded chunks, unmount
  closed overlays and rails, isolate high-frequency cursor/playback updates,
  prevent zoom-only full-series rebuilds, and size ECharts before initialization.

### Verification evidence

- Real Atlanta `.ibt` (26,556 rows, 277 declared channels, 585 cached columns):
  direct import fell from 24.70-29.88 s to 4.66-5.59 s; overview analysis fell
  from 21.29-27.00 s to 2.93-3.83 s. The generated 277-channel manifest remained
  exactly equal, and peak working memory fell from about 1,150 MB to 518 MB.
- Native manifest health calculation measured 8.32 s to 0.60 s (13.82x), while
  end-to-end cache staging measured 7.21 s to 0.74 s.
- Representative trace output fell from 3,043 points / 509 KB to 437 points /
  79.6 KB. Warm endpoint median measured 22.88 ms, with extrema and event-anchor
  preservation covered by regressions.
- Synthetic 6,000-row, 1,001-position alignment median fell from 0.682 s to
  0.268 s. A 6,000-position nearest lookup fell from 1,944 ms to 1.34 ms.
- A 5,463-point track map serialized in 0.86 ms instead of 72.49 ms. The app map
  package is 619 KB instead of 1.52 MB, while the canonical map endpoint retains
  its full point contract; warm package median measured 40.55 ms.
- UI entry JavaScript fell from 307.63 KB to 218.49 KB (29.0%); gzip fell from
  88.05 KB to 67.61 KB (23.2%); launch artwork fell from 535.00 KB to 453.92 KB.
- Full Python regression, whole-repository Ruff, TypeScript, production build,
  browser smoke, exact manifest parity, randomized alignment parity, hostile
  partial-channel evidence, cache mutation, cache invalidation, and API contract
  checks passed. Four protected real-fixture checks remain environment-dependent.

---

## P10 - Evidence Integrity and Resilience

This phase was opened by the 2026-08-08 whole-product adversarial audit. It
targets failures that can certify invalid evidence, lose immutable experiment
history, attach old results to a new driver decision, or leave the local app
unresponsive. Valid canonical payloads remain backward-compatible; malformed or
incomplete evidence must fail closed and explain what is needed.

### P0 implementation queue

- [x] Validate every numeric context range used by the driver-noise and
  repeatability gate. NaN, infinity, malformed strings, sparse ranges, and
  inverted ranges must produce blockers instead of repeatability credit or an
  exception.
- [x] Preserve null semantics in the production vector calculation for platform
  compression. A missing dependency must remain unavailable and cannot create a
  platform event or recommendation.
- [x] Screen every controlled A/B/A2 cohort for complete nearby-car distance and
  player-speed context using the established asymmetric time-gap policy. Unknown
  or nearby context must block setup attribution and response-memory admission;
  it must not introduce draft or clean-air labels.
- [x] Preserve controlled-test workflows and certificates when the same run is
  re-imported. Updating a run must not trigger `ON DELETE CASCADE` data loss.
- [x] Key comparison UI results to the exact baseline/test run and lap request.
  Clear old results immediately and ignore late responses so evidence from one
  pair can never render under another pair.
- [x] Reject incomplete, non-finite, zero-width, reversed, or out-of-range track
  zones before overlay generation. No malformed request may create an
  unbounded loop or exhaust API workers.

### P1 implementation queue

- [x] Make explicit shock-reader lap, window, and phase selectors fail closed
  when their selector channels are absent. Never emit an exact click direction
  from an unfiltered archive or claim provenance from an absent channel.
- [x] Require pairwise damper velocity/time coverage before distribution math;
  disjoint sparse channels must return unavailable instead of dividing by zero.
- [x] Preserve a valid 0% start/finish target in notebook findings and test plans
  rather than replacing it with the legacy 55% default.
- [x] Load a session's run summaries in bounded bulk queries instead of opening
  one database connection per run, while preserving session order and response
  shape.
- [x] Preserve platform events at exactly 0% track position and make overlay
  acquisition failures visible rather than presenting missing evidence as a
  clear result.
- [x] Make telemetry, manifest, channel-catalog, and track-map caches mutation
  safe, byte bounded, and fresh across metadata-only or identical-size/time file
  replacement.
- [x] Admit full-lap timing endpoints only through a bounded circular boundary
  rule derived from observed sample spacing; interior gaps must remain blocked.
- [x] Prevent Dial-In and shock surfaces from publishing an exact setup target
  that lacks an observed adjacent legal option and tech-passing provenance.
- [x] Scope resumed controlled workflows to the current run and preserve the
  complete warm-up, measured-lap, rollback, and stop protocol after navigation.
- [x] Distinguish Platform loading, error, unavailable, and genuinely clear
  states; a failed request must never be worded as clean evidence.

### P10 verification evidence

- Hostile regressions cover non-finite and inverted context ranges, missing
  vector dependencies, nearby-car A/B/A2 context, exact run/lap response
  identity, malformed zones, disjoint damper clocks, valid 0% targets, stale
  cache replacement, bounded circular endpoints, and every loading/error/clear
  distinction named above.
- Re-import tests prove the complete controlled workflow remains byte-for-byte
  equivalent at the contract level, including stage identifiers and laps,
  execution history, reproduction inputs, quality state, learning, and
  certificate evidence, while stale import-owned segments are removed.
- Dial-In and Shock Reader publish an exact target only for a sourced,
  tech-passing adjacent option. Missing provenance, far-only sparse options,
  wrong-direction options, and client-supplied authorization all withhold the
  target, provenance, and action-bearing wording.
- Session summary assembly for 160 runs across nine repetitions improved from a
  frozen-HEAD median of 240.820 ms to 2.140 ms (about 112.5x) through the bounded
  bulk read while preserving session order and response shape.
- Final verification collected 1,499 Python tests: 1,495 passed and four
  protected real-fixture checks skipped because their external fixture was not
  present. Whole-repository Ruff, TypeScript, the production UI build, and
  `git diff --check` passed. The final UI entry was 222.69 KB (68.86 KB gzip);
  Laps, Platform, and Dial-In remained lazy chunks.
- In-app browser smoke exercised a locally imported two-run session, Laps and
  52-lap stint evidence, Platform, Setup, Dial-In, Race/Learning mode, and a run
  switch that remains in the selected workspace. The browser console was clean.
- Independent backend/integration and UI adversarial reviews returned CLEAR
  after the final unauthorized Shock target and run-switch workspace defects
  were fixed and replayed.

---

## P11 - Decision-First Desktop UX

This phase turns the verified engineering foundation into a cockpit that stays
fast, legible, and trustworthy at a 1280 x 720 desktop target. Race Mode keeps
the next decision prominent; Learning Mode reveals the supporting evidence
without changing the underlying authorization rules.

### Complete and verified

- [x] Rebuild the shell as a responsive two-tier context bar with an intentional
  session drawer, compact run identity, unclipped session details, and no
  document-level horizontal overflow at the target viewport.
- [x] Add an exact-identity controlled-test ribbon. It may resume only the
  selected server workflow, survives navigation and re-import, and never binds
  an unrelated run or session.
- [x] Compact the Race Mode Priority Rail only after a server-confirmed clear
  result. Loading, findings, unavailable evidence, and errors remain visible.
- [x] Give the event timeline explicit expanded/focused keyboard ownership,
  reset playback on evidence-scope changes, and isolate modal shortcuts so
  hidden playback cannot hijack page navigation.
- [x] Reduce the default Laps stint table to seven decision columns, keep the
  full engineering sheet behind a disclosure, preserve a sticky stint identity,
  and make every selection and detail action keyboard accessible.
- [x] Derive visible best-lap, stint, and falloff conclusions only from currently
  qualified useful laps. Legacy persisted junk laps are requalified on read and
  cannot remain a false session best or drive derived evidence.
- [x] Order Platform as decision, local recorded-sample trace, subsystem
  controls, then optional whole-lap context. Race Mode starts collapsed;
  Learning Mode starts expanded.
- [x] Present Setup as an axle-oriented four-corner workbench. Default to Diff
  only for a different, current-scope, non-stale baseline with a real snapshot;
  otherwise default to Current.
- [x] Make Dial-In advisory and progressive: quick symptom entry, optional
  refinement, one next-action card, exact legal-option authorization, persistent
  measurement protocol, and one active controlled test at a time with an
  explicit auditable abandon action.
- [x] Key async session, run, lap, workflow, comparison, Platform, and cache
  commits to exact request identity. Clear old state immediately and ignore late
  responses after navigation or mutation.
- [x] Fail closed across Overview, evidence cards, recommendations, Platform,
  and Setup. Unqualified or provenance-free evidence renders as `No call`,
  disables action links, and cannot preserve stale recommendation prose.

### P11 verification evidence

- Final verification collected 1,525 Python tests: 1,521 passed and four
  protected real-fixture checks skipped because their external fixture was not
  present. Whole-repository Ruff, TypeScript, the production UI build, and
  `git diff --check` passed.
- The final production UI kept major workspaces lazy: Setup was 19.45 KB (5.77
  KB gzip), Dial-In 35.93 KB (9.40 KB gzip), Laps 93.18 KB (24.11 KB gzip), and
  Platform 101.40 KB (29.36 KB gzip). The entry bundle was 230.42 KB (71.22 KB
  gzip).
- Live 1280 x 720 browser checks covered populated short and 54-lap runs, all
  five workspaces, both UI modes, compact and expanded rails, keyboard-only
  controls, modal focus trapping, run/session transitions, exact workflow
  abandonment, and stale-event replacement. The console remained clean.
- A hostile Bristol replay invalidated the stored 39.667-second cooldown-like
  lap before best-lap, stint, falloff, or Platform conclusions. A legacy
  Talladega replay removed provenance-free tuning actions and rendered `No
  call`, empty findings, and no next test.
- The independent integrated review and accessibility/responsive sub-audit both
  returned CLEAR with no remaining P0/P1 findings after 225 and 102 focused
  checks respectively.

---

## P12 - Internal Engineering Intelligence

This phase adds a deterministic local Smart Engineer above the existing evidence
and controlled-test authorities. It may organize evidence, compare causes,
select a producer-owned measurement, answer a fixed set of grounded questions,
and remember verified outcomes. It does not invent telemetry, probability, or
setup authority.

### Complete and verified

- [x] Build a typed evidence graph whose public claims, causes, controls, and
  citations bind to exact run, session, lap, event, channel, and setup identities.
- [x] Rank competing causes ordinally as leading, possible, ruled out, or
  unresolved. Do not present unsupported probabilities or hidden confidence
  arithmetic.
- [x] Select one evidence-qualified next step: an already-authorized controlled
  test, a producer-declared discriminator, a measurement mission, driver focus,
  or an explicit no-call with recovery blockers.
- [x] Keep exact setup values behind repository revalidation of the current
  source-A baseline, adjacent legal option, immutable provenance, complete
  protocol, and source-event relationship. B/A2, cross-run, ambiguous-workflow,
  and caller-attested paths fail closed.
- [x] Add immutable engineering memory for prediction contracts, outcome grades,
  controlled-test narrative, exact-context setup response, and presentation-only
  driver preferences. Memory cannot create evidence or setup authority.
- [x] Report calibration as observed protocol-valid direction counts with its
  sample size and caveat, never as a calibrated probability.
- [x] Answer the supported engineering questions only from the selected run and,
  when supplied, the exact selected lap. Every action-bearing answer requires the
  controlled card's complete qualified citation set.
- [x] Add a lazy Smart Engineer workspace. Race Mode leads with one short
  briefing and next step; Learning Mode adds competing causes, the compact/full
  evidence graph, context matches, calibration, narrative, and citation detail.
- [x] Make citations navigable to their exact lap, track position, event, and
  workspace while clearing answers and stale state whenever evidence scope
  changes.
- [x] Withhold malformed, mismatched, stale, cross-context, or untrusted derived
  rows and optional memory. Data-integrity faults remain visible as blockers but
  cannot expose action prose or take down the report.

### Data-locked follow-ons

- [ ] Calibrated probabilities remain locked until enough held-out, protocol-valid
  outcomes exist for honest validation.
- [ ] Formal information-gain and DOE selection remain locked behind their P7/P8
  dataset prerequisites. The current planner uses only producer-declared,
  evidence-qualified discriminators.
- [ ] Open-ended generative engineering answers remain locked. The current query
  surface is deterministic, fixed-intent, citation-bound, and locally auditable.

### P12 verification evidence

- Final verification collected 1,666 Python tests: 1,662 passed and four protected
  real-fixture checks skipped because their external fixture was not present.
  Whole-repository Ruff, TypeScript, the production UI build, and
  `git diff --check` passed.
- The production build kept Smart Engineer lazy at 26.04 KB (6.97 KB gzip); the
  entry bundle was 233.48 KB (72.09 KB gzip).
- Live 1280 x 720 browser checks covered populated Race and Learning reports,
  measurement-only fail-closed behavior, the UI's suggested grounded question,
  exact-lap response clearing, compact and full evidence graphs, exact citation
  navigation to Lap 14 at 12.5%, zero horizontal overflow, and a clean console.
- Independent release review returned CLEAR after 230 focused backend and 25
  frontend contract checks. It replayed the authorized source-A path and verified
  that B/A2, cross-run, malformed, missing-verifier, ambiguous-session, memory,
  and untrusted-prose paths remain blocked.

---

## P13 - Cross-Tab Decision Broadcasting

This phase makes every primary workspace state its decision, exact evidence
scope, authority, and next handoff before exposing deeper analysis. The shell
and tabs share one truth contract, while Race Mode stays concise and Learning
Mode adds the supporting explanation.

### Complete and verified

- [x] Give Overview, Laps, Platform, Setup, Dial-In, and Smart Engineer a shared
  first-card broadcast for status, exact scope, evidence readiness, authority,
  and the most useful next workspace.
- [x] Keep shell navigation signals consistent with each tab's fail-closed
  decision. Integrity warnings, unavailable capability, short runs, loading,
  and transport failures cannot appear green elsewhere in the app.
- [x] Bind every run, lap, lap-window, representative lap, track zone, event,
  setup snapshot, comparison, raw zoom, and damper response before publishing
  it or handing it to another workspace.
- [x] Make controlled workflows durable and unambiguous: one active workflow per
  scope, exact source/window identity, immutable plan and stage bindings,
  deterministic A/B/A2 cohorts, safe recovery, and cancellable blocked legacy
  records.
- [x] Separate an authorized source-run test plan from an unverified current-run
  stage candidate. Dial-In never relabels the plan with the candidate run's lap
  or window.
- [x] Clear stale zones, channels, setup keys, events, and answers whenever the
  new evidence identity cannot prove they still belong. A locationless event
  cannot inherit the previous event's track zone.
- [x] Bind telemetry manifests and normalized caches to their run, original
  source hash, and cache hash. Swapped, stripped, ambiguous, or pre-v4 artifacts
  fail closed with re-import guidance, including direct Shock Reader access.
- [x] Keep recovery singular and usable: one primary Platform retry, in-tab
  workflow-status retry, explicit workflow conflict resolution, readable status
  text, human Race Mode run labels, and exact IDs retained in audit metadata.

### P13 verification evidence

- Final verification collected 1,740 Python tests: 1,734 passed and six protected
  checks skipped. Four require external real fixtures; two local persisted-cache
  checks correctly require original `.ibt` re-import because their pre-v4
  artifacts lack immutable ownership.
- Whole-repository Ruff, TypeScript, the production UI build, and
  `git diff --check` passed. Major workspaces remain lazy: Overview 14.46 KB,
  Setup 24.23 KB, Smart Engineer 30.68 KB, Dial-In 53.70 KB, Laps 99.11 KB,
  and Platform 108.65 KB; the entry bundle is 242.52 KB (75.01 KB gzip).
- Live 1280 x 720 Race and Learning checks covered all six primary workspaces,
  aligned shell/tab states, exact Platform-to-Setup-to-Engineer and
  Laps-to-Platform-to-Engineer handoffs, zero document overflow, and a clean
  console.
- Hostile replay covered cross-run and cross-session responses, same-lap
  different-window workflows, multiple active workflows, packet/stage/cohort
  corruption, stale zones, malformed nested evidence, manifest swaps,
  same-schema cache swaps, direct parquet access, and CSV-to-Parquet rollback.
- Independent tab-content and final cross-tab adversarial reviews returned CLEAR
  with no remaining reproducible P0/P1 issue.

---

## P14 - Evidence Compounding and Adaptive Engineering

This phase makes the app smarter by compounding only qualified observations,
exact session history, recording health, and persisted workflow state. It may
route attention, coach measurement, and remember a contradicted hypothesis. It
does not turn observational correlation into a cause, probability, optimum, or
new setup authority.

### Complete and verified

- [x] Promote producer-owned brake, rotation, tire, damper, powertrain, and
  driver conclusions into typed observation-only mechanism evidence. Every
  cited sample must co-observe the required channels, repetition counts must
  equal distinct cited supporting laps, and untrusted producer prose cannot
  become a public action.
- [x] Detect repeatable same-setup opportunities at matched physical positions
  only when at least three eligible laps clear the empirical same-run noise
  floor. Keep the finding observational and separate from setup authorization.
- [x] Build robust same-setup anomaly envelopes and driver-repeatability
  coaching. Incomplete common coverage, reciprocal/bimodal cohorts, junk laps,
  and broad pointwise multiplicity fail closed instead of creating a fleet of
  false alerts.
- [x] Build an exact ordered-session engineering ledger. Pace changes require
  paired eligible laps, physical alignment, fuel, all four tire-distance
  channels, tire compound, air/track temperature, wind, racing-line median and
  tail limits, nearby-car exclusion, and an effect above paired-lap empirical
  noise. The ledger labels every change observation-only.
- [x] Track recurring and resolved event signatures only from actionable,
  positive-confidence, blocker-free evidence. A resolved claim additionally
  requires the next run to prove healthy observable coverage for every source
  channel.
- [x] Rebuild each controlled hypothesis lifecycle from immutable workflow,
  prediction, grade, stage, compatibility, source-run, and full source-setup
  identities. An exact Undo/invalid fingerprint becomes `do_not_repeat`; a
  changed source context remains a different hypothesis.
- [x] Rank typed measurement debt and one feasible next mission using producer
  requirements, current channel availability, blockers resolved, unresolved
  causes covered, required laps, acceptance checks, and stop rules. This is an
  inspectable deterministic utility order, not formal information gain.
- [x] Add a navigation-only next-trustworthy-move router, mission stage,
  controlled-test preflight, certified-result reminder, and typed recovery.
  Workflow-derived moves bind the exact workflow revision; setup-authorized
  moves additionally bind the exact control and complete source-event set.
- [x] Compare recording health against two exact compatible trusted prior runs.
  Coverage, range, variation, effective rate, missingness, dropout, constant,
  saturation, and range/rate changes may request re-import or a verification
  run, but can never diagnose a vehicle cause or authorize setup.
- [x] Add robust observational stint-state intelligence: continuous eligible
  segments, Theil-Sen pace drift, MAD/noise-guarded change points, measured
  fuel/tire/weather/driver covariates, right censoring, and hard boundaries for
  pit, refuel, reset, repair, caution, incident, and tow context. Tire or causal
  attribution requires repeated comparable sets and remains withheld otherwise.
- [x] Add a deterministic scoped question parser for run, lap, lap-window,
  phase, and setup-control entities. Ambiguous, reversed, missing, hyphenated,
  and out-of-scope requests clarify or withhold rather than silently widening.
- [x] Add Race/Learning smart cards for opportunity, mechanisms, driver focus,
  anomalies, session changes, lifecycle, telemetry health, measurement debt,
  preflight, and one next move. Structured questions lead generic suggestions;
  disclosure and explicit `Mark updates seen` memory are presentation-only.
- [x] Keep exact-context guarded counterfactual ranges inside observed legal
  response envelopes with immutable source observations. Do not publish an
  optimum, extrapolation, or universal response.

### Data-locked follow-ons

- [ ] Calibrate detector thresholds, alignment intervals, evidence scores, and
  prediction reliability against frozen held-out same-setup and controlled-test
  outcomes. Current empirical bands report their sample basis and remain
  descriptive, not probabilities.
- [ ] Add formal expected-information-gain selection only after producer-owned
  competing-cause outcomes can validate it out of sample. The current planner
  stays deterministic and blocker-aware.
- [ ] Add hierarchical or context-distance transfer only after leave-one-context-
  out validation proves it does not create negative transfer. Exact local
  controlled evidence must remain dominant.
- [ ] Keep multi-control DOE, response optimization, and Bayesian search locked
  until at least 30 controlled experiments, six observations per factor, three
  contexts, held-out score at least 0.65, contradiction at most 25%, and 100%
  traceability are all satisfied.

### P14 verification evidence

- Final verification collected 1,877 Python tests: 1,871 passed and six
  protected checks skipped. Whole-repository Ruff, TypeScript, the production
  UI build, and `git diff --check` passed.
- The production build keeps Smart Engineer lazy at 56.72 KB (14.14 KB gzip);
  the entry bundle is 249.47 KB (76.93 KB gzip).
- Focused hostile suites covered co-observed mechanism samples, false repetition,
  low-confidence/action-prose injection, multimodal anomalies, missing tire or
  racing-line context, unobservable resolved events, exact query windows,
  current-versus-previous session selection, workflow revision/control/event
  binding, explicit attention acknowledgement, recording-health lineage, and
  observational stint boundaries.
- Fresh-process 1280 x 720 Race and Learning browser checks had zero document
  overflow, zero unlabeled visible buttons, a visible 2 px keyboard focus ring,
  and a clean console. Legacy artifacts correctly showed recovery and retained
  no stale Smart Engineer briefing or action.
- Independent backend and UI adversarial reviews returned CLEAR after 228 and
  174 focused checks respectively; the stint/P3 slice passed 95 focused checks.

---

## P15 - Premium Race Engineering Experience

- [x] Rebuild launch, session selection, and import around a premium local race-
  engineering workflow. Session cards derive truthful single/mixed track and car
  context only from complete exact membership; duplicate names remain distinct
  visually and to assistive technology.
- [x] Make import progress stage-based and outcome-aware. Native and browser
  flows require a real persisted run plus verified cockpit load before claiming
  completion; saved-but-not-opened runs receive accurate, non-destructive
  recovery rather than a false re-import failure.
- [x] Establish a two-tier track/car/setup then run/lap/mode context hierarchy,
  labeled workspace rail, one visible page heading, unclipped decision signals,
  deliberate loading states, and a keyboard-visible skip path.
- [x] Give Overview, Laps, Platform, and Setup a consistent decision briefing:
  state, why, what next, exact scope, comparison context, evidence authority,
  and the shortest valid handoff. Learning Mode retains the deeper coaching and
  provenance trail without bloating Race Mode.
- [x] Turn Smart Engineer and Dial-In into a single mission flow with why-now
  context, typed recovery, evidence trail, A/B/A2 progress, exact run/lap
  bindings, preflight checks, done/stop/rollback guardrails, and one controlled
  next move. Shell readiness follows exact server report and workflow state.
- [x] Make every recovery state truthful and actionable. Workflow-catalog and
  Smart Engineer failures broadcast Checking/Unavailable instead of advisory
  authority, Platform errors have one primary retry, and session deletion shows
  an explicit nothing-was-deleted outcome.
- [x] Harden keyboard and stale-scope behavior. Escape atomically clears the
  full evidence cursor while preserving intended run/lap scope; delete
  confirmation focuses Keep and restores a stable neighboring target; stale
  event, zone, workflow, import, and session responses cannot relabel current
  context.
- [x] Verify compact and expanded layouts, reduced-motion behavior, visible
  focus, complete accessible names, and zero horizontal page overflow at the
  1280 x 720 desktop target.

### P15 verification evidence

- Final verification collected 1,904 Python tests: 1,898 passed and six
  protected real-fixture checks skipped. The suite passed in three bounded
  batches; whole-repository Ruff, TypeScript, the production UI build, and
  `git diff --check` passed.
- The final production entry is 264.21 KB (80.51 KB gzip). Smart Engineer stays
  lazy at 64.80 KB (16.53 KB gzip), Dial-In at 56.85 KB (15.16 KB gzip), and
  charting remains isolated from the entry path.
- Fresh-process 1280 x 720 Race and Learning checks covered launch, truthful
  session metadata, Overview, Smart Engineer recovery, and Dial-In. Document
  width remained 1280/1280, all six workspace signals were unclipped, visible
  buttons had complete names, the active workspace exposed one visible `h1`,
  and delete/Keep focus returned to the exact stable session control.
- An independent final adversarial review returned CLEAR after import,
  session-membership, shell readiness, navigation, stale-focus, accessibility,
  and responsive checks. The post-review readability/error polish also passed
  focused contracts, typecheck, live HMR inspection, and the final full suite.

---

## P16 - Premium Telemetry Visualization

- [x] Replace nested hard-edged chart boxes with one open telemetry-canvas
  language: subtle plot fields, restrained grids, signal-color hierarchy,
  readable metric strips, glass tooltips, and responsive Race/Learning layouts.
- [x] Rebuild the Laps pace trace with truthful lap-time, delta, and Rolling-5
  metric cues; separate fastest/selected states; explicit baseline/test/range
  layers; keyboard-selectable points; and honest line breaks across invalid,
  excluded, or missing stint laps.
- [x] Rebuild Platform whole-lap charts as open signal lanes with unsmoothed raw
  traces, visible units, severity/event markers, selected-location context,
  static premium zoom controls, exact-sample keyboard inspection, and a layered
  local trace. Proxy channels stay dashed and explicitly labeled in both views.
- [x] Upgrade run-to-run delta traces with physical-position axes, synchronized
  cursors, unit-aware tooltips, an explicit zero reference, target-zone wash,
  honest gaps, dashed proxy identity, container-aware resizing, and an
  accessible reset. Stale or cross-scope responses cannot replace the selected
  run/lap/channel/zone result.
- [x] Preserve mathematical and evidence truth: no smoothing, no null-to-zero,
  no false continuity, no proxy-as-measured styling, and no duplicated overlay
  counts. Reduced-motion, focus, accessible names, and 1280 x 720 overflow were
  verified.

### P16 verification evidence

- 88 focused chart/trace contracts and 227 broad frontend, chart-visibility,
  stint, and performance contracts passed. Whole-repository Ruff, TypeScript,
  the production Vite build, and `git diff --check` passed.
- Live 1280 x 720 Race and Learning checks verified the pace surface, honest
  junk-lap gaps, active-metric best markers, complete scope counts, zero page
  overflow, zero clipped chart stats, zero unnamed visible buttons, and visible
  keyboard point focus.
- The production entry remains 264.21 KB (80.51 KB gzip); charting remains in
  its isolated lazy chunk. An independent adversarial chart review returned
  CLEAR after proxy, unit, gap, stale-response, metric-marker, count, keyboard,
  reduced-motion, and responsive replays.

---

## P17 - Oval Driver Operating System

- [x] Reframe the first five minutes around an oval driver's actual questions:
  how many laps are clean, what is the longest uninterrupted block, what is the
  best clean pace, where in the corner is the priority, and what should be
  verified next. Run and session surfaces keep track temperature, setup tech
  state, and exact run identity visible without adding another workspace.
- [x] Add an observation-only Laps run brief that separates best three/five-lap
  speed from qualified 20-60-lap race-run pace, withholds estimates below the
  gate, names excluded-lap categories, and distinguishes observed balance drift
  from tire or setup causality.
- [x] Add RF/RR readiness that requires at least ten uninterrupted canonically
  eligible laps plus an explicit producer-owned corner trend. Missing, invalid,
  excluded, or nonconsecutive laps break the chain; short or split runs never
  become tire, falloff, or best-long-run conclusions.
- [x] Add a run-owned Setup-at-a-glance surface for oval anchors: cross weight,
  nose weight, brake bias, grille tape, RF/RR cold pressure, rear gear, and
  steering ratio. The one-change audit verifies known matching car/track scope
  and remains non-authoritative until Dial-In revalidates the full plan.
- [x] Add an evidence-bound crew board for entry, center, exit, and straightaway
  carry, plus an exact-sample Platform checkpoint for brake, steering,
  throttle, and speed. Only typed producer phases are named; proxy resistance or
  scrub observations remain visibly proxy and never become measured aero.
- [x] Make the whole-car comparison workbook reachable from Laps without
  expanding the six-tab navigation. Lead with clean-lap pace, matched location,
  driver repeatability, RF readiness, and one-change discipline; independently
  bind both comparison and insight responses to exact runs, laps, and zone.
- [x] Preserve continuity everywhere: missing lap numbers reset Rolling-5,
  split timing buckets and chart lines, block full-stint verdicts, and cannot be
  pooled into 10/20-lap readiness. The browser gate mirrors the complete
  canonical invalid-lap taxonomy rather than trusting `is_useful` alone.
- [x] Project conventional oval turn anchors from the imported centerline and
  section geometry. Every current oval map exposes correctly ordered T1-T4
  labels at the corner centers, except Pocono's truthful T1-T3 layout; road and
  roval maps never inherit oval labels, and tri-oval frontstretch bends cannot
  become fictitious Turn 5-7 markers.
- [x] Give maps and Smart Engineer one vendor-neutral physical-region contract.
  Every oval turn has a bounded start/end area plus entry, center, and exit;
  grounded citations carry the same region identity and cannot invent a turn
  when no qualified physical-position evidence exists.

### P17 verification evidence

- 1,947 tests were collected: 1,941 passed and six protected-fixture checks
  skipped. Focused oval, stint-continuity, comparison-scope, shell, and
  responsive contracts passed after hostile missing-lap, junk-tag, stale-result,
  split-bucket, and proxy replays.
- Whole-repository Ruff, TypeScript, the production Vite build, and
  `git diff --check` passed. Compare remains a lazy Laps workbook rather than
  increasing initial shell weight or navigation complexity.
- Live 1280 x 720 Race and Learning checks verified clean-lap and 10-lap shell
  readiness, 20-lap race-run withholding, RF/RR and balance states, setup
  anchors, the whole-car workbook, zero page overflow, and zero unnamed visible
  buttons. A final independent continuity and authority review returned CLEAR.
- The 82-map canonical coverage audit verified all 43 oval layouts with finite,
  sequential geometry anchors and zero violations. Pocono and Talladega hostile
  regressions and the complete 2,232-test collection passed (2,227 passed, five
  protected skips), plus changed-file Ruff, TypeScript, the 2,190-module build,
  diff integrity, and a live Atlanta overlay inspection. Turn labels scale with
  the map, sit outward from the racing surface, and use leader lines so they stay
  legible without covering the track.
- The hardened audit verified 171 bounded turn regions: every turn anchor resolves
  to the center of its own region, with 155 section-geometry regions and 16
  centerline-geometry fallbacks. All 82 local canonical caches were migrated to
  the neutral `track_map_v2` tag, and both cached JSON and public packages contain
  no vendor naming. Smart Engineer citation-region and UI presentation contracts,
  all 2,233 tests (2,228 passed, five protected skips), targeted Ruff, TypeScript,
  the 2,190-module production build, and diff integrity passed.

---

## P18 - Deterministic Reasoning and Controlled Learning

- [x] Rank causes by independent evidence units rather than raw event count.
  Repeated eligible-lap observations can strengthen a cause, same-lap correlated
  events cannot vote twice, and an exact protocol-valid controlled contradiction
  outranks an observational count contest.
- [x] Admit verified A/B/A2 outcomes into current reasoning without conflating
  diagnosis with control acceptability. A target effect may support the mechanism
  while a countereffect still produces Undo and blocks that exact setup policy;
  inconclusive or invalid execution never becomes contradiction or support.
- [x] Bind learned outcomes and do-not-repeat policy to canonical context,
  material setup, physical track window, symptom, cause, control, direction,
  metric, phase, and countereffect contract. Presentation wording, event IDs,
  source-run churn, case, whitespace, and numeric representation cannot evade a
  prior Undo; a materially different setup or corner remains independently testable.
- [x] Enforce semantic repeat policy before every exact-target surface: direct
  packet planning, workflow creation, public projection, Stage B attachment,
  scoring, and report authority. Valid scored history remains visible and
  certificate-auditable while future unchanged failed plans remain blocked.
- [x] Replace self-asserted measurement ranking with an inspectable planner that
  validates blocker ownership, event/cause provenance, channel readiness, health
  lineage, and honest additional-lap cost. Integrity recovery outranks lap
  qualification, affected-channel recovery, repetition, and discrimination.
- [x] Publish typed mind-change criteria with the exact metric, evidence scope,
  threshold provenance, required independent laps or A/B/A2 stages, stop rule,
  countereffect, and deterministic next state. Collection guidance cannot invent
  causal falsification authority.
- [x] Make grounded questions exact and fail-closed across run, single-lap,
  lap-window, phase, and control scope. Missing representative laps, competing or
  shorthand lap scopes, out-of-scope history, and mismatched navigation request
  clarification instead of silently broadening or narrowing the answer.
- [x] Use one setup-authority projection across the API, Engineer, shell ribbon,
  and Dial-In. The exact control, values, three-step protocol, qualified event set,
  workflow revision, Stage B preflight, and current artifact generation must all
  agree; blocked, malformed, stale, or free-form query payloads expose only safe
  recovery and never stored setup prose.
- [ ] Collect held-out controlled outcomes before activating calibrated
  probabilities, formal information gain, hierarchical context transfer, or
  multi-control optimization. Deterministic evidence tiers remain authoritative
  until the existing P7/P8/P14 unlock criteria are truly met.

### P18 verification evidence

- 2,063 tests were collected: 2,057 passed and six protected-fixture checks
  skipped. Focused reasoning, query, planner, workflow-policy, public-authority,
  Engineer, ribbon, and Dial-In hostile regressions passed after independent
  evidence, countereffect-only Undo, semantic-policy churn, competing lap scope,
  stale artifact, and appended Stage B command replays.
- Whole-repository Ruff, TypeScript, the production Vite build, and
  `git diff --check` passed. The production build transformed 2,188 modules;
  Smart Engineer remains lazy-loaded and no new probabilistic authority was added.
- Independent backend, UI-authority, and final cross-boundary adversarial audits
  returned CLEAR with no remaining reproducible P0/P1 intelligence blocker.

---

## P19 - Engineering Truth, Experiments, and Durable Memory

- [x] Publish one canonical reasoning snapshot that separates mechanism truth,
  setup-control response, and policy acceptability. Public cause rankings and the
  evidence graph now derive from the same backend-owned snapshot; the API adapter
  no longer synthesizes cause nodes or causal edges.
- [x] Represent signed support and contradiction with explicit evidence nodes,
  observation nodes, cause nodes, and independence clusters. Same-run correlated
  evidence cannot inflate causal authority, and observational contradiction cannot
  rule out a mechanism without a protocol-valid mechanism-diagnostic control.
- [x] Build per-lap engineering context for eligible laps with explicit continuous,
  pit-snapshot, constant, missing, and unhealthy channel semantics. Next Gen raw
  carcass-temperature aliases now have vectorized/row parity; constant wear and
  carcass values remain snapshots rather than false live trends, and uncorrected
  rear wheel-speed mismatch remains a geometry-contaminated proxy.
- [x] Bind measurement and discriminator plans to immutable mission contracts,
  resource feasibility, supplied exact-contract attempt history, typed outcomes,
  and a deterministic stop-testing rule. Every stop decision retains the immutable
  contract that triggered it, and stale attempts cannot satisfy a changed mission.
- [x] Persist and reload immutable measurement attempts in the runtime planner.
  Completed-clean, no-signal, integrity-failure, infeasible, and abandoned outcomes
  are append-only, exact-contract records; restarted planning reconstructs durable
  `stop_testing`, while stale attempts cannot satisfy a changed contract.
- [x] Make session-event lifecycle tolerant to small physical-window jitter and
  preserve new, recurring, and resolved events. Session-position comparison now
  returns typed comparability debt instead of collapsing every mismatch into an
  empty result.
- [x] Revalidate exact-context Keep/Undo policy across each readable saved and archived
  session. A prior Undo blocks only the identical material policy contract; changed
  setup, context, corner, or measurement scope remains independently testable.
- [x] Fail closed when a saved session cannot be revalidated during durable Undo
  lookup. Typed `history_incomplete` debt identifies the affected session and
  recovery; only an explicit operator quarantine acknowledges unavailable history,
  and readable session Undo records continue to block unchanged policy.
- [ ] Collect held-out controlled histories before activating calibrated
  probability, formal information gain, hierarchy transfer, or multi-control
  optimization. This phase adds no new statistical setup authority.

### P19 verification evidence

- The complete 2,073-test Python collection passed with six protected-fixture
  skips. Focused reasoning, internal-report, run-API, session-lifecycle,
  Next Gen lap-context, mission-contract, and canonical-snapshot regressions passed.
- Whole-repository Ruff, TypeScript, the production Vite build, and
  `git diff --check` passed. The production build transformed 2,188 modules.
- Verification covers test-only event discovery, tolerant physical-window matches,
  stale-attempt isolation, exact-contract stop testing, backend graph ownership,
  evidence-cluster deduplication, observational contradiction limits, vectorized
  carcass aliases, pit-snapshot tire semantics, and geometry-contaminated wheel-speed
  authority. Junk laps remain excluded and statistical activation remains locked.
- Durable lifecycle regressions cover restart-safe exact-contract attempt reload and
  stop reconstruction, immutable stop-contract provenance, corrupted saved-session
  debt, explicit quarantine, and fail-closed repeat-policy authority.

---

## P20 - Engineering State Awareness and Whole-Car Mechanism Fusion

Overall status: **Verified deterministic production slice; shadow observers and
statistical activation remain data locked**. State awareness extends P19 without
creating another reasoning, setup, or policy authority.

- [x] Define immutable, extra-forbid `ChannelRole`, `DerivedMetricContract`,
  `EngineeringStateFrame`, `StateTransition`, `MechanismEpisode`, and
  independently blocked `TrustBudget` contracts. State awareness is structurally
  observation-only and cannot carry setup targets, cause rank, Keep/Undo, or
  intervention authority.
- [x] Complete the read-only existing-producer map. Six mechanism families have a
  direct producer-owned typed P19 path; platform response, resistance/scrub-like,
  stint trend, and sim integrity retain explicit Slice B fusion debt rather than
  fabricated findings.
- [x] Give all ten existing mechanism families one exact-scope, producer-owned path
  into canonical P19 reasoning while preserving independent blockers and distinct
  same-kind physical windows.
- [x] Add material control-context boundaries, requested-versus-applied semantics,
  FFB comparability, weight/power/build compatibility, and source-backed vehicle
  engineering profiles without guessing missing geometry.
- [x] Add descriptive steering-to-yaw transient response and preserved 360 Hz
  steering workload metrics under explicit proxy/forbidden-claim contracts. Exact
  FFB, steering conversion, physical-position, speed, driver, and clock context is
  mandatory for comparison.
- [x] Add descriptive chassis, tire, brake, combined-acceleration, and disturbance
  exposure metrics under explicit proxy/forbidden-claim contracts.
- [x] Build temporal state transitions, observation-only mechanism episodes, and a
  state-drift ledger, then feed their evidence into P19 without adding another
  cause ranker or setup-policy evaluator.
- [x] Publish one stale-safe engineering-awareness projection and integrate it into
  existing workspaces without adding cockpit startup work or a new top-level tab.
- [x] Keep probabilistic authority, formal information gain, Bayesian optimization,
  and multi-control automatic optimization data locked.

### P20 verification evidence

- Slice A: 15 hostile contract tests pass. They cover unknown channel roles,
  derived-metric authority ceilings, cross-run/setup/lap evidence rejection,
  material-control mutation boundaries, complete channel semantics/coverage,
  temporal-only relationship vocabulary, observation-only episodes, independence
  cluster accounting, separate trust axes, frozen models, and extra-field denial.
- Focused Ruff passes for the Slice A contracts and hostile tests. The producer
  audit records current canonical ownership, direct-path coverage, fusion debt,
  and the one-projected-read performance boundary. No telemetry formula, API, UI,
  reasoning ranker, or setup authority changed in this slice.
- Slice B: all ten existing mechanism families preserve explicit producer/artifact
  identity, source run/setup scope, sample coverage, and exact citations. Platform,
  stint, and integrity now use the shared single projected read; controlled
  resistance requires three distinct server-verified stage scopes. Hostile tests
  retain two same-kind physical windows, dedupe only an exact artifact identity,
  keep per-producer blockers independent, strip setup prose, and prove a qualified
  resistance artifact reaches P19 with observation-only authority.
- The real 26,556-row Atlanta Next Gen fixture produced explicit artifacts for all
  ten mechanism families from one observation build (28 distinct producer/artifact
  identities). Only platform and simulator-integrity evidence qualified in that
  file; every other family remained visibly blocked instead of inheriting another
  producer's success.
- Slice C: raw/processed controls remain separate; applied brake-bias changes split
  context; pit requests require independent service confirmation; any material FFB
  mismatch blocks steering-effort comparison; and weight, power, car, track, tire,
  repair, or build mismatches preserve observations while blocking causal setup and
  powertrain attribution. Twelve hostile tests plus 151 surrounding normalization,
  parity, manifest, and real-fixture checks passed.
- The Atlanta fixture materialized every actually declared context alias with
  vectorized/row parity. Its six available FFB configuration fields form a limited
  fingerprint because `SteeringWheelFFBEnabled` is absent; steering workload
  comparison therefore remains blocked. The identity-only vehicle profile pins
  exact car/build provenance while leaving all unproven geometry and conventions
  missing.
- Slice D: eight hostile tests cover frame/row parity, exact temporal response,
  junk-lap and applied-mutation blocking, preserved 360 Hz torque samples, missing
  sub-tick data, invalid phases, FFB mismatch, limited fingerprints, proxy-only
  comparison, and structural denial of setup authority. On the real Atlanta lap 4,
  detector-owned phase windows produced ready transient descriptors and 360 Hz
  workload artifacts; workload comparison stayed blocked because the FFB-enabled
  state is absent.
- Slice E: nine hostile tests cover force/grip/thermal overclaim denial, junk-lap
  blocking, straight-versus-corner geometry gates, source-profile binding,
  pressure-velocity rather than brake-energy semantics, constant/snapshot tire
  exclusion, raw acceleration caveats, row/frame parity, and repeated exact-position
  disturbance identity. Focused Ruff and model compilation pass.
- On the 26,556-row Atlanta **schema/capability** fixture, executable-path checks
  produced descriptive artifacts while the identity-only profile correctly
  blocked corner slip correction and damper-band classification. This is evidence
  for channel/update-semantic gates and exact scope only, not validation of chassis,
  tire, powertrain, platform, or other performance physics. The repeated-position
  signature also states that track input was not directly measured.
- Slice F: nine hostile tests prove exact frame binding, missing-channel and setup
  denial, noncausal transition vocabulary, conservative independence clustering,
  deterministic non-probabilistic signatures, P19 graph/snapshot ingestion, and
  persistent above-noise clean-stint drift gates. The surrounding P20/P19 focused
  checkpoint passed 250 tests with Ruff clean.
- The Atlanta schema/capability fixture produced 12 exact state frames and no
  temporal episode, which is the correct no-finding result because no qualified
  producer evidence repeated at one exact context. The combined existing
  observation plus awareness build was about 6.0 seconds cold and warm. It remains
  lazy and is not a cockpit-startup dependency; Slice G owns bounded caching.
- Slice G: the immutable public projection binds exact run, P19 snapshot SHA,
  state revision, profile hash, authority, producer artifacts, and analyzer/schema
  versions. All ten subsystem states remain independently fail-closed; setup
  leverage contains only P19-owned controls; mechanism, control response, and
  policy remain separate. The route carries no raw trace and uses an eight-entry
  identity-invalidated cache.
- Overview, Laps, Platform, Setup, Compare, and Smart Engineer now consume the
  same backend projection with request-sequence and exact-run stale guards and
  canonical `focusEvidence` navigation. No top-level tab or cockpit-startup
  dependency was added. The real Atlanta schema/capability projection measured
  about 29 ms cold and under 1 ms warm in a fresh process; its lack of episodes
  and drift findings stayed explicit debt, not fabricated physics.
- Slice H remains intentionally unimplemented for production. Body-sideslip,
  bank/gravity compensation, and geometry-corrected wheel observers are shadow/data
  locked until source-backed constants and held-out validation exist.

---

## P21 - Evidence Lab, Calibration, and Shadow Intelligence

Overall status: **Verified scientific infrastructure; advanced statistical
authority remains locked**. P21 can measure evidence readiness and evaluate
offline/shadow candidates, but P19 remains the sole production reasoning and
setup-policy authority and P20 remains the sole whole-car projection.

- [x] Audit every data-locked capability against its current authority, required
  dataset, independence unit, ground truth, held-out test, activation threshold,
  archive inventory, and remaining deficit.
- [x] Add content-addressed immutable dataset, manifest, unit, artifact,
  qualification, and split-policy records with fail-closed source, workflow,
  lineage, stage, and pseudoreplication leakage detection.
- [x] Freeze reproducible evaluation artifacts against code, dataset, split,
  configuration, vehicle-profile, metric, threshold, subgroup, and negative-control
  identity.
- [x] Add append-only evidence campaigns for driver noise, controlled A/B/A2
  response, tire semantics, long runs, vehicle geometry, control workload, and
  null/no-change behavior.
- [x] Define bounded proxy-validation contracts and exact car/build field-level
  vehicle-profile validation without treating snapshot channels or identity-only
  profiles as dynamic/empirical truth.
- [x] Add non-authoritative prospective shadow contracts, frozen predictions,
  later outcomes, calibration metrics, change-point candidates, response-model
  scoring, negative-transfer tests, controlled-effect evaluation, and deterministic
  planner comparison.
- [x] Add identity-bound activation gates with pre-registered thresholds, subgroup
  and prospective requirements, maximum authority ceilings, and no client/manual
  override.
- [x] Publish exact-scope Learning Readiness in Smart Engineer Learning Mode only,
  including fail-closed recovery screens, while leaving Race Mode free of
  calibration clutter.
- [x] Keep probability, formal information gain, sideslip/gravity/geometry
  observers, response authority, Bayesian optimization, and multi-control
  optimization locked until qualified real and prospective evidence passes every
  gate.

### P21 verification evidence

- The read-only archive inventory found 13 runs across three saved sessions, 626
  laps, 602 complete laps, and 506 existing useful markers, but zero protocol-valid
  controlled workflows or frozen prospective predictions. Those counts remain
  inventory, not qualified evidence.
- Fifty-four focused P21 regressions passed before final semantic closure; the
  added causal/planner/semantic group passed 20 focused tests. Hostile coverage
  includes duplicate source files, adjacent-window pseudoreplication, A/B/A2 split
  leakage, synthetic activation denial, snapshot/live-trend mismatch, FFB mismatch,
  failed restoration, mechanism/policy separation, planner authority violations,
  false stops, gate identity, and client override denial.
- The full Python suite passed 2,182 tests with six protected fixture-dependent
  skips. Whole-repository Ruff, TypeScript, the 2,189-module production Vite build,
  and diff integrity passed.
- Learning Readiness measured 18.051 ms cold and 15.735 ms mean warm against a
  fresh temporary database. It reads metadata and registries only and is not a
  cockpit-startup dependency.
- Live local browser smoke showed exact zero-qualified-evidence deficits,
  `Advanced models: Shadow only`, P19/P20 production authority, and missing vehicle
  geometry in Learning Mode. Race Mode contained zero Learning Readiness headings,
  and the browser console remained clear.
- Synthetic data validated mechanics and failure handling only. P21 did not claim
  real proxy accuracy, causal response, calibration, transfer, or statistical
  setup authority. The detailed contract is in `docs/p21_evidence_lab.md`.

---

## P22 - Prospective Field Validation and Learning Operations

Overall status: **Verified operational foundation; real campaigns and advanced
authority remain data-locked**. P22 makes P21 evidence campaigns executable and
prospective while P19 retains all production reasoning, measurement, setup,
Keep/Undo, and stop-testing authority and P20 retains whole-car projection.

- [x] Add content-addressed campaign operations with frozen run/context identity
  and append-only, restart-safe start, pause, resume, complete, and abandon
  lifecycles that reject invalid direct transitions.
- [x] Qualify successful `.ibt` imports automatically using canonical eligible
  laps, exact source/car/build/setup identity, fuel/weather/traffic bands, control
  mutation checks, immutable independence units, and per-lap rejection reasons.
- [x] Promote only protocol-sufficient driver-noise and uninterrupted long-run
  assessments automatically; keep controlled setup, tire semantics, geometry,
  control-workload, and null campaigns pending their required workflow or source
  validation record.
- [x] Freeze exact P19 controlled-test predictions before outcome exposure and
  attach one immutable canonical A/B/A2 outcome later with mechanism, control
  response, countereffect, and policy kept separate.
- [x] Rank feasible evidence acquisition with an inspectable deterministic
  deficit/rule-fit/gates/lap-cost heuristic that is structurally collection-only,
  not formal information gain or setup authority.
- [x] Review every advanced capability against cloned pre-registered P22 field
  gates without manual selection or a preselected model; limited activation is
  only eligibility for a later bounded observer review.
- [x] Publish active test-session progress, exact rejection feedback, frozen
  prospective state, Learning Ledger categories, and remain-locked capability
  review in Smart Engineer Learning Mode only.
- [x] Keep formal information gain, probability authority, sideslip/gravity/
  geometry observers, response authority, Bayesian optimization, and
  multi-control optimization locked until qualified real and prospective data
  passes every exact gate.

### P22 verification evidence

- The complete Python collection contains 2,201 tests. The full suite passed with
  six protected fixture-dependent skips; 20 focused P21/P22 lifecycle,
  qualification, prediction, outcome, UI-contract, and activation regressions
  passed again after final lifecycle hardening.
- Hostile coverage includes duplicate source assessment, contaminated traffic,
  brake-bias mutation, invalid/equal-timestamp lifecycle events, hindsight
  freezing, immutable prediction collision, one-to-one outcome matching,
  mechanism-supported plus Undo separation, no-model preselection, and planner/
  optimizer authority denial.
- Whole-repository Ruff, TypeScript, the 2,189-module production Vite build, and
  diff integrity passed.
- Live local browser smoke against the existing 13-run archive showed no feasible
  campaign from an unreadable legacy recording, zero qualified campaign progress,
  the Proven/In validation/Locked ledger, `Decision: REMAIN LOCKED`, and no browser
  console errors. Race Mode contained zero P22 test-session or ledger content.
- No real campaign, proxy validation, controlled response population, or model
  activation was claimed. The next limiting reagent is qualified Next Gen field
  data collected under the frozen operations. The detailed contract is in
  `docs/p22_field_validation.md`.

---

## P23 - First Earned Adaptive Capability

Overall status: **NO ACTIVATION EARNED**. This is the scientific result, not a
missing implementation. The complete archive is inventory only and contains no
qualified population that can pass an activation gate.

- [x] Audit and rank every P21/P22 candidate before selecting one, including
  workload/transient descriptors, geometry/gravity/sideslip observers,
  change-point/response/calibration/transfer methods, information gain, and both
  optimizers.
- [x] Select the existing steering-workload descriptor as the lowest-risk useful
  candidate because it has a deterministic 360 Hz formula, exact FFB context,
  strong null/block controls, no geometry dependency, and an observation-only
  authority ceiling.
- [x] Freeze and persist content-addressed protocol
  `p23p-7039505728f07034d6f5` with whole-session independence, exact context,
  exclusions, metrics, thresholds, subgroups, negative controls, prospective
  boundary, drift rules, and authority bans.
- [x] Reject aggregate or architectural success as activation evidence and
  publish `NO ACTIVATION EARNED` through Learning Mode while preserving P19/P20
  authority and leaving Race Mode uncluttered.
- [ ] Collect 9 qualified historical exact-FFB sessions and 90 clean laps across
  short, intermediate, and superspeedway contexts.
- [ ] Pass the frozen historical held-out metrics, all 8 real negative controls,
  all 9 required subgroup reports, and exact build/profile checks.
- [ ] After historical passage, collect and grade 10 new immutable prospective
  source sessions with predictions frozen before outcomes.
- [ ] Consider a limited observation-overlay activation only if every unchanged
  gate passes; setup values, probabilities, cause rank, planning, and Keep/Undo
  remain forbidden.

### P23 verification evidence

- The read-only activation audit found zero qualified datasets, campaign
  attempts, evaluation artifacts, prospective outcomes, profile validations, or
  activation decisions. Thirteen archived runs across three saved sessions do
  not count as qualified evidence.
- Twenty-six focused P21/P22/P23 regressions passed during implementation.
  Hostile coverage includes protocol mutation, invalid aggregate activation,
  source-session independence, prospective boundary, synthetic exclusion,
  subgroup/control completeness, context drift, and P19/P20 authority isolation.
- The complete Python collection passed: 2,209 tests collected, 2,203 passed,
  and six protected fixture tests skipped. Whole-repository Ruff, TypeScript,
  the 2,189-module production build, and diff-integrity checks also passed.
- Live Race/Learning smoke confirmed the P23 card is absent in Race Mode,
  appears exactly once in Learning Mode, reports `NO ACTIVATION EARNED`, exposes
  no activation control, and leaves the P19/P20 locked-authority decision intact.
- On the real Talladega archive, the P23 audit completed in 15.106 ms cold and
  14.564 ms warm mean; full Learning Readiness completed in 62.397 ms cold and
  65.162 ms warm mean. Both are Learning-only and outside startup authority.
- The full ranked matrix, selection rationale, frozen thresholds, result, and
  next collection missions are in `docs/p23_first_activation_audit.md`.

---

## P24 - Evidence Acquisition Operations

Overall status: **Verified collection infrastructure; P23 evidence collection
ongoing.** P24 makes the frozen P23 campaign executable and auditable. It does
not activate the steering-workload envelope or add intelligence authority.

- [x] Reuse P21 immutable datasets/leakage gates, P22 operations and acquisition
  guidance, P20 steering/control context, and the unchanged P23 protocol rather
  than creating a parallel learning system.
- [x] Add immutable, content-addressed session qualification certificates that
  bind source, run/session, car/track/build/profile/setup/FFB identity, exact lap
  decisions, channel truth, independence, subgroups, blockers, and admission.
- [x] Make the stored certificate authoritative for dataset construction; later
  builders consume its facts and cannot reinterpret the telemetry independently.
- [x] Preserve a lap-level flight recorder with canonical eligibility, traffic,
  setup/FFB context, clock/sub-tick health, and separate requested/applied
  control boundaries without bridging incompatible contexts.
- [x] Expose protocol-bound historical, null, negative-control, profile, and
  prospective templates plus a fact-only pre-run checklist. Prospective remains
  hard-locked until historical validation passes.
- [x] Audit the ten steering/FFB signals for units, signed behavior, count-as-time
  ordering, effective rate, coverage, corruption, sample continuity, scalar to
  sub-tick consistency, configuration stability, and steering conversion.
- [x] Freeze negative-control expectations before outcomes and require both the
  expected decision and blocker class to match the later immutable result.
- [x] Prevent renamed/copied/re-imported source telemetry, new run IDs, derived
  caches, and adjacent laps/windows from increasing session independence.
- [x] Publish actual P23 acquisition debt, next collection, latest certificate,
  and flight recorder in Learning Mode only while leaving Race Mode and P19/P20
  authority unchanged.
- [x] Re-import a source-owned Next Gen recording and complete steering signal
  truth/profile validation.
- [ ] Collect the 9 historical sessions, 10 null stints, 8 negative controls,
  and 9 subgroup requirements under the frozen certificate contract.
- [ ] Begin prospective collection only after the unchanged historical gate
  passes; no current session counts as prospective.

### P24 scientific counts

- Historical exact-FFB sessions: **0 / 9**
- Same-setup null stints: **0 / 10**
- Frozen negative controls: **0 / 8**
- Required subgroup groups: **0 / 9**
- Steering/profile truth: **complete**
- Prospective: **locked until historical validation passes**
- P23 activation: **NO ACTIVATION EARNED; shadow only**

The older Atlanta archive remains inventory because immutable telemetry-cache
ownership cannot be proven. P25 used a different, source-owned Atlanta practice
recording to complete steering truth without retroactively trusting that legacy
artifact or fabricating campaign progress.

### P24 verification evidence

- Ninety-one focused P21-P24 regressions passed after the product-quality pass;
  16 directly exercise P24. Hostile
  coverage includes copied/renamed sources, same-run re-import, adjacent-lap
  inflation, MaxForce/linear/smoothing/damper/steering-conversion mismatch,
  requested/applied boundary isolation, protocol mutation, certificate-owned
  admission, frozen negative-control expectations, prospective locking, and
  P19/P20/P23 authority isolation.
- P24 changed-file Ruff, TypeScript, the 2,189-module production build, and diff
  integrity passed. The complete Python collection passed: 2,225 tests
  collected, 2,219 passed, and six protected fixture tests skipped. A
  repository-wide Ruff audit reports 1,026 inherited findings outside P24, so
  no whole-repository lint claim is made here.
- Live smoke found no P24 content in Race Mode and exactly one Learning Mode
  campaign card with four accessible gates, truthful zero counts, incomplete
  profile state, the prospective lock, the typed next mission, a no-certificate
  state, and shadow-only admission.
- Certificate history is API-bounded, Learning Readiness carries a 12-lap
  recorder preview with explicit total/truncation state, immutable admission
  uses direct identity retrieval, and all 13 expectation-only negative-control
  recipes are discoverable while still counting only eight protocol controls.
- Measured 10-lap background work: 0.045 ms mean flight recorder, 0.239 ms mean
  certificate build, 20.198 ms admission, and 43.639 ms complete qualification.
  Warm progress averaged 3.764 ms; full Learning Readiness on saved Atlanta data
  was 87.976 ms cold and 78.453 ms warm mean.
- Full architecture, signal contracts, operations, evidence counts, and
  performance are recorded in `docs/p24_evidence_acquisition_operations.md`.

---

## P25 - First Qualified Evidence Campaign

**Status: verified field-acquisition pilot; NO QUALIFIED SESSION EARNED.** The
owned Next Gen Atlanta practice recording passed source/cache/schema ownership,
all ten steering-signal truth gates, the 360 Hz reconstruction contract, exact
FFB identity, and flight-recorder construction. Its 29 otherwise useful flying
laps were all rejected for nearby-car contamination, so the certificate admits
nothing and the frozen P23 thresholds remain unchanged.

- [x] Re-import one source-owned real Next Gen `.ibt` through the application
  path and bind source SHA-256, byte size, cache SHA-256, schema, run, setup,
  vehicle/build/profile, campaign, and certificate identity.
- [x] Audit all ten frozen P23 steering/FFB signals, including declared type,
  unit, structure, coverage, update behavior, canonical role, health, clipping,
  saturation, and scientific debt.
- [x] Prove six ordered count-as-time samples at 60 Hz reconstruct 360 Hz from a
  clean `SessionTick` sequence, while retaining timestamp anomalies as facts.
- [x] Bind the exact material FFB settings and `73 mm/rev` steering conversion
  into one immutable fingerprint.
- [x] Preserve every relevant lap and exact exclusion in the flight recorder;
  do not bridge the rejected traffic laps or the requested pit-state boundary.
- [x] Make the P25 certificate fail closed on absent source/cache/schema
  ownership and prevent a rejected or admission-empty certificate from reaching
  the dataset registry.
- [x] Collapse copied, renamed, moved, cache-rebuilt, and re-imported recordings
  to one source-session attempt/count identity; a frozen null card cannot reuse
  its own reference source as an observed null attempt.
- [x] Freeze the future same-setup/null run card before outcome, including exact
  car/build/profile, track, setup, FFB, steering conversion, fuel band, tire
  compound, control state, ten telemetry requirements, one warmup lap, and ten
  clean eligible laps.
- [x] Expose exact ownership, signal/FFB state, all certificate blockers,
  admissions, recorder decisions, counts, and the null run card in Learning
  Mode only; Race Mode remains unchanged.
- [ ] Earn the first qualified historical source session with at least ten
  uninterrupted clean laps and acceptable traffic/context evidence.
- [ ] Drive and import Null Session 01 under immutable card
  `p25n-4cb35044c911b200f334`; do not qualify it before the real file passes.

### P25 real scientific result

- Real source SHA-256:
  `37e380ebc4e70ca33190a0bace40c9a88508744fec4115177559083a7aeb50a7`
- Ownership: **verified**; fresh current-version cache and schema identity are
  bound to run `stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb`.
- Steering/profile truth: **complete**; all ten signals ready, full coverage,
  no malformed/non-finite/rail/saturation debt.
- Sub-tick truth: **pass**; 6 samples/record, 60 Hz base, 360 Hz effective,
  contiguous `SessionTick`, scalar relation `last_consistent`, normalized error
  0.0.
- FFB fingerprint:
  `7d5868401be0d368ffdeef7651a9b1b0f4a037f2e255d123fdffaf6d06a1e207`.
- Certificate `p24c-36d0f278b166d6f8bb36`: **rejected**; 0 clean
  admitted laps, 33 recorder entries, and no dataset admissions. Twenty-nine
  useful laps are explicitly traffic-contaminated.
- P23 counts: historical **0 / 9**, null **0 / 10**, negative controls **0 / 8**,
  subgroups **0 / 9**, prospective **locked**, activation **NO ACTIVATION
  EARNED**, authority `shadow_only`.

Complete source identity, signal matrix, duplicate audit, run card, performance,
and validation evidence are recorded in
`docs/p25_first_qualified_evidence_campaign.md`.

---

## P26 - Vehicle Systems Intelligence and Crew-Chief Component Graph

**Status: verified and adversarially hardened deterministic Next Gen foundation.** The existing Dial-In
knowledge now compiles into an immutable backend graph that separates controls,
component properties, whole-car states, observations, symptoms, outcomes, and
context. P26 projects P20 observations and exact P19 controlled history onto
that graph; it does not create another setup-authority path.

- [x] Define source-backed, build-scoped contracts for tires, alignment,
  springs, dampers, anti-roll bars, weight distribution, ride height/platform,
  brakes, differential, final drive, steering, and cooling configuration.
- [x] Compile every supported `SetupControlSpec` and every Next Gen-applicable
  accepted `SetupEffect` into typed nodes and safe expectation edges, with no
  broad runtime `causes` relation, orphan edge, or unmapped production control.
- [x] Preserve direct settings, live channels, derived metrics, indirect
  proxies, interpretation blockers, and unavailable quantities for every
  component. No bar-load, spring-force, damper-force, wheel-load, tire-force,
  exact drag, downforce, torque, or horsepower authority is inferred.
- [x] Make mechanical coupling, manual rechecks, and the scoped 2026 Next Gen
  spring/ride-height garage auto-compensation explicit and version-bound.
- [x] Generalize one garage row into seven immutable one-physical-factor
  experiment contracts, including coordinated front/rear ride-height controls,
  invariants, preconditions, expected response, countereffects, success metrics,
  and rollback rules. The contracts remain non-authoritative until P19 supplies
  one exact legal target and controlled-test authorization.
- [x] Assemble exact-run `ComponentAwarenessState` from P20 producer artifacts
  and P19 causes/outcomes without rereading telemetry. Generic whole-car
  observations create coupled component candidates, not proven component
  causes; every qualified P20 observation retains its own lap/phase/window
  scope, and exact-context Undo blocks only the rejected control while leaving
  unrelated component controls testable.
- [x] Expose read-only run, component-inspection, and control-trace endpoints;
  ground component questions such as “What is the RF spring doing?” through the
  same scoped Engineer query path while keeping controlled-history questions
  higher priority.
- [x] Add compact Vehicle Systems projections to the existing Setup and Engineer
  workspaces. Race Mode shows the leading family and next discriminator;
  Learning Mode adds agreement, evidence counts, settings, interactions,
  controlled history, policy blockers, and the P19 authority boundary.
- [x] Bind public projections and control traces to one persisted, verified
  telemetry artifact with exact run/source/cache/schema ownership, compatibility
  fingerprint, Next Gen car/version, reviewed iRacing build, and `Oval`
  configuration; mismatched, incomplete, stale, foreign, or corrupt scope fails closed.
- [x] Preserve typed mechanism and related-control identities through ranked-cause
  redaction. Component relevance no longer depends on matching words in prose, and
  broad whole-car mechanisms remain candidate families rather than isolated causes.
- [x] Add a reasoning-snapshot hash and a closed runtime observation/history graph.
  Runtime edges distinguish observed state, controlled response, and policy rejection,
  remain non-authoritative, and cannot point generic observations directly at components.
- [x] Cache immutable knowledge compilation, require explicit mappings for all 50
  Next Gen setup areas, type all three API responses, embed the root projection in
  the canonical intelligence response, and make the UI reject schema, identity,
  scope, hash, applicability, or authority mismatches.

### P26 verification evidence

- The current-only `p26.vehicle-systems.v3` graph contains 12 component
  definitions, 24 build-scoped interactions, 609 typed nodes, 843 typed edges,
  50 engineering-area nodes, 101 control nodes, seven registered source
  identities, a deterministic knowledge-content hash, and zero untyped `causes`
  edges, duplicate identities, orphan edges, or cross-owned ordinary edges.
- The real local Next Gen Atlanta run
  `stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb` completed the full
  P19/P20 build and exact-identity P26 projection. The persisted artifact verified
  exact run, source, cache, schema, car, reviewed build, and oval ownership; setup
  capture covered tires, alignment, springs, four-corner dampers, anti-roll bars,
  brake master cylinders, differential, platform, final drive, steering, and
  cooling without manufacturing component causality or setup authority.
- Hostile regressions prove manufactured component authority is rejected,
  unavailable state cannot be mixed with usable observability, one exact P19
  control authorizes at most one component projection, Undo is per-control,
  foreign or multi-scope P20 evidence cannot be relabeled, invalid history cannot
  become exact context, prose changes cannot alter typed relevance, broad
  mechanisms stay unresolved, runtime edges remain closed, and driver-execution
  evidence cannot become a physical steering-component diagnosis.
- The public contract is current-only: projection v4, runtime graph v3, and static
  graph v3. Engineer consumes the projection already embedded in the canonical
  intelligence response; Setup refreshes on workflow revision and exact setup
  identity. Deep client guards reject malformed nested state, null/non-null scope
  mismatches, stale hashes, unsupported applicability, and authority leaks.
- The complete 2,268-test collection passed: 2,263 passed and five protected
  skips. Changed-file Ruff, TypeScript, the 2,192-module production build,
  executable client trust-boundary tests, OpenAPI route inspection, the real Next
  Gen artifact regression, and diff integrity passed.

---

## P27 - Autonomous Crew Chief Executive

- [x] Reuse the rich private P19 `ReasoningSnapshot` rather than unsanitizing a
  public response or adding a duplicate cause ranker.
- [x] Preserve every typed mechanism membership on a physical P20 episode while
  retaining one artifact/independence identity.
- [x] Freeze run, session, selected scope, P19, P20, P26, setup, runtime,
  workflow, objective, investigation, and event-history identity in one workspace revision.
- [x] Persist immutable investigation origins and ordered, content-hashed typed
  events; reject stale writes and corrupt/reordered replay.
- [x] Freeze an accepted producer-authority fingerprint separately from the
  evolving event revision; changed P19/P20/P26/setup/runtime/workflow truth is
  read-only until an exact explicit rebase, and event count/head integrity makes
  silent tail deletion visible.
- [x] Provide a bounded approved-tool registry, deterministic subgoal planner,
  critic, one contextual driver question, atomic root projection, and exact P19-only terminal decision.
- [x] Upgrade the existing Engineer Race/Learning workspace without adding a tab
  or selection context; route evidence through canonical `focusEvidence`.

## P28 - Trackside Mission Control

- [x] Build hard Success Contracts exclusively from the current P19 measurement
  plan or controlled card, including repetition, independence, invariants,
  acceptance, rejection, retest, stop, and rollback semantics.
- [x] Monitor exact P19 measurement/A/B/A2 progress with a Run Sentinel that
  accepts only canonical eligible, context-clean laps and retains every rejection reason.
- [x] Bind Sentinel progress to the canonical workflow preflight stage and
  persisted stage-run ownership so a B run cannot advance A2 restoration.
- [x] Keep missing coverage unknown/blocked, preserve setup isolation, and never
  let the sentinel create Keep/Undo or stop-testing authority.

## P29 - Component Response Atlas and Driver Intelligence

- [x] Persist exact-context P26 controlled history as immutable component
  response records with separate mechanism, control-response, policy, context,
  setup, build, objective, phase, and evidence identities.
- [x] Persist driver complaint/answer memory separately as
  `complaint_prior_only`; it scopes inspection but cannot mutate P19 cause truth.
- [x] Record deterministic operational effectiveness counts without fake
  probability, causal uplift, or optimization claims.
- [x] Produce a revision-cached proactive brief and expose Atlas/driver-memory
  references in the atomic Engineer command deck.
- [x] Namespace workspace caches by repository identity, recheck immutable
  telemetry/lap inventory for warm context reads, and fail closed on unreadable
  active or exact-history workflows.

## P30 - Adaptive Experimentation Research

- [x] Expose a typed `data_locked`/authority-`none` infrastructure boundary and
  keep the optional generative executive disabled `shadow_only`.
- [ ] Activate hybrid observers, active experiment selection, interaction DOE,
  causal time-series methods, or Bayesian optimization only after the existing
  P21/P22 held-out and prospective activation gates genuinely pass.
- [ ] Grant no advanced method setup authority; current production remains one
  P19-authorized factor under exact-context A/B/A2.

## P31 - Truthful Crew Loop

- [x] Normalize simulator-integrity ratios with raw/provenance retention and a
  narrow unity-jitter contract; ambiguous ratio/percentage values fail closed.
- [x] Make missing scrub dependencies unavailable rather than zero, correct
  physical tire handedness/axles in row and vector engines, and add output-level
  co-observation contracts for braking and tire conclusions.
- [x] Treat authoritative ABS state separately from data-locked cut fields and
  tier wheel-lock evidence so an uncorrected wheel-speed proxy cannot prove a corner.
- [x] Bind new P19 workflows to immutable vehicle-condition and applied-control
  certificates plus tire, fuel, weather, wind, wetness, traffic, and execution context;
  legacy v1 records remain readable but cannot acquire v2 truth retroactively.
- [x] Represent evidence as explicit physical segment sets, preserve disjoint
  islands through revalidation, and cluster P20 mechanisms by meaningful overlap
  without multiplying causal independence.
- [x] Make `focusEvidence` a replace transaction with producer/artifact/system,
  Compare role, and source-run/setup identity; remove dead distance state and the
  empty Field Compare surface.
- [x] Bind Compare requests, responses, and persisted baskets to versioned source,
  cache, build, setup, lap, and physical-zone identity through shared cancellation,
  timeout, and runtime validation.
- [x] Make Crew mission states exact P19 projections, expose retry/rebase/abandon/
  objective/follow-up lifecycle actions, remove GET-time response/history writes,
  and select distinct evidence for each deterministic investigation tool.
- [x] Replace broad P26 live observability with quantity-specific certificates
  that separate screenable channel presence from qualified producer observation.
- [x] Give every Compare engine an explicit finding/evaluated-clear/unavailable
  state and unit-specific sustained-event thresholds; remove ungrounded public
  pseudo-confidence from the combined observation.
- [x] Add one semantic single-flight intelligence snapshot and indexed workflow
  scope, plus a lightweight visibility-aware catalog. Unchanged checks build no
  intelligence and unrelated corrupt history is never parsed.
- [x] Add strict nested P20/P26/Crew client decoders and behavioral React state
  tests while preserving the single Race-mode WHAT/WHERE/WHY/UNCERTAIN/NEXT surface.
- [x] Add measurement-only Crew effectiveness facts, source-owned shift-light RPM
  thresholds, raw candidate-channel contracts, and lap/session-based calibration
  stability evaluation. These facts do not unlock adaptive confidence or authority.
- [x] Keep P19 sole setup/Keep/Undo/retest authority, P20 observational, P26
  relevance/observability only, P30 disabled, and unavailable exact physics locked.

### P31 cache, persistence, and truth migrations

- Telemetry manifest schema is v6; protected `.ibt` files must be re-imported.
  V6 invalidates persisted nominal diffuser geometry, records qualified-clock
  decision readiness, and adds typed engineering role/admission provenance.
- New controlled workflows use `controlled-workflow-aba2-v2` stage condition and
  control identity. Historic v1 hashes remain verifiable without invented context.
- SQLite adds `stage_experiment_contexts_json` and the indexed
  `controlled_workflow_run_index`; additive migration backfills existing bindings.
- Shared intelligence snapshot identity hashes the exact relevant repository
  rows plus source, cache, schema, compatibility, run/session, setup, workflow,
  event, and candidate truth. Operational database writes do not churn it.

### P31 adversarial improvement ledger

- Real segmented Atlanta revalidation found stale child-segment sample counts;
  revalidation now recomputes segment membership and counts from co-observed rows.
- Schema migration initially invalidated synthetic v4 manifests and legacy scored
  workflow hashes; fixtures now consume the current manifest constant and explicit
  workflow-version compatibility prevents historical relabeling.
- Catalog optimization initially covered polling only; all cold intelligence,
  exclusivity, and creation paths now use the same normalized run index.
- Ten-thousand-history, concurrent single-flight, malformed relevant/unrelated
  workflow, transactional evidence focus, and strict nested-response regressions
  guard the new boundaries.
- Cold-path profiling exposed a second telemetry materialization and full-width
  per-lap integrity scans. The canonical observation read now supplies lap context
  and integrity scans only declared channel families. Warm Atlanta construction is
  below 10 ms; remaining cold work is truth-preserving P3/context aggregation debt.
- The packaged browser smoke had drifted behind the launch gate, renamed session
  action, and collapsed whole-lap chart surface. It now drives the shipped flow,
  imports protected Atlanta telemetry, opens Platform, expands charts, captures a
  screenshot, and rejects unexpected browser/transport failures.
- The expanded packaged Crew/restart smoke found P3 rebinding counting uncited
  rows between disjoint physical islands while retaining segment-only counts. That
  mismatch raised a fresh-import validation 409. Rebinding now filters and recounts
  exact segments; a hostile gap regression and the previously failed run pass.

### P31 release validation

- Python: 2,338 collected; 2,333 passed, five skipped, zero failed. The explicit
  slow selection collected 26 (25 passed, one skipped); the integration marker is
  nonempty and its restart/tamper test passed; 187 focused P19/P20/P26/Crew tests
  passed with zero failures.
- Frontend: three behavioral Vitest/React Testing Library tests, five executable
  runtime-trust files, TypeScript, and the 2,197-module production build passed.
- Product/runtime: OpenAPI 3.1 exposed 86 paths/94 operations with no duplicate
  operation IDs; the protected Atlanta regressions passed; PyInstaller produced
  the Windows sidecar. Built-UI browser smoke imported Atlanta, opened intelligence
  and Crew, restarted both processes, and reopened the exact persisted run with no
  console errors or unexpected failures. Its older unreviewed car build correctly
  kept P26/Crew authority withheld rather than bypassing applicability.
- Performance: Atlanta canonical intelligence measured 13.195 s cold and 5.488 ms
  warm, with one build, one cache entry, and exact object reuse. The warm target
  passed; the 2.0 s cold target remains open. A scoped catalog over 10,000 corrupt
  unrelated histories deserialized one relevant row and passed in 0.22 s.

### P27-P30 verification evidence

- Focused Crew Chief, authority, P19/P20/P26, API, persistence, restart, UI, and
  hostile-response contracts pass, including stale revision, event corruption,
  extra-field injection, forged target, foreign session, and exact P19 mirror cases.
- The persisted Next Gen Atlanta workspace builds from one canonical bundle with
  exact P19/P20/P26/setup/runtime identities and no raw trace or second planner.
- TypeScript, production UI build, OpenAPI inspection, changed-file Ruff,
  bytecode compilation, full Python regression, and diff integrity are required
  for the release entry below.
- The continuous adversarial hardening pass closed 12 material findings: one P0,
  three P1, six P2, and two P3. The final tree passed 2,316 collected Python
  tests (2,311 passed, five protected environment/artifact skips), 159 focused
  hostile/authority/P19/P20/P26/context tests with zero skips, whole-repo Ruff,
  TypeScript, a 2,196-module production build, bytecode compilation, seven-route
  OpenAPI inspection, the real Atlanta workspace regression, the unchanged
  609-node/843-edge/50-area P26 graph, and diff integrity. Real Atlanta warm
  Crew Chief assembly improved from 3,317.595 ms to 148.147 ms while retaining
  immutable artifact rechecks.

## P32 - Lap-Time Mechanics and Speed Intelligence

- [x] Add a versioned, source-backed registry of 12 performance principles,
  17 typed performance mechanisms, outcomes, and objective envelopes. Objective
  selection changes policy protection, never measured physics or setup authority.
- [x] Build one repository-scoped, run-owned narrow performance basis from
  qualified laps and canonical context; preserve position alignment, source
  channels, path/time bases, coverage, blockers, and exact setup identities.
- [x] Reuse canonical reciprocal-speed time alignment for a deterministic
  `LapTimeOpportunityMap` with local/carried/amplified/recovered/surrendered
  origin semantics, persistence, carry, repeatability, and theoretical-not-
  guaranteed opportunity.
- [x] Build connected `CornerPerformanceChain` projections across approach,
  braking, entry, center, exit, and following-straight carry without treating a
  single minimum-speed sample as the whole center phase.
- [x] Add typed driver-demand/vehicle-response separation with explicit line,
  traffic, mixed-change, and unresolved states; contaminated evidence cannot
  become setup attribution.
- [x] Derive a qualified-telemetry `TrackDemandProfile` and connect measured time
  consequences to P20 mechanisms and P26 component relevance without creating a
  component-cause edge or new setup authority.
- [x] Add a branched `PerformanceExplanationChain`, mandatory strongest
  contradiction, nine bounded Crew Chief performance inspections, and planner
  order beginning with measured time consequence before component relevance.
- [x] Extend exact-context A/B/A2 memory with time origin, phase effect, downstream
  carry, countereffects, repeated response, and the unchanged P19 policy verdict.
- [x] Add the concise Race-mode Speed Story and Learning-mode time ribbon, corner
  chain, driver/car, track-demand, P20/P26, objective, contradiction, history, and
  canonical `focusEvidence` surfaces behind an atomic P32 client trust boundary.
- [x] Keep the empirical layer observation-only: no fake minimum-lap-time model,
  no exact tire/aero force, no generic `causes` edge, no optimal setup, no
  guaranteed theoretical pace, and every setup action remains an exact P19 mirror.

### P32 release validation - VERIFIED AFTER P32.1 2026-08-13

The original green suite did not exercise several public-builder behaviors and
therefore overstated release closure. A real Atlanta audit showed a fully
traffic-contaminated comparison narrated as a `0.136 s` attributable cost, while
vertical disturbance exposure read `99.44%` from the normal gravity baseline.
P32 was reopened rather than accepting that false green. P32.1 now closes those
truth gaps with public-builder, restart, client-boundary, and real-telemetry proof.

- Python: 2,361 collected; 2,356 passed, five protected skips, zero failures.
  Twenty backend P32 hostile tests and three frontend P32 contracts cover the
  requested local-speed, braking/carry, path, traffic, repeatability, missing-data,
  cross-start/finish, component/history, contradiction, authority, and forbidden-
  claim boundaries. Whole-repo Ruff and bytecode compilation passed.
- Frontend: TypeScript, all three behavioral UI tests, all five executable runtime
  trust suites, and the 2,198-module production build passed.
- Real telemetry: the persisted Next Gen Atlanta workspace produced schema
  `p32.performance-intelligence.v1`, all 12 principles and 17 mechanisms, four
  measured opportunities, one connected corner chain, three non-causal component
  links, full reciprocal-speed coverage, four Crew evidence artifacts, exact
  P19/P20/P26/P32 identity binding, zero setup authority, a data-locked optimizer,
  and a `no_call` Crew decision.

## P32.1 - Performance Truth Closure

- [x] Make Traffic/context contamination lead the Speed Story: preserve the
  observed signed difference, block attribution, name the strongest confounder,
  and request a clean comparable pass.
- [x] Preserve gain/loss sign semantics everywhere; a negative elapsed-time
  effect is a gain and cannot be narrated as time that the driver lost.
- [x] Reuse the canonical full run-compatibility identity and fail closed on
  car, track, build, session, or configuration mismatch.
- [x] Require complete co-observed driver-demand evidence before calling inputs
  matched, and compare racing line by physical position rather than path length alone.
- [x] Remove the normal vertical-gravity baseline from disturbance exposure;
  distinguish real limiter evidence from ordinary shifts and derive tire-state
  development from qualified run length.
- [x] Require exact phase/physical-scope repeatability, contiguous carry until
  first recovery, adjacent following-straight attribution, and bounded circular
  start/finish continuity.
- [x] Preserve measured P32 time/origin/carry when P26 is unavailable while
  withholding only component attribution and all setup authority.
- [x] Make all nine P32 Crew inspections reachable and attach the typed artifact
  each tool claims to inspect.
- [x] Deeply mirror every rendered P32 contract at the client boundary, including
  forbidden causal/optimization prose, finite bounds, authority pairing, request
  objective, exact P19 next move, and opportunity/evidence identity.
- [x] Put `NEXT · P19` first in compact Race Mode and retain the full performance
  chain, explicit unavailable states, and canonical focus behavior in Learning Mode.
- [x] Preserve controlled-test time origin, phase effect, and downstream carry
  across persistence/restart; invalid or incomplete tests must publish none.
- [x] Replace constructor-only hostile checks with public-builder telemetry tests
  and pass the traffic-contaminated Atlanta acceptance contract before re-closing.

### P32.1 release validation

- Python: 2,405 collected; 2,400 passed and five protected tests skipped. The focused
  94-test P32/Crew/client release slice and 54 hostile performance-truth tests
  passed, including canonical traffic, sparse demand, signed gain/loss, compatibility,
  opportunity-relative carry, exact adjacency/repeatability, P26 unavailability,
  typed Crew artifacts, restart memory, and ordinary-read versus integrity failure.
- Frontend: TypeScript, the executable hostile runtime trust suite, all five UI
  behavior tests, and the 2,198-module production build passed. The client deeply
  binds every typed Crew artifact to the canonical P32 projection and rejects
  causal prose, blocked component candidates, invalid history, and identity drift.
- Real telemetry: the persisted Next Gen Atlanta public workspace passed the full
  backend-to-client guard with four measured opportunities and 19 typed P32 Crew
  entries. It reports the observed `+0.136447 s` loss, blocks attribution because
  source/reference traffic exposure is `100%`, names traffic as the strongest
  contradiction, publishes zero component influence and zero setup authority,
  measures disturbance exposure at `0.0613`, withholds limiter zones, labels tire
  development `short_run`, and ends in `no_call`.
- Whole-repo Ruff, bytecode compilation, and diff integrity passed.

## P33 - Engineering Learning Flywheel

- [x] Persist one immutable, append-only `EngineeringExperienceRecord` ledger
  with a transactionally bound stream head, deterministic content identity,
  source hashes, typed context/problem/P19 facts, and references to canonical
  investigation, A/B/A2, P26, and P32 artifacts instead of copied telemetry.
- [x] Reconstruct recurrence deterministically across sessions while separating
  exact, compatible, weak, and blocked transfer; car/build, track configuration,
  setup context, objective, tire/weather, traffic, and driver-execution drift can
  only reduce historical relevance.
- [x] Project contextual driver fingerprints from independent qualified episodes
  and exact car-response fingerprints from existing controlled P19/P26/P32
  history without turning either into mechanical diagnosis or setup advice.
- [x] Preserve investigation order, exact successful discriminators, questions,
  measurements, terminal outcomes, elapsed/lap/tool costs, and true no-finding
  paths as typed effectiveness and negative knowledge.
- [x] Record mind change only when the newly cited artifact has exact source
  provenance and the before/after P19 snapshots truly differ; retrieval alone
  cannot become confirmation, discrimination, causation, or faster resolution.
- [x] Count independent physical episodes, controlled workflows, sessions, and
  contexts rather than references or dense samples; one source cannot teach
  recurrence or learned priority by being cited repeatedly.
- [x] Embed one bounded `CrewChiefLearningPrior` in the existing workspace with
  `attention_only` authority. Current qualified evidence remains pinned first;
  exact history outranks compatible history; learning may reorder only live tools
  inside an unchanged safety band and must explain `WHY THIS IS EARLIER`.
- [x] Keep terminal learning capture healthy and atomic while containing corrupt
  history: P19 workflow scores and Crew terminal truth still commit with an exact
  durable blocked-capture identity, no experience is invented, restart preserves
  the state, and the P33 prior visibly blocks all learned reorder.
- [x] Extend Engineer Race/Learning mode with concise recurrence memory and a
  typed Engineering Memory surface; historical evidence navigation verifies the
  exact source session, run, setup, build, artifact, and digest before changing
  selection. No new top-level tab or arbitrary learning mutation route exists.
- [x] Keep retrieval bounded to indexed context branches with fixed limits and no
  telemetry reads. A 10,001-record ledger returned a warm page in `34.303 ms`, a
  cold projection in `53.024 ms`, and a cached projection in `7.197 ms`.
- [x] Keep Bayesian optimization, DOE setup authority, formal causal learning,
  neural/generative setup engineering, learned probabilities, and autonomous
  multi-control experimentation locked behind their existing evidence gates.

### P33 release validation - VERIFIED 2026-08-14

- Python: 2,514 collected; 2,509 passed and five protected tests skipped. The
  dedicated P33 model/repository/service/lifecycle files contain 82 hostile and
  scenario tests; the integrated P33/authority/P19/P26/P32/Crew/API/client slice
  passed 336 checks. The post-fix full collection was rerun from zero failures.
- Adversarial closure permanently covers reference inflation, tied P19 ranks,
  exact-before-compatible priority, ordered request/result identity, genuine
  discriminator credit across normal workspace-revision advancement, rebase
  invalidation, dead-end containment, driver/build/objective drift, Undo axis
  separation, exact mind-change provenance, cross-session navigation, append-only
  tamper/deletion, restart identity, bounded retrieval, and corrupt-ledger
  authority containment.
- Frontend: all six executable runtime trust suites, nine Vitest behavior/unit
  tests, TypeScript, and the 2,201-module production build passed. The client
  mirrors the complete learning, provenance, investigation, and workflow-capture
  contracts and independently recomputes their canonical digests.
- API/packaging: OpenAPI 3.1 generated 94 operations across 86 paths and 325
  schemas with zero duplicate operation IDs. P33 remains inside the existing Crew
  workspace, GET stayed read-only, the Windows sidecar packaged successfully, and
  its exact executable returned `status=ok` before clean shutdown.
- Real telemetry: persisted Atlanta and EchoPark workspaces passed the complete
  backend-to-client trust boundary. Atlanta preserved the observed `+0.136447 s`
  loss, blocked attribution at `100% / 100%` traffic, published zero component
  claims and zero setup authority, measured disturbance at `0.0613`, ended in
  `no_call`, and exposed P33 as `attention_only`, insufficient-history, with no
  learned reorder and no P19-rank change.
- Whole-repo Ruff, bytecode compilation, and diff integrity passed.

## P33.1 - Driver-Facing Truth and Interface Sharpening

- [x] Reduce Race Mode to the exact P19 next move, observed signed result,
  attribution state, and strongest contradiction; place origin/carry and every
  supporting engineering surface behind deliberate disclosures.
- [x] Keep Learning Mode complete without turning insufficient or blocked P33
  history into a wall of empty cards. Engineering Memory remains visibly
  `attention_only` and never gains P19 rank or setup authority.
- [x] Separate context-cleared laps from mission-accepted laps and measurement
  attempts. Completion now requires a server-verified acquisition cohort whose
  laps remain exact-P19 context-cleared and retain complete healthy required-
  channel and physical-position coverage, or an exact bound controlled-workflow
  stage. The recorded outcome remains client-attested and cannot alter P19 stop-
  testing authority; ordinary clean laps remain screening evidence only.
- [x] Bind the complete Run Sentinel to the atomic Crew workspace identity and
  independently recompute its canonical digest at every public client boundary,
  while excluding mission progress from producer authority revision.
- [x] Replace opaque artifact IDs and `KNOW`/`exact` totals with human evidence
  labels, typed evidence-state counts, physical lap/window context, and optional
  technical provenance.
- [x] Make the unresolved Priority Rail a dismissible narrow-screen overlay with
  an always-visible attention trigger, Escape handling, focus return, and mode-
  switch persistence while retaining the mandatory desktop evidence rail.
- [x] Preserve one page heading, explicit Race/Learning toggle state, track context,
  single-column narrow Race stories, and keyboard-safe support disclosure.

### P33.1 release validation - VERIFIED 2026-08-14

- Python: 2,527 collected; 2,522 passed and five protected tests skipped. New
  hostile contracts cover screening-only and traffic-blocked laps, warning or
  partially populated channels, missing or spatially gapped physical-position
  coverage, exact controlled-stage binding, sentinel cache versus authority
  identity, Race disclosure, and responsive evidence-rail behavior.
- Frontend: all 12 Vitest behavior/unit tests, all six executable runtime trust
  suites, TypeScript, and the 2,201-module production build passed. OpenAPI 3.1
  still exposes 94 operations across 86 paths and 325 schemas with no duplicate
  operation IDs.
- Real product proof: persisted Atlanta and EchoPark workspaces passed the public
  backend-to-client guard. Live EchoPark Race/Learning inspection preserved the
  traffic-blocked performance story, zero setup authority, 11 context-cleared
  laps, zero mission-accepted attempts, and an explicit unbound acceptance state.
  At 390 x 844 the Priority Rail opened as an overlay, dismissed by button and
  Escape, stayed dismissed across mode changes, and left the Race workspace usable.
- Changed-file Ruff, backend bytecode compilation, and diff integrity passed.

## P34 - Earned Investigation Adaptation

- [x] Freeze immutable, content-addressed deterministic-baseline,
  memory-informed-shadow, and one-position limited-attention policy contracts.
  The baseline preserves every mandatory identity, integrity, context,
  driver-versus-car, contradiction, and current-evidence pin ahead of memory.
- [x] Persist baseline and shadow decisions on the same exact pre-outcome Crew
  workspace, P19/P20/P26/P32 snapshot, P33 ledger boundary, tool cohort,
  qualified artifact cohort, objective, and driver-answer state. Production uses
  baseline until a server-owned activation artifact passes the frozen protocol.
- [x] Preserve append-only paired decisions, investigation outcome certificates,
  source-pair discriminator outcomes, counterfactual classifications, outcome
  followups, negative transfers, negative controls, evaluations, and activation
  decisions with exact parent hashes, restart reconstruction, and bounded reads.
- [x] Keep counterfactual credit honest. Unperformed or unqualified shadow work is
  `counterfactual_unobservable`; v1 can certify only a directly supported
  one-position discriminator advance and cannot infer whole-path tool, time, lap,
  question, mission, or dead-end savings.
- [x] Freeze the activation protocol, prospective boundary, independence unit,
  exclusions, seven negative controls, subgroup/drift gates, safety thresholds,
  efficiency thresholds, one-position ceiling, and automatic rollback rules
  before admitting any real outcome.
- [x] Contain corrupt unrelated P33/P34 history while failing closed on relevant
  corruption; verify source-owned P33 relevance and complete control cohorts;
  block future memory, material driver drift, incompatible/unreviewed builds,
  stale receipts, post-rebase v1 credit, and forged evaluations or activations.
- [x] Integrate one read-only `INVESTIGATION IMPROVEMENT` card in Learning Mode.
  Race Mode renders no P34 surface, the client exposes no activation control, and
  the exact runtime mirror rejects drift across policy, protocol, P19-P33,
  qualified evidence, frozen pair, comparison, readiness, and projection truth.
- [x] Keep normal Crew reads bounded and write-free. Foundation plus pair creation
  is atomic; terminal Crew/P33 truth survives a blocked P34 savepoint; workflow
  followup recovery drains deterministic 512-item pages without one corrupt row
  starving later valid work.
- [ ] Earn `limited_attention` from qualified real investigations. **DATA LOCKED:**
  the current archive has zero qualified historical investigations, zero genuinely
  prospective investigations, zero observable policy comparisons, and none of
  the required recurrence, context, problem-family, objective, subgroup, or
  negative-control population. Production therefore remains
  `deterministic_baseline`; memory remains `shadow_only` and `attention_only`.

### P34 frozen protocol

- Boundary: `2026-08-15T08:12:46Z`; real prospective investigations must open
  strictly after this instant. Historical replay and synthetic mechanics cannot
  satisfy the activation gate.
- Baseline: `p34pol_48190cf9a560de6fae1bb655` / SHA-256
  `48190cf9a560de6fae1bb655fe365b41478038825653743b2a391d62ea788709`.
- Memory shadow: `p34pol_de720756ba383ec92910e64e` / SHA-256
  `de720756ba383ec92910e64e6360685d9d0f900adb4e5f9156db4488b3e55198`.
- Limited ceiling: `p34pol_d9e85250e6c0f43d3eadb5c7` / SHA-256
  `d9e85250e6c0f43d3eadb5c7aad06fd257e23956d3fb0bcba5b586b17b7a0795`.
- Activation protocol: `p34proto_487dd9698e01a7f77d493d01` /
  SHA-256 `487dd9698e01a7f77d493d011e4f0ec0246ba0ed7efdaea17ef164cbc7a8fd61`.

### P34 release validation - VERIFIED 2026-08-15

- Scientific result: **NO ATTENTION ACTIVATION EARNED.** Zero real historical,
  prospective, observable, or unobservable qualified comparisons were admitted;
  all efficiency and quality results remain descriptive/unavailable, no negative
  transfer is invented, every safety/authority ceiling remains intact, and exact
  remaining collection missions are published in Learning Mode.
- Hostile proof covers all seven frozen negative controls; all physical-scope,
  objective, driver/build drift, current-evidence, future-memory, receipt,
  post-rebase, cache/WAL, corruption, restart, recovery, synthetic-independence,
  counterfactual, discriminator, subgroup, activation-forgery, rollback, and
  displayed-versus-executed action boundaries. P19 rank/state/action, setup
  authority, mission truth, and Keep/Undo/Retest are byte-invariant under memory.
- Performance: 10,000 independent investigations with multi-revision rows remain
  bounded and reread no telemetry; 10,001 fails closed. Measured cold evaluation
  was 67.7 ms and the complete cold projection 80.7 ms; warm paired decision was
  0.851 ms, activation resolution 11.008 ms, and readiness projection 27.669 ms.
- Python: 2,620 collected; 2,611 passed with nine protected skips. The dedicated
  P34 suite contains 54 paired-policy, persistence, scenario, scale, and hostile
  tests; the integrated P19-P34/Crew/API/client slice passed 370 of 374 checks
  with four protected fixture skips. The complete repository, Ruff,
  changed-backend bytecode compilation, and diff integrity passed.
- Frontend: 84 hostile runtime assertions, 17 Vitest behavior/unit tests,
  TypeScript, and the 2,202-module production build passed. Live 1280 x 720
  EchoPark inspection showed zero P34 DOM in Race Mode and a read-only Learning
  card that says deterministic baseline, shadow only, no activation earned, no
  setup authority, and no inferred savings.
- API/packaging: OpenAPI 3.1 exposes 94 operations across 86 paths and 333 schemas
  with zero duplicate operation IDs and the same seven Crew endpoints. The
  Windows sidecar packaged to 83,741,667 bytes, SHA-256
  `0583551298D12B7A0292CAED316376B2F1FA6666D2D86F101B24CEFE700F5245`,
  returned the exact healthy response, and shut down with no residual process or
  listener.
- Real telemetry: cleaned, isolated Atlanta preserved `+0.136447 s` observed
  loss, `blocked_by_traffic`, `100% / 100%` traffic, zero component claims, zero
  setup authority, `0.0613` disturbance, no limiter zones, and `no_call`. P33
  remains `attention_only`; P34 reports deterministic baseline, shadow only, no
  activation, no effective activation artifact, and exact acquisition deficits.

## P35 - Next Gen Oval Vehicle Dynamics Intelligence

- [x] Compile one immutable, content-addressed Next Gen oval vehicle-dynamics
  knowledge graph from reviewed local sources. Typed quantities, mechanisms,
  load paths, tire-demand states, chassis responses, transient and steady-state
  behavior, component influences, interactions, observation contracts, and
  driver-response chains carry exact provenance, units, phase, context,
  applicability, unavailable-quantity, forbidden-inference, and authority locks.
- [x] Model the current Next Gen car instead of legacy stock-car folklore. The
  graph covers independent rear suspension, rack-and-pinion steering, four-corner
  brake pressure and wheel response, springs versus dampers, front and rear bars,
  static distribution versus dynamic loading, alignment, differential behavior,
  tires, platform/aero proxies, gearing, and tire-state evolution. Track-bar and
  truck-arm controls are forbidden for this architecture.
- [x] Represent the oval lap as connected physical states and preserve the exact
  five-stage chain `DriverInput -> VehicleDemand -> VehicleResponse ->
  Tire/Platform -> Time`. Each of the 16 reviewed mechanism families declares
  transient/steady-state regime, supporting and contradicting evidence, exact
  discriminator, driver/context confounders, P20 observations, P26 candidate
  families, and P32 consequences.
- [x] Keep physics honest. Exact tire force, wheel load, spring/damper force, ARB
  torque, downforce, aerodynamic balance, drag coefficient, differential torque,
  friction coefficient, and contact-patch distribution remain unavailable. Static
  crossweight cannot become live wheel load, banking cannot fabricate tire load,
  and generic combined-demand knowledge cannot invent a friction limit.
- [x] Project one run-owned `PerformanceMechanismAssessment` into the existing Crew
  workspace. P20 remains the observation producer, P32 remains measured-time and
  driver-versus-car authority, P26 remains current component relevance, and P19
  remains the sole cause, setup, controlled-test, Keep/Undo/Retest, and terminal
  authority. P35 reads no raw rows, laps, segments, or unrestricted telemetry.
- [x] Bind every positive mechanism and focus artifact to the exact current P19,
  P20, P26, P32, runtime, run/session, lap cohort, physical-position window,
  phase, evidence state, channels, traffic/context state, and source hash. The
  frozen runtime-trust manifest independently constrains each mechanism's P20/P32
  bridge, component families, inspection tool, observation contracts, evidence
  layers, aliases, and 76 exact channel-requirement groups.
- [x] Add 14 bounded Vehicle Dynamics inspection tools and expert context-only
  questions. Their outputs are typed evidence, never setup advice. The sealed P34
  protocol is unchanged: P35 tools and artifacts are excluded from P34 cohorts,
  and a P35 inspection revision executes deterministic baseline with P34 pairing
  explicitly withheld.
- [x] Add a compact Learning-only Vehicle Dynamics Blackboard with performance
  problem, driver demand, vehicle response, tire/platform demand, regime,
  candidates, candidate-only component families, strongest support and
  contradiction, discriminator, and exact `NEXT · P19`. Race Mode retains its
  decision-first story and adds only one compact non-authoritative dynamics line;
  no tab, setup control, component cause, or alternate recommendation path exists.
- [x] Fail closed against static-knowledge authority, stale or foreign builds,
  non-oval scope, traffic, missing channels, partial brake corners, unmatched
  P20/P19 snapshots, cross-lap evidence, forged graph/component/focus relations,
  response-label/body disagreement, carried exit loss mislabeled as gearing,
  tire migration overclaim, unavailable physics, and coordinated payload rehashes.

### P35 frozen knowledge contract

- Knowledge version: `2026.08.p35-next-gen-oval.v1`.
- Graph: `p35vdg_c14af7ad22a752df5710a6e6`, version
  `2026.08.next-gen-oval.v1:c14af7ad22a7`, SHA-256
  `c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030`.
- Runtime trust: `p35.vehicle-dynamics-runtime-trust.v1`, SHA-256
  `5bc9139f42049f391015040948147f9de37af1b2da770ea99e10d1db72f74164`.
- Exact reviewed applicability: current NASCAR Next Gen oval car paths, car
  version `2026.06.08.02`, and iRacing builds `2026.03.09.03` through
  `2026.06.24.02`. A later build or non-oval package resolves unavailable until
  reviewed; no compatibility is inferred from a nearby version string.
- Inventory: 13 sources, four external namespaces, 56 quantities, 16 mechanisms,
  eight load paths, eight tire-demand states, eight chassis-response states, four
  transient and three steady responses, 11 component influences, 16 interactions,
  32 observation contracts, three driver-response chains, two forbidden control
  families, 226 nodes, 83 edges, and 76 runtime channel groups.

### P35 release validation - VERIFIED 2026-08-15

- Whole repository: the definitive isolated run collected 2,694 Python tests and
  finished with 2,685 passed, nine protected skips, and zero failures. Whole-repo
  Ruff, bytecode compilation of every changed Python file, and diff integrity
  passed; the production database SHA, size, mtime, and absent WAL/SHM state were
  unchanged.
- Backend: 34 ontology/compiler hostiles and 30 runtime/Crew integration tests
  passed. The broader Crew/P32.1/P33/P34/P35 slice passed 225 checks with one
  protected skip. An independent coordinated-rehash adversary returned
  **BACKEND CLEAR** after replaying build, runtime, P20/P32 provenance, lap/window,
  traffic, unavailable-physics, brake-channel, focus, component, P19, and P34
  authority attacks.
- Frontend: all seven executable runtime-trust programs, 20 of 20 Vitest behavior
  tests, TypeScript, the 2,205-module production build, and 39 focused frontend
  contracts (37 passed and two protected fixture skips) passed. Exact runtime
  mirrors reject stale graph/trust identities, scientific P20 or evidence-index drift, invalid
  mechanism-channel relations, unavailable runtime, and coordinated rehashing.
  Python float-number semantics and float arrays are mirrored explicitly; frozen
  model parity prevents those canonical key sets from silently drifting.
- API: regenerated OpenAPI 3.1 remains stable at 86 paths and 94 operations with
  no missing or duplicate operation IDs. P35 adds no route; the assessment is one
  atomic field of the existing Crew workspace. Published model property order is
  exact, static graph/trust internals are not public, and every authority-shaped
  P35 field is a denial or ceiling literal.
- Scenario evidence: a synthetic position-aligned telemetry cohort flows through
  the real P20/P32 producers into one qualified P35 candidate. The known Atlanta
  session, evaluated only through an isolated database copy, preserves the
  measured `+0.136447 s` loss while traffic blocks attribution: candidates remain
  visible but blocked, positive support and component causal claims remain zero,
  a contradiction and useful discriminator remain navigable, setup authority is
  false, and P19 remains `no_call`.
- Live and packaged delivery: isolated Atlanta browser QA passed the complete
  backend-to-client structural and canonical-hash boundary. Race Mode rendered no
  Blackboard and one compact blocked-dynamics line; Learning Mode rendered every
  requested expert section, compact channel provenance, the exact measured loss,
  blocked zero-support candidate, contradiction/discriminator navigation, and no
  setup authority. The final Windows sidecar built from the post-canonicalization
  tree to 83,869,869 bytes (SHA-256
  `A1653CC0A4EBFED2EF2A28525EC9D58FE85C400C523EAEBF30EC878315073494`),
  returned the exact health contract from its sole loopback listener, and left no
  process, port, or temporary database behind. The production database SHA, size,
  mtime, and absent WAL/SHM state remained byte-for-byte unchanged.

## P35.1 - Unified Dial-In Knowledge Spine

- [x] Compile all 92 reviewed Dial-In effects into immutable, content-addressed
  `MechanismSetupBridge` records that bind typed P20 observation families, P26
  component families, P32 performance mechanisms, P35 vehicle-dynamics
  mechanisms, exact phases/regimes, expected responses, countereffects,
  protected outcomes, bounded inspection tools, applicability, and provenance.
  Missing control mappings never erase reviewed engineering knowledge.
- [x] Publish an exact coverage report instead of inferring coverage from the
  legacy action table. The frozen report SHA-256 is
  `d3f9f95c41f85bdbc2ac697d242d6d1e560bd58575cf65155e3843f88c7c8680`:
  92 catalog effects, 92 unique bridges, 64 measurable hypotheses, 22
  structurally P19-testable controls, six explicitly unsupported/removed legacy
  Next Gen effects, and zero missing or duplicate effect identities.
- [x] Build one run-owned `CurrentEngineeringKnowledgeProjection` from the
  canonical P20, P26, P32, P35, P33, and P19 projections. Driver complaint is a
  question/phase prior only; current candidate ordering comes from the exact P32
  opportunity and candidate-owned P35 evidence. No raw telemetry observer or
  parallel performance opportunity was added.
- [x] Preserve three explicit authority levels: educational knowledge describes
  general influence only; a measurable hypothesis adds current relevance and a
  discriminator but no target; a P19-testable control exists only when its exact
  action equals the current nested P19 terminal decision. Only that third level
  can expose direction, target, or controlled-test policy.
- [x] Make session-bound Dial-In, Crew Chief, Engineer Learning Mode, controlled
  workflow, and P19 share the same P32 opportunity ID and projection hashes. A
  private immutable workflow receipt seals the exact window, phase, measured
  time, and source-channel cohort; drift from the legacy opportunity builder is
  rejected rather than silently creating another performance truth.
- [x] Replace hidden historical score authority with typed P19/P33 exact-context
  history: prior response, dead ends, and Keep/Undo/Retest remain visible inputs,
  but cannot change current P19 cause truth. Unreviewed builds remain educational
  only, generic history cannot outrank current evidence, and track bar, truck arm,
  bump stop, and packer logic remain forbidden for the Next Gen car.
- [x] Add the bounded Crew tools `inspect_setup_knowledge_for_mechanism` and
  `inspect_control_experiment_contract`, plus the Learning-only Engineering
  Knowledge Spine with `WHY THIS SYSTEM IS RELEVANT`, `WHAT IT PHYSICALLY
  CHANGES`, `WHAT THE CAR IS DOING NOW`, `WHAT EVIDENCE IS MISSING`, `WHAT WOULD
  SEPARATE THE CANDIDATES`, `WHAT HISTORY SAYS`, and exact `NEXT · P19`. Race Mode
  stays concise and renders no P35.1 knowledge-spine DOM.
- [x] Deep client validation recomputes projection and bridge identities, enforces
  the complete 92-effect inventory, binds every displayed Dial-In hypothesis to
  the shared projection, and rejects complaint-only promotion, forged level-three
  targets, opportunity drift, authority smuggling, duplicate relations,
  unsupported builds, and legacy-control inheritance.

### P35.1 release validation - VERIFIED 2026-08-16

- Whole repository: an isolated no-bytecode run collected 2,709 Python tests and
  completed with 2,700 passed, nine protected skips, and zero failures in
  267.659 seconds. Whole-repository Ruff, temporary-output bytecode compilation
  of all 22 changed Python files, and diff integrity passed.
- Focused truth: 11 P35.1 backend hostiles cover the 92-effect compiler, graph
  bindings, missing action mappings, complaint neutrality, transient-versus-
  steady evidence, carried-loss gearing containment, exact P19 authority,
  unreviewed builds, canonical P32 workflow identity, and session-bound Dial-In.
  Four focused frontend contracts and the executable Dial-In, Crew, and workflow
  trust guards passed.
- Frontend and delivery: TypeScript passed with zero errors, all 30 Vitest
  behaviors passed, and the production build completed with 2,207 modules.
  Regenerated OpenAPI remained stable at 86 paths and 94 operations with no
  missing or duplicate operation IDs.

## P35.2 - Semantic Precision and Release Trust

- [x] Bind every P19-testable setup action to one exact reviewed effect,
  control, direction, and experiment factor. Opposite directions that share a
  garage control no longer share an ambiguous knowledge handoff, and shuffled
  bridge/catalog order cannot change the selected identity. Zero or multiple
  matches fail closed.
- [x] Preserve P26 component truth as separate static possibility, current
  candidate, current support/tested, contradicted, blocked, unobservable, and
  irrelevant cohorts. The public Dial-In and Learning surfaces no longer turn
  component presence into current relevance.
- [x] Separate effect-level expected vehicle state, validation metric,
  countereffect state, protected performance outcome, and rollback condition.
  Coverage now reports identity, semantic precision, runtime observability, and
  experiment readiness independently. The P35.2 coverage SHA-256 is
  `a7dd3bcb645b037d803289dd94ffa7a0c89c6d01e7ce7c52e635c8471826cc1c`:
  92 of 92 identities and semantic contracts, 86 runtime-observable contracts,
  22 testable effects, nine distinct controls, 15 control/direction pairs,
  eight physical experiment factors, and three coordinated-control contracts.
- [x] Publish independent `knowledge_applicability` and
  `runtime_evidence_state` axes. Reviewed mechanical possibility can remain
  visible while current measurement is unavailable, contradicted, or blocked;
  it cannot masquerade as a calculated current-run result.
- [x] Make session-bound Dial-In consume the canonical P20/P26/P32/P35/P33/P19
  products and bypass the legacy event-to-mechanism inference, telemetry-row
  history query, and weighted learning-bias ranker. The legacy adapter remains
  available only for unbound capability/fallback use.
- [x] Bind controlled workflow performance truth to a content-addressed physical
  segment set with explicit segment list, circular-scope flag, and independence
  unit. The current one-window contract rejects wrapping and disjoint scopes
  instead of flattening them into a different interval.
- [x] Make the Learning summary diversity-aware: the candidate that owns the
  best discriminator leads, then distinct mechanisms/components are represented
  before catalog-order fill. Static possibilities, current evidence, strongest
  contradiction, evidence debt, and the one exact P19 next move remain visibly
  separate.
- [x] Pin the client to the reviewed 92-effect static bridge registry and exact
  runtime P26/P35 partitions. A coordinated projection rehash cannot swap a
  bridge, direction, experiment factor, mechanism relation, or static component
  map. Authorized public actions and Crew terminal decisions require the same
  complete semantic identity as P19.
- [x] Repair normal CI policy: Ruff is version-pinned, every job uses an isolated
  database, the push/PR gate includes a nonempty integration slice plus Vitest,
  TypeScript, production build, and synthetic trust, and main adds the complete
  Python suite. The protected real-`.ibt` release job also uses an isolated
  database. A new remote SHA is not called green until these workflows pass after
  a future push.

### P35.2 release validation - VERIFIED LOCALLY 2026-08-16

- Whole repository: the isolated no-bytecode run collected 2,723 Python tests
  and completed with 2,714 passed, nine protected skips, and zero failures in
  267.606 seconds. Whole-repository Ruff and diff integrity passed.
- Trust and integration: the permanent synthetic trust audit passed, including
  exact directional pairs, order independence, P26 relevance partitions,
  semantic-role separation, legacy-path bypass, physical-scope rejection, P19
  equality, and compiler-to-client registry parity.
- Frontend: the executable Intelligence, Dial-In, and Crew hostile guards passed;
  TypeScript reported zero errors; all 30 Vitest behaviors passed; and the
  production build completed with 2,208 modules.
- Remote status: production `main` at `a9b1d3799e0756eb487aac648d7f683b24bdb0ac`
  remains the previously failing Actions SHA. These local repairs are not labeled
  remotely green until they are intentionally committed/pushed and the new exact
  SHA completes Actions successfully.

## P35.3 - Inner Crew Chief Cognitive Closure

- [x] Make every advertised inspection tool either reachable for the current
  typed subgoal or explicitly non-executable with its missing inputs and skip
  reason. Required context, the strongest contradiction, exact P35.1 mechanism
  knowledge, and exact P19 control/experiment factors cannot disappear behind a
  broad artifact cap or a nonexistent producer.
- [x] Replace scheduled-tool coverage with exact cause cognition. Causes now
  distinguish not inspected, requested, inspected without evidence, supported,
  contradicted, discriminator pending, unresolved after inspection, and exact
  P19 ruled-out state. Only a typed request/result/artifact/cause relationship can
  advance current coverage; historical P34 markers remain readable but inert.
- [x] Persist a complete deterministic cognitive trace: problem interpretation,
  hypothesis registration, request, typed result and selection receipt,
  hypothesis inspection, contradiction, subgoal completion, critique, driver
  dialogue, and terminal decision. One bounded `advance-until-boundary` operation
  performs safe mandatory work and stops at a driver, evidence, traffic, stale,
  blocked, or terminal boundary.
- [x] Give the critic real `pass`, `blocked`, `reinvestigate`, and `ask_driver`
  outcomes without granting it setup authority. Driver answers carry typed phase,
  transient/steady-state, traffic, stint, power-state, time-origin, and demand
  semantics or are explicitly context-only.
- [x] Freeze an investigation-open consumption baseline and expose only exact
  post-open accepted laps, measurement attempts, requests/durations, questions,
  continue actions, and workflows for the future P36 campaign. P34 v1 outcome
  certificates and promotion rules remain unchanged, and P19 remains the sole
  cause, experiment, setup, and terminal-action authority.

### P35.3 release validation - VERIFIED LOCALLY 2026-08-17

- Whole repository: 2,734 Python tests were collected; 2,729 passed and five
  protected tests skipped, with zero failures. The frozen P34 suite and 11
  dedicated P35.3 cause, driver, critic, selection, persistence, and compatibility
  tests passed. Whole-repository Ruff and diff integrity passed.
- Frontend: TypeScript reported zero errors, all 30 Vitest behaviors passed, the
  executable Crew trust guard and both real Atlanta public-workspace trust cases
  passed, and the production build completed with 2,208 modules.
- Operational proof: a persisted Atlanta workspace opened exact P19 hypotheses,
  completed mandatory data-quality and lap-context inspections, recorded typed
  support and consumption events, stopped at the traffic boundary, and preserved
  the underlying P19 decision while the Crew presentation failed safe.
- End-to-end polish: typed driver scope now changes the next physical inspection,
  persisted critique must equal reconstructed critique, server and client both
  enforce ordered eligibility plus exact selection receipts, one driver continue
  action remains one count across restart, and each new typed result records its
  measured execution duration. Learning Mode exposes the active subgoal, evidence
  gate, eligibility, receipt, and post-open consumption without widening authority.
- Remote status: these local changes are not labeled remotely green until they
  are intentionally committed/pushed and the new exact SHA passes Actions.

## P35.4 - Phase-Resolved Vehicle Response and Setup Diagnosis

- [x] Remove the known unsafe nominal-physics paths from production-capable
  helpers. Missing CG height, motion ratio, rolling resistance, air density,
  wind/heading, grade, engine force, and power components now make the dependent
  quantity unavailable instead of selecting 0.30 m, 1:1, 0.015, sea-level air,
  ground speed, flat grade, zero loss, or a partial wheel-power sum.
- [x] Keep steering and platform semantics truthful. `SteeringWheelAngle` remains
  driver steering-wheel demand and cannot create road-wheel steer, front slip
  angle, Ackermann error, or understeer-gradient claims. Ride-height angles
  require source-backed motion ratios; the mixed-axle whole-car roll estimate is
  removed while direct height states remain available.
- [x] Stop fixed tire-temperature and slip thresholds from publishing thermal or
  usage causes. I/M/O, pressure gain, pit-boundary carcass/wear snapshots, tire
  distance, and slip-like exposure remain descriptive; a cause class now requires
  future same-car/build/track/age/weather residuals and independent repetition.
- [x] Add immutable `PhaseResponseMetric`, `VehicleResponseObservation`,
  `VehicleProblemSignature`, and `MechanismSeparationRow` contracts. One exact
  P32 phase/window now records measured time, driver-demand deltas, yaw/speed/
  acceleration/line response, onset at the resolution actually known,
  transient-versus-steady regime, persistence, source/reference lap identity,
  context blockers, strongest contradiction, candidate support, missing evidence,
  discriminator, protected countereffects, and component-family relevance.
- [x] Wire the response/signature layer through the existing P35 assessment and
  Crew workspace without adding a raw-telemetry reader or authority path. P20
  remains the observation owner, P32 owns elapsed time and driver-versus-car
  separation, and P19 remains the only cause, exact test, setup, Keep/Undo/Retest,
  and terminal authority. Force-like, nominal-geometry, aero, Ackermann, and
  slip-angle proxies are rejected from positive P35 mechanism support.
- [x] Extend the existing Race/Learning presentation rather than add a tab. Race
  Mode can state measured phase time, phase-boundary onset, driver-demand state,
  vehicle-response state, leading candidate, and contradiction in one compact
  line. Learning Mode adds a phase-resolved car-state card, native-unit response
  metrics, and an auditable mechanism-separation matrix; unavailable values stay
  absent rather than rendering as zero.
- [x] Adversarially close coordinated and legacy physics escape paths. Nested
  metric/response/signature IDs are content-addressed; backend and client require
  exact source/reference laps, chain provenance, context/evidence state, metric
  units/semantics, signature truth, and candidate/separation equality. Positive
  support requires matched driver demand, line, changed vehicle response, clean
  context, and no traffic. Missing or invalid motion ratios cannot unlock any
  affected force-like spring/platform/aero proxy; missing yaw cannot become zero
  geometry correction; nonfinite physics stays unavailable; absolute carcass-
  temperature labels and severity coloring are removed; and ground-speed
  pressure values are explicitly non-comparable display proxies, never aero load.
- [x] Add continuous-clock producer contracts for brake-to-four-line-pressure/
  deceleration, brake-release-to-yaw, throttle-to-acceleration/yaw, event-aligned
  four-corner platform/damper settling, and qualified stint migration. Exact
  onset/lag, gain, overshoot, settling, correction, noise-floor, repetition,
  speed, phase, physical-scope, source, and clock fields remain observation-only;
  unavailable measurements never become numeric defaults.
- [ ] Promote additional ARB, differential-preload, tire-pressure, damper-row,
  and alignment controls only after those measurement contracts earn exact
  response evidence. P35.4 adds no new setup direction or adjacent legal value.

### P35.4 local verification - 2026-08-17

- The complete repository collected 2,754 Python tests and finished with 2,749
  passed, five protected skips, and zero failures. The previously timing-sensitive
  P33 10,001-record gate passed inside the monolithic run. Whole-repository Ruff,
  changed-file bytecode compilation, and diff integrity passed.
- Hostile coverage includes raw steering versus road-wheel semantics, missing or
  invalid motion ratios, incomplete force/power balance, ground-speed aero
  overclaim, fixed tire thresholds, pit-snapshot classification, missing yaw,
  nonfinite constants, nested-ID drift, unit/semantic swaps, source/reference lap
  swaps, foreign chain sources, signature drift, candidate/separation drift,
  traffic, driver/line changes, carried losses, and setup-authority smuggling.
- The real persisted Atlanta integration remained measured and traffic-blocked,
  preserved zero positive mechanism support and zero setup authority, reread no
  lower telemetry, and passed cold/warm deterministic replay plus coordinated
  payload attacks under the stricter backend contract.
- TypeScript, all 31 Vitest behavior/unit tests, both executable Crew/P35 client
  trust programs, focused frontend contracts, and the 2,208-module production
  build passed. The build retains the existing large-main-chunk advisory; no
  warning threshold was weakened and no packaging work was added to this physics
  milestone.

## P35.4.1 - Canonical Telemetry Truth Closure

- [x] Make the physical alignment grid immutable. Brake, throttle, steering,
  yaw, and platform response annotate driver-event correspondence but cannot
  translate physical position; only qualified GPS/road landmarks may correct it.
- [x] Make one full source SHA-256 one recording. Imports reuse content-addressed
  artifacts, aliases remain auditable but cannot count independently, every
  Compare route rejects `SAME RECORDING`, and A/B/A2 plus durable learning require
  complete distinct source identities.
- [x] Establish one qualified telemetry clock. Contiguous integer `SessionTick`
  plus the declared rate owns decision timing; `SessionTime` remains preserved
  corroboration and a degraded clock cannot make a lap or UI decision eligible.
- [x] Remove nominal diffuser geometry. Missing wheelbase, track width, or
  rub-block correction makes all dependent fields unavailable; reviewed-profile
  output remains an explicitly calculated proxy and manifest/cache schema v6
  prevents stale nominal values from surviving migration.
- [x] Replace warning-prose decisions with typed engineering blockers whose
  explicit target axes prevent a traffic-blocked resistance mechanism from
  poisoning valid pace, platform, stint, map, or navigation observations.
- [x] Classify all 62 audited unmapped channels by engineering role and admission
  authority. Simulator lap values corroborate timing only; per-corner tire
  counters remain pit snapshots; unknown future signals remain inventory/debug.
- [x] Restore Learning-only **Telemetry Capabilities**, support one custom
  observation-only chart lane, reduce Platform to question-owned channel
  projections, and execute chart tests for gaps, proxy styling, exact physical
  scope, and extrema preservation.

### P35.4.1 verification - 2026-08-18

- The definitive collection contained 2,839 Python tests: 2,836 passed, three
  DuckDB-dependent tests remained intentionally skipped, and zero failed. The
  repaired adversarial boundary passed 214 focused hostiles; all 165 tests that
  exposed legacy fixture/migration incompatibilities then passed together.
- All 38 Vitest behavior tests, TypeScript, the 2,209-module production build,
  entry/chunk/CSS bundle budgets, whole-repository Ruff, and diff integrity passed.
- The protected real Atlanta audit re-imported 26,556 records, archived 277/277
  declared channels, and retained schema fingerprint
  `5565017159206c0b2f4407add6f97b66dfcd28b38c3ded62a78899b5428441af`.
- Live 1,280-pixel and 390-pixel Race/Learning checks had no document overflow,
  browser warnings, or console errors. Cold whole-car awareness completed inside
  its intelligence timeout; pit snapshots could not open continuous lanes; an
  admitted custom lane retained unit, proxy, physical-scope, and no-authority truth.
- Adversarial review and regression now cover driver-input alignment warping,
  far-apart response clustering, duplicate/unknown recording identity, foreign
  response clocks and telemetry, SessionTime-only eligibility, unbound stint
  sources, unsupported diffuser constants, typed blocker scope, pit-only channel
  semantics, legacy clock migration, and setup-authority smuggling. P19 remains
  the sole cause, exact test, setup, Keep/Undo/Retest, and terminal authority.

## P35.4.2 - Response-to-Mechanism Operational Integration

- [x] Carry the already-built brake/throttle response report through the shared
  intelligence snapshot and bind qualified four-line-pressure, brake-release,
  yaw, acceleration, lag, gain, overshoot, settling, correction, speed-band,
  and independent-lap evidence into the current P35 assessment.
- [x] Run the four-corner disturbance producer only when the leading P32 scope
  names a disturbance/platform mechanism. A disturbance-compliance row may
  reference the response only after two independent eligible laps repeat at the
  same exact physical location and context.
- [x] Build stint response migration from the same verified observation read and
  exact opportunity windows. `stint_dependence` becomes `observed_migration`
  only when at least ten consecutive clean same-setup laps clear the producer's
  robust trend and empirical-noise gates.
- [x] Add an immutable `OperationalResponseEvidence` projection. It can refine
  canonical-clock onset, observed speed-band scope, repeated-surface scope, and
  four-corner scope, but remains observation-only and cannot become P19 support,
  component cause, setup direction, or terminal authority.
- [x] Add Learning-only quantitative response details under the existing
  Blackboard: BRAKE -> PRESSURE, RELEASE -> YAW, THROTTLE -> ACCELERATION,
  DISTURBANCE -> CHASSIS, and lap-by-lap STINT MIGRATION. Race Mode and the tab
  model remain unchanged.
- [ ] Promote ARB, differential-preload, tire-pressure, damper-row, or alignment
  controls. These remain evidence-locked; P35.4.2 adds no legal target or setup
  authority.

### P35.4.2 verification - 2026-08-18

- The complete 3,326-test Python repository regression passed after the exact no-lap run
  boundary was made fail-closed. The dedicated five-test hostile slice proves
  four-corner brake-pressure completeness, missing-corner denial, repeated
  physical disturbance identity, ten-lap stint/noise gating, and strict
  separation between response evidence and candidate support.
- Observation, persisted-snapshot, intelligence API, Crew Chief, P35, OpenAPI,
  Python/client contract, and exact-authority focused suites passed together.
  Whole-repository Ruff, TypeScript, Learning behavior tests, production build,
  bundle budgets, and diff integrity passed.
- The production UI built 2,228 modules. Entry remained 191.10 KB raw / 52.55 KB
  gzip and the new quantitative evidence stayed inside the existing Learning
  Blackboard rather than adding a workspace or initial-shell dependency.
- Field evidence remains honestly unearned: historical 0/9, null stints 0/10,
  negative controls 0/8, subgroups 0/9. Null Session 01 and a real P19 A/B/A2
  outcome still require new driving and are not credited by this software slice.

## P35.5 - Field-Ready Alpha Hardening

- [x] Bound the current decision product to an honest NASCAR Next Gen oval alpha.
  Other telemetry remains available for lossless archival inspection and fails
  closed outside exact reviewed car/build/track applicability.
- [x] Remove probability-shaped UI language from uncalibrated evidence. Event,
  comparison, Notebook, damper, alignment-quality, and engineering scores render
  as ordinal strength out of 100; measured coverage remains a percentage.
- [x] Make one canonical next move singular. Priority and Overview handoffs are
  explicitly supporting evidence navigation, and the shell reads only a compact
  exact-identity cached projection that never starts cold intelligence.
- [x] Simplify first use to Import -> one trustworthy move -> one graded mission.
  Returning drivers resume the last exact session without a mandatory splash;
  continuous 0-100% lap playback, per-run/lap zoom persistence, evidence-debt
  grouping, setup-focus handoff, and test-discipline factors support inspection.
- [x] Make desktop ownership exact. The official Tauri single-instance plugin
  focuses the first window; a per-process backend identity blocks attachment to
  another service; an owned sidecar exit is detected and restarted; normal close
  terminates the owned process tree.
- [x] Make delivery reproducible and reviewable. Python, Node, and Cargo inputs
  are locked; OpenAPI and TypeScript contracts are generated together; Vite,
  ECharts, and direct dependencies pass the advisory gate; PR CI adds Playwright,
  Cargo, API-drift, dependency, and tightened bundle gates.
- [x] Expand release truth beyond archive counts. The protected real fixture now
  proves qualified SessionTick, useful-lap/junk exclusion, evidence-linked events,
  frame-native import, and the expected context-blocked setup-attribution no-call
  before Tauri installers are built and smoked.
- [x] Reduce cold duplicate work without weakening producers. Observation rows
  are bound in place, P3 consumes only the eligible cohort, and canonical phase
  labels are computed once per eligible lap. Full Engineer vectorization remains
  open, but ordinary run open no longer pays that construction cost.
- [ ] Earn Null Session 01 and one real source-owned P19 A/B/A2 outcome.
  **FIELD DATA REQUIRED:** implementation and synthetic validation cannot create
  the independent driving sessions required by P23/P36.

### P35.5 verification - 2026-08-18

- Current Python collection: 2,850 tests. The definitive 2,847-test run passed
  with three protected skips and zero failures; the three subsequently added
  manifest, zoom, and persisted-snapshot contracts passed in focused closure suites.
- Frontend: 43 Vitest behaviors, TypeScript, two Chromium first-use flows, the
  2,228-module Vite 8/ECharts 6.1 production build, tightened entry/CSS/chunk
  budgets, zero npm advisories, and generated API drift checks passed.
- Delivery: Cargo locked check, optimized Tauri build, MSI and NSIS bundles, and
  packaged single-instance/backend-identity/normal-shutdown smoke passed.
- API: generated OpenAPI 3.1 contains 88 paths, 96 operations, and 361 schemas;
  the TypeScript declaration projection regenerates without diff.
- Performance: uncached shell projection measured 13.173 ms with intelligence
  build count remaining zero; cached shell projection measured 28.376 ms. The
  full Atlanta Engineer cold path improved from a 13.426 s local pre-optimization sample
  to 12.226 s in this pass and remains explicit vectorization debt, not a closed
  first-construction 2.0 s claim. Digest-verified exact-semantic restart reuse
  measured 104.327 ms with the reasoning snapshot unchanged and zero fresh build
  count. The entry bundle fell from 450.99 KB to 191.10 KB raw.
- Security/truth: ordinal scores no longer render as probability percentages;
  README slip-angle/understeer scope matches runtime; decoder fallback provenance
  is typed and visible; manifest reduction failures become `not_assessed`; schema
  migrations are checksum-bound and fail closed on tamper or newer history.

## P36 - Prospective Investigation Evidence Campaigns

- [ ] Run the preregistered prospective campaigns needed to test whether learned
  investigation ordering earns promotion. **DATA LOCKED:** P35 builds the car
  expert; it does not manufacture the independent real investigations, recurrence,
  negative controls, subgroup coverage, or observable comparisons required by the
  frozen P34 activation protocol.
- [ ] Admit a learned-order promotion only from source-owned prospective evidence
  that satisfies the existing P21/P22 acquisition rules and P34 safety/rollback
  gates. Until then production remains deterministic baseline, P33 remains
  attention-only, P34 remains shadow-only, and P19 remains sole setup authority.

---

## Professional analysis surface, without losing the product thesis

- [x] Match essential professional language: time variance, overlays, math
  channels, maps, histograms, PSD, synchronized comparisons, cursor statistics,
  metrics, and reports.
- [x] Keep RacerZLab differentiated through automatic evidence assembly, truth
  contracts, cause separation, one controlled next test, keep/undo/retest, setup
  context, measurement missions, and persistent response memory.
- [x] Do not add graphs that do not improve a decision or its auditability.

## Permanent trust rules

- [x] Treat this section as acceptance criteria for every release.
- Never call a proxy measured downforce.
- Never call total resistance exact aerodynamic drag.
- Never convert missing telemetry to zero.
- Never treat a complete lap as automatically eligible.
- Never recommend a damper regime without shaft-velocity evidence.
- Never recommend tire pressure from one temperature reading.
- Never attribute driver improvement to setup.
- Never infer universal setup limits from one setup.
- Never treat telemetry rows as independent setup tests.
- Never train a setup model on uncontrolled comparisons.
- Never hide contradictory evidence.
- Never produce many simultaneous major changes.
- Never silently discard newly introduced iRacing channels.
- Never imply one best setup exists for every race objective.
- Never implement unsafe live manipulation, input automation, cheating, or
  behavior that violates iRacing rules.

Enforcement status: the named synthetic trust audit runs in CI, and the release
workflow requires a protected, identity-pinned real `.ibt` fixture. Repository/tag
protection or the packaging workflow must require that job before publication;
that external GitHub setting is documented but cannot be verified from source code.

## Immediate next work queue

Implementation queue completed in this pass:

1. [x] Replace client-asserted P4/P5 decisions with server-derived run, lap,
   setup, event, driver, context, and integrity assembly.
2. [x] Wire complete persisted A/B/A2 execution, scoring, rollback, and certificate
   surfaces into Dial-In.
3. [x] Turn Active Reset attempt grouping into a guarded repeatability laboratory.
4. [x] Complete measured grade context, powertrain diagnostics, distance-first
   tire-life curves, and fail-closed production pit-window logic.
5. [x] Add nonlinear response memory, interaction admission, exact build/context
   isolation, and observed legal/tech-passing envelopes.
6. [x] Complete automatic server-side opportunity and symptom assembly.
7. [ ] Collect and audit enough real controlled history to evaluate the P7 unlock;
   DOE/search production routes remain locked until the threshold is truly met.
8. [x] Unify Dial-In capability truth, observed-mechanism evidence, selected
   decision context, transparent ranking, exact-context response memory, and
   driver-facing decision kinds.
9. [ ] Collect held-out controlled outcomes for P8 score calibration and formal
   competing-cause evaluation; do not relabel ordinal evidence as probability.
10. [ ] Collect frozen same-setup and controlled histories for P14 detector,
    alignment, and prediction calibration; keep formal information gain,
    hierarchical transfer, and multi-control optimization locked until their
    stated validation thresholds are met.

## Roadmap update log

| Date | Change | Evidence |
|---|---|---|
| 2026-08-03 | Created roadmap from the supplied telemetry-evolution blueprint | Blueprint mapped into P0-P7 and permanent trust gates |
| 2026-08-03 | Marked verified universal-telemetry work complete | 277/277 real-file channel archive, 360 Hz sub-tick preservation, full tests and lint |
| 2026-08-03 | Hardened P0 compatibility, health, and transactional archive promotion | 29 focused P0 tests and Ruff passed; real Atlanta audit found 277/277 complete channels, zero false health faults, contiguous ticks, complete car/track/build/session identity, every advertised alias materialized, and no redundant raw namespace columns |
| 2026-08-03 | Added the shared evidence-contract foundation and first relative-resistance contract | 18 targeted contract tests and Ruff passed; prohibited-output tests cover measured CdA, exact drag force, and exact horsepower loss |
| 2026-08-03 | Hardened causal comparison and single-run tuning gates | Nearby-car context preserves observed speed but withholds setup credit; missing/sparse evidence no longer becomes a neutral gain; localized CFS compression, tire units, setup-tree changes, and junk-lap action paths gained regression coverage; real Atlanta vector archive is 26,556 x 539 |
| 2026-08-03 | Closed adversarial traffic/segment edge cases | Proximity warnings now describe only observed context; row/vector segment deltas use track-ordered median endpoint bands; live and persisted analysis share one segment model; full Python suite, focused Ruff, UI typecheck, and diff checks pass |
| 2026-08-03 | Verified P0-P3 evidence/alignment/engineering backend slice | Focused tests cover universal telemetry, evidence contracts, phase/time alignment, ten P3 systems, API registration, comparison integrity, and UI type contracts; Ruff and TypeScript checks pass |
| 2026-08-03 | Closed adversarial P3 eligibility and attribution bypasses | Hostile regressions cover useful-tagged pit laps, confidence-cap propagation, one-change ranking, damper repeatability, cohort integrity, exact common-position A/B/A matching, missing/mismatched context and discriminators, unmapped setup changes, three-run compatibility, phase gaps, false limiter evidence, repair/refuel/tire boundaries, and active-stint fuel range |
| 2026-08-03 | Audited P4-P7 truth status | Backend planner/packet/memory/DOE primitives are tested; client-asserted production routes and data-dependent experimentation remain explicitly LOCKED and unchecked |
| 2026-08-03 | Completed whole-product adversarial polish and robustness pass | Full 1,172-test suite passed with four fixture skips; reachable UI reviewer returned CLEAR; percentage/ratio quality, paired clocks, finite-value caps, ordered stint fuel math, redline validation, per-corner tire/shock evidence, warning classification, recovery states, wind units, keyboard access, bundle splitting, and launch-asset weight gained regression coverage |
| 2026-08-04 | Completed the P3-P7 implementation roadmap and adversarial release pass | 1,253 tests collected: 1,249 passed and four environment-dependent skips; 181 named synthetic trust tests and whole-repo Ruff passed; TypeScript and production UI build passed; pinned Atlanta audit passed at 26,556 records, 277/277 declared channels, and schema `5565017159206c0b2f4407add6f97b66dfcd28b38c3ded62a78899b5428441af` |
| 2026-08-04 | Closed final adversarial decision and import faults | Retest scoring persists without crashing; mixed-sign A/B/A2 effects cannot enter memory; every core declared alias reaches production normalization; all simple row/vector aliases have parity and value tests; Active Reset fails closed on missing/hostile integrity context; downloadable controlled-test certificates preserve reproduction evidence |
| 2026-08-04 | Hardened shock slope decisions and presentation | Same-zone two-lap repetition, continuity, car-owned boundary selection, plus/minus 25% sensitivity, moving-sample deadband math, adjacent-option-only slope tests, explicit action/effect/size/keep/undo wording, and UI/API/CLI parity passed focused adversarial tests, Ruff, TypeScript, and the production build |
| 2026-08-05 | Unified Dial-In recommendation intelligence | Capability and observed evidence are structurally separate; selected zone/phase/objective/priority reach the server; list-position scoring was removed; exact-context models can suppress contradicted directions; recommendation score provenance is included in the controlled-test report; focused backend/UI contracts, Ruff, and TypeScript passed |
| 2026-08-05 | Closed adversarial P8 authorization and scoring gaps | Candidate-specific event/mechanism linkage, selected-scope containment, exact-control memory isolation, objective-sized measurement missions, immutable score-time A/B/A2 setup validation, multi-control fail-closed behavior, persisted UI context, and context-mismatch action gating gained regression coverage |
| 2026-08-05 | Hardened production A/B/A2 certification and physical guardrails | Consecutive post-warmup cohorts, file-owned recording chronology, repeated noise floors, six-lap sign states, complete non-target alignment, control-specific platform/cooling/gearing/brake guardrails, hostile platform numeric gates, durable rollback provenance, and fully rendered score distributions passed 1,353 tests with four environment-dependent skips, whole-repo Ruff, UI typecheck/build, diff integrity, and a final adversarial CLEAR review |
| 2026-08-08 | Completed the P9 whole-app performance pass | Real Atlanta direct import improved about 80-83% with exact 277-channel manifest parity and about 55% lower peak memory; warm reads, trace payloads, alignment lookups, track-map rendering, and UI delivery were reduced without weakening canonical contracts; the corrected tree passed 1,385 Python tests with four environment-dependent skips, Ruff, TypeScript, production build, browser smoke, and a final adversarial CLEAR review |
| 2026-08-08 | Verified P10 evidence integrity and resilience | Hostile context, provenance, persistence, cache-mutation, endpoint, and stale-UI regressions passed; 1,499 tests were collected with 1,495 passing and four protected fixture skips; Ruff, TypeScript, production build, browser smoke, and two independent CLEAR reviews passed |
| 2026-08-08 | Completed P11 decision-first desktop UX | Responsive Race/Learning surfaces, exact workflow/session identity, seven-column stint decisions, progressive Platform/Setup/Dial-In disclosure, legacy junk-lap requalification, evidence-trust fallbacks, keyboard access, and 1280 x 720 layouts passed 1,525 collected tests with four protected skips, Ruff, TypeScript, production build, browser smoke, and independent integrated plus accessibility CLEAR reviews |
| 2026-08-08 | Completed P12 internal engineering intelligence | Evidence graph, ordinal cause comparison, one evidence-qualified next measurement, grounded exact-scope questions, immutable engineering memory, honest calibration counts, presentation-only personalization, and the Race/Learning Smart Engineer workspace passed 1,666 collected tests with four protected skips, Ruff, TypeScript, production build, 1280 x 720 browser smoke, and an independent release CLEAR review |
| 2026-08-08 | Completed P13 cross-tab decision broadcasting | Six decision-first workspace broadcasts, shell/tab truth parity, exact scope handoffs, durable one-workflow authority, telemetry artifact ownership, stale-zone clearing, responsive recovery, and human Race Mode labels passed 1,740 collected tests with six protected skips, Ruff, TypeScript, production build, 1280 x 720 checks, and independent tab-content plus final adversarial CLEAR reviews |
| 2026-08-08 | Completed P14 evidence compounding and adaptive engineering | Typed mechanism observations, repeatable physical-position opportunities, robust anomalies, driver coaching, exact-context session ledger and hypothesis lifecycle, blocker-aware measurement guidance, telemetry-health comparison, observational stint state, adaptive smart cards, and scoped questions passed 1,877 collected tests with six protected skips, Ruff, TypeScript, production build, fresh-process 1280 x 720 browser checks, and independent backend plus UI adversarial CLEAR reviews; calibrated probability, formal information gain, hierarchical transfer, and optimization remain data-locked |
| 2026-08-08 | Completed P15 premium race-engineering experience polish | Premium launch/import/session flow, exact shell readiness, comparative workspace briefings, Smart Engineer and Dial-In mission progress, honest recovery, keyboard-safe focus, accessible duplicate-session context, and responsive 1280 x 720 presentation passed 1,904 collected tests with six protected skips, Ruff, TypeScript, production build, diff integrity, live Race/Learning checks, and independent adversarial CLEAR review |
| 2026-08-08 | Completed P16 premium telemetry visualization | Open telemetry canvases, truthful pace/delta/Platform line hierarchy, honest gaps, active-metric cues, dashed proxy identity, exact units, stale-safe comparison responses, and keyboard sample inspection passed 88 focused chart checks, 227 broad frontend/performance checks, Ruff, TypeScript, production build, diff integrity, live 1280 x 720 Race/Learning inspection, and an independent adversarial CLEAR review |
| 2026-08-08 | Completed P17 oval driver operating system | Driver-first clean-run readiness, short-versus-race pace, uninterrupted RF/RR evidence, clean-lap ledger, oval setup anchors, entry/center/exit/carry crew board, exact-sample checkpoint, and the Laps-hosted whole-car workbook passed 1,947 collected tests with six protected skips, Ruff, TypeScript, production build, diff integrity, live 1280 x 720 Race/Learning checks, and a final adversarial CLEAR review |
| 2026-08-09 | Completed P18 deterministic reasoning and controlled learning | Independent evidence tiers, exact controlled-outcome semantics, physical-window semantic repeat memory, blocker-aware measurement planning, typed mind-change criteria, exact grounded-query scope, centralized repeat enforcement, and one fail-closed API/UI Stage B authority projection passed 2,063 collected tests with six protected skips, Ruff, TypeScript, production build, diff integrity, and three independent adversarial CLEAR reviews |
| 2026-08-09 | Verified RacerZLab Intelligence Spine / Closed-Loop Reasoning Foundation | Canonical reasoning snapshots, backend-owned signed evidence graphs, independence clusters, Next Gen per-lap channel semantics, immutable mission contracts, append-only restart-safe attempt history, durable stop reconstruction, typed comparability debt, tolerant event lifecycle, and fail-closed cross-session Undo memory passed the complete 2,073-test collection with six protected skips, Ruff, TypeScript, production build, and diff integrity; statistical authority remains data-locked |
| 2026-08-09 | Verified P20 deterministic engineering-awareness production slice | Producer-owned state frames, context/control boundaries, source-backed profiles, descriptive transient/exposure metrics, temporal episodes, exact P19 projection, bounded API cache, and six stale-safe existing-workspace surfaces passed the complete 2,134-test collection with six protected skips, Ruff, TypeScript, production build, diff integrity, and a real Atlanta schema/capability route check; state drift remains typed unavailable until a canonical numeric ledger is attached, while shadow observers and statistical authority remain data-locked |
| 2026-08-10 | Verified P21 Evidence Lab, Calibration, and Shadow Intelligence foundation | Immutable evidence registries, frozen split/evaluation identity, hostile leakage detection, seven collection campaigns, bounded proxy/profile validation, prospective shadow records, causal/planner evaluation, thirteen activation gates, and Learning-only readiness passed 2,182 tests with six protected skips, Ruff, TypeScript, a 2,189-module production build, diff integrity, performance checks, and live Race/Learning smoke; the archive contains no qualified controlled population, so P19/P20 remain authoritative and advanced statistical methods remain locked or shadow-only |
| 2026-08-10 | Verified P22 prospective field-validation operational foundation | Frozen campaign lifecycles, import-time exact qualification, immutable pre-outcome P19 predictions, canonical later outcomes, deterministic collection guidance, cloned field gates, and the Learning Ledger passed the 2,201-test collection with six protected skips, Ruff, TypeScript, a 2,189-module production build, diff integrity, and live Race/Learning smoke; no real evidence campaign or advanced activation is claimed, so P19/P20 remain authoritative |
| 2026-08-10 | Completed P23 first-earned-capability audit with no activation earned | All 15 P21/P22 candidates were ranked; the deterministic exact-FFB steering-workload envelope was selected and frozen under immutable protocol `p23p-7039505728f07034d6f5`; the empty qualified archive correctly produced no authority envelope. Twenty-six hostile focused regressions and the complete 2,209-test collection passed with six protected skips, plus Ruff, TypeScript, the 2,189-module production build, diff integrity, live Race/Learning smoke, and real-archive latency checks; P19/P20 authority remains unchanged |
| 2026-08-10 | Polished and re-verified P24 evidence acquisition operations; P23 collection remains at zero | Protocol-bound immutable certificates, lap flight recorders, steering truth audits, bounded history/preview contracts, direct certificate retrieval, typed negative-control discovery, accessible Learning-only campaign gates, source duplicate protection, fact-only checklists, and five collection templates passed 91 focused P21-P24 regressions and the complete 2,225-test collection with six protected skips, changed-file Ruff, TypeScript, the 2,189-module production build, diff integrity, and live Race/Learning smoke; a whole-repo Ruff audit truthfully retains 1,026 inherited findings outside P24, the archive remains inventory, profile truth is incomplete, prospective collection is locked, and P23 remains shadow-only |
| 2026-08-10 | Verified P25 acquisition pilot; no qualified session earned | A source-owned 63,657-record Next Gen Atlanta re-import proved source/cache/schema ownership, all ten steering signals, contiguous 360 Hz sub-tick reconstruction, exact FFB/73 mm-rev identity, a 33-lap immutable recorder, duplicate-source resistance, and a pre-outcome null run card; all 29 otherwise useful laps were traffic-contaminated, so certificate `p24c-36d0f278b166d6f8bb36` admitted nothing and P23 counts remained zero. Ninety-four focused P21-P25 regressions and all 2,228 collected Python tests passed (2,223 passed, five protected skips), plus changed-file Ruff, TypeScript, the 2,189-module production build, diff integrity, and live Race/Learning smoke; Learning Readiness was reduced from about 6.2 seconds to about 121 ms by reusing the frozen operation context, and P23 remains locked and shadow-only |
| 2026-08-10 | Corrected and polished conventional turn placement across every oval map | Canonical section and centerline geometry now produces T1-T4 anchors for all standard ovals and truthful T1-T3 for Pocono, while road/roval maps remain untouched and tri-oval frontstretch bends cannot become fake Turn 5-7 labels. Scale-aware outward labels and leader lines remain readable without covering the racing surface. The real 82-map audit verified 43 oval layouts with zero violations; Pocono and Talladega regressions, all 2,232 collected tests (2,227 passed, five protected skips), changed-file Ruff, TypeScript, the 2,190-module production build, diff integrity, and live Atlanta T1-T4 overlay inspection passed |
| 2026-08-10 | Unified oval map regions with Smart Engineer location awareness | All 171 oval turns now expose bounded entry/center/exit regions backed by section geometry or centerline fallbacks; every anchor resolves to its own region center, public packages and 82 migrated local caches are vendor-neutral, and grounded AI citations carry the same canonical location without gaining setup authority. The 82-map/43-oval audit had zero violations; all 2,233 tests passed (2,228 passed, five protected skips), plus targeted Ruff, TypeScript, the 2,190-module production build, diff integrity, and a real Atlanta package check |
| 2026-08-10 | Re-verified oval geometry and made regions native Smart Engineer scope | The independent centerline audit proved all 171 bounded turn regions across 43 oval layouts contain measurable direction change, consume plausible lap area, and retain center-phase anchors. Canonical non-overlapping gaps now add 86 Front/Back stretches plus five real Indianapolis/Pocono connectors, and all 82 map payloads are continuously checked for vendor-neutral output. Smart Engineer parses turns, T-number shorthand, stretches, connectors, and entry/center/exit; it filters evidence by physical region, rejects undefined or ambiguous regions, and exposes the interpreted scope without weakening setup authority. The complete 2,238-test collection passed (2,233 passed, five protected skips), plus focused region/API contracts, changed-file Ruff, TypeScript, the 2,190-module production build, zero audit violations, and diff integrity |
| 2026-08-10 | Enforced one greenfield canonical map registry | The mapbase contains exactly 82 index entries, 82 JSON files, 82 map IDs, 82 SHA-256 identities, and zero duplicate track/layout keys, cache paths, or orphan files. Same-byte imports remain idempotent; a changed file with the same canonical track/layout now replaces its prior entry and safely removes only the superseded cache. Track maps now accept only current `track_map_v2`/`mt2` records with one `sha256`; the migration cleanup API, retained-source handling, legacy source variants, and redundant `source_hash`/`source_removed` fields were removed. The zero-violation real-map audit, focused map tests, changed-file Ruff, TypeScript, diff integrity, and the complete 2,238-test collection passed (2,233 passed, five protected skips) |
| 2026-08-10 | Verified P26 Vehicle Systems Intelligence foundation | A source-backed, immutable Next Gen component graph now separates physical parts, garage controls, properties, whole-car states, observations, symptoms, outcomes, context, interactions, unavailable quantities, and one-physical-factor experiments. Runtime awareness projects only P20 observations and P19 controlled history/authority; the real Atlanta run correctly produced an unresolved platform/suspension candidate family rather than four false component causes. Grounded component questions and compact Race/Learning Setup/Engineer surfaces preserve prior Undo and exact authority. The complete 2,250-test collection passed (2,245 passed, five protected skips), plus changed-file Ruff, TypeScript, the 2,191-module production build, OpenAPI inspection, bytecode compilation, real Next Gen projection, and diff integrity |
| 2026-08-10 | Adversarially hardened P26 end to end | Replaced prose word matching with typed cause/control identities; bound public projections to verified compatibility fingerprints and exact Next Gen car/build/oval scope; added snapshot hashes and a closed non-authoritative runtime evidence/history graph; made all Next Gen setup-area mappings explicit; cached graph compilation; typed API contracts; and made the UI reject identity, schema, hash, and authority mismatches. The real Atlanta fixture retained four candidate component families, captured settings, 28 runtime nodes, 26 runtime edges, and zero setup authority. The complete 2,255-test collection passed (2,250 passed, five protected skips), plus Ruff, TypeScript, production build, OpenAPI inspection, bytecode compilation, and diff integrity |
| 2026-08-10 | Closed the P26 greenfield dot-to-dot contract | Removed the remaining split-version assumptions and made one current contract span verified telemetry ownership, exact Next Gen applicability, all 50 engineering areas, explicit area-to-property semantics, independently scoped P20 observations, exact P19 history and per-control Undo, grounded component questions, canonical report embedding, workflow-aware refresh, and deep client trust-boundary validation. The current graph compiles 609 nodes and 843 edges with deterministic content identity; the real Atlanta artifact verified full setup capture without causal or setup-authority overclaim. The complete 2,268-test collection passed (2,263 passed, five protected skips), plus changed-file Ruff, TypeScript, the 2,192-module production build, executable runtime guards, OpenAPI inspection, and diff integrity |
| 2026-08-12 | Verified P27-P30 deterministic autonomous Crew Chief operating system | One revision-bound private P19/P20/P26 workspace now owns event-sourced investigations, eight bounded inspections, deterministic critic and driver dialogue, hard Success Contracts, a junk/context-aware Run Sentinel, exact-context component response records, complaint-only driver memory, and an existing-Engineer Race/Learning command deck. Exact setup authority remains an equality-checked P19 projection; the optional generative boundary is disabled and P30 remains data-locked. The complete no-bytecode 2,300-test collection passed (2,295 passed, five protected skips), plus 154 focused authority/Crew Chief/P19-P20-P26 tests, whole-repo Ruff, TypeScript, the 2,196-module production build, bytecode compilation, seven-route OpenAPI inspection, executable synthetic and real-Atlanta UI trust guards, the unchanged 609-node/843-edge P26 graph, and diff integrity. |
| 2026-08-12 | Completed continuous adversarial Crew Chief audit and repair | Twelve material findings were closed across stale authority, driver-dialogue sequencing, A/B/A2 stage ownership, event-tail and redundant-row tamper detection, repository-scoped caching, evidence deduplication, workflow fail-closed behavior, late UI responses, nested response trust, and API bounds. The final 2,316-test collection passed (2,311 passed, five protected environment/artifact skips), plus 159 focused tests with zero skips, whole-repo Ruff, TypeScript, the 2,196-module production build, bytecode compilation, seven-route OpenAPI inspection, real Atlanta execution, the unchanged 609-node/843-edge/50-area P26 graph, and diff integrity. Immutable warm caching reduced real Atlanta Crew Chief assembly from 3,317.595 ms to 148.147 ms; P19/P20/P26/Crew Chief authority ceilings and all data locks remain unchanged. |
| 2026-08-13 | Completed P31 Truthful Crew Loop hardening | Telemetry truth, controlled-experiment identity, segmented evidence, transactional focus, exact Compare provenance, P19-mirrored Crew missions, deterministic investigation, quantity-level P26 observability, shared single-flight intelligence, scoped workflow polling, strict UI trust, and measurement-only research infrastructure passed all 2,338 collected Python tests (2,333 passed, five skipped), 187 focused authority tests, Ruff, TypeScript, three behavioral UI tests, five runtime trust suites, the 2,197-module build, OpenAPI inspection, protected Atlanta regressions, Windows sidecar packaging, and built-UI Atlanta import/Crew/process-restart smoke. Warm Atlanta intelligence is 5.488 ms with one build; the measured 13.195 s cold path remains explicit vectorization debt. P19/P20/P26/Crew authority ceilings and P30/statistical/physics locks remain unchanged. |
| 2026-08-13 | Verified P32 Lap-Time Mechanics and Speed Intelligence | A run-owned empirical performance model now connects qualified driver demand, vehicle response, measured elapsed time, origin/carry, corner chains, track demand, P20 mechanisms, P26 relevance, controlled history, and the exact P19 next move. All 2,361 Python tests passed subject to five protected skips, plus 20 P32 hostile tests, three UI contracts, whole-repo Ruff, bytecode compilation, TypeScript, three behavioral UI tests, five runtime trust suites, the 2,198-module production build, diff integrity, and persisted Atlanta execution. Atlanta produced four measured opportunities, one corner chain, three non-causal component links, full reciprocal-speed coverage, exact P19/P20/P26/P32 identity, zero setup authority, and a data-locked optimizer. |
| 2026-08-13 | Closed P32.1 Performance Truth Closure after reopening P32 | Traffic and unknown context now lead and block attribution without hiding the signed observation; canonical compatibility/proximity gates, complete demand coverage, local disturbance, opportunity-relative carry, exact adjacency/repeatability, P26-independent core intelligence, nine typed Crew tools, restart-safe exact history, and deep client trust prevent a convincing but unsupported speed story. The full collection finished with 2,400 passed and five protected skips, plus the 94-test integrated release slice, 54 hostile truth tests, Ruff, bytecode compilation, TypeScript, five UI behavior tests, the hostile runtime suite, the 2,198-module build, diff integrity, and a real public Atlanta backend-to-client guard. Atlanta exposes `+0.136447 s` observed, blocks attribution at 100% source/reference traffic, publishes zero component/setup authority, measures disturbance at `0.0613`, withholds limiter zones, and remains `no_call`. |
| 2026-08-14 | Verified P33 Engineering Learning Flywheel | One immutable qualified-experience ledger now projects recurrence, contextual driver and car fingerprints, diagnostic effectiveness, exact mind changes, dead ends, transfer/drift, and transparent attention-only Crew memory without modifying current P19 truth or setup authority. The complete 2,514-test collection passed with 2,509 successes and five protected skips, plus 82 dedicated P33 tests, a 336-test integrated authority slice, six runtime trust suites, nine UI tests, Ruff, bytecode compilation, TypeScript, the 2,201-module build, OpenAPI inspection, packaged-sidecar health, persisted Atlanta/EchoPark client guards, and bounded 10,001-record retrieval at 34.303 ms warm / 53.024 ms cold projection / 7.197 ms cached. Corrupt history now records a visible blocked capture without vetoing P19 or Crew terminal truth; ordered request/completion evidence and normal event-hash revision advancement cannot fabricate or erase discriminator credit; all adaptive, causal, probabilistic, generative, and multi-control authority remains locked. |
| 2026-08-14 | Sharpened the P33.1 driver-facing truth and interface | Race Mode now leads with one P19 next move and a compact signed Speed Story; supporting analysis is deliberate, Learning Mode avoids empty-memory sprawl, evidence links use lap/window/state labels, and the Run Sentinel distinguishes context screening from server-verified acquisition under a canonical client-verified digest while keeping the client-attested outcome non-authoritative. Contract acceptance now fails closed on typed P19 proximity or traffic exposure, warning/partial required channels, and missing or spatially gapped physical-position coverage. The full 2,527-test Python collection passed with five protected skips, plus 12 Vitest tests, six runtime trust suites, Ruff, bytecode compilation, TypeScript, the 2,201-module build, OpenAPI inspection, persisted Atlanta/EchoPark client guards, and live desktop plus 390 x 844 EchoPark inspection. The narrow unresolved Priority Rail is dismissible by button or Escape, stays dismissed across mode changes, and retains an accessible evidence-attention trigger without weakening the mandatory desktop rail or any P19/setup authority boundary. |
| 2026-08-15 | Verified P34 earned-investigation shadow evaluation; no attention activation earned | Three immutable planner policies and one preregistered protocol now freeze baseline-versus-memory decisions on identical pre-outcome Crew/P19-P33 truth, persist outcome/counterfactual/discriminator/control/transfer evidence, evaluate independent investigations and complete negative controls, and permit at most one same-tier attention move only after a server-owned gate. The empty real archive truthfully leaves production deterministic and memory shadow-only with exact collection deficits. All 2,620 Python tests passed subject to nine protected skips, plus 54 dedicated P34 tests, 84 runtime hostiles, 17 UI tests, Ruff, bytecode compilation, TypeScript, the 2,202-module build, 10,000-investigation bounded/zero-telemetry performance, OpenAPI, packaged health, real Atlanta truth, live Race/Learning containment, and an independent backend adversarial CLEAR. |
| 2026-08-15 | Verified P35 Next Gen Oval Vehicle Dynamics Intelligence | A content-addressed, build-applicable Next Gen oval physics graph now connects driver demand, tire/load/platform response, candidate mechanisms, typed evidence requirements, and measured P32 time while P19 remains the sole cause and setup authority. The definitive 2,694-test collection passed with 2,685 successes and nine protected skips, plus 34 core hostiles, 30 runtime/Crew checks, an independent backend adversarial CLEAR, 20 UI behaviors, 39 focused frontend contracts (37 passed and two protected skips), seven runtime programs, Ruff, bytecode compilation, TypeScript, the 2,205-module build, OpenAPI, live traffic-blocked Atlanta Race/Learning proof, and the final packaged Windows health smoke. Prospective promotion campaigns move to data-locked P36. |
| 2026-08-15 | Polished the P35 Race/Learning vehicle-dynamics handoff | Race Mode keeps its four-field decision hierarchy and one compact `READY`/`BLOCKED`/`UNAVAILABLE` vehicle-dynamics line; Learning Mode now separates measured time from unresolved attribution, labels uncertainty honestly, presents blocked component families only as a static possibility map, exposes exact channels through keyboard-accessible disclosures, and presents the next bounded inspection with its exact current source context, evidence scope, and blocker without inventing observation-contract requirements. Twenty-nine UI tests, six focused P35 frontend contracts, TypeScript, the 2,205-module production build, diff integrity, and live traffic-blocked Atlanta checks at 1280 x 720 and 393 x 844 passed with no horizontal clipping, vertical overlap, or browser warnings. P19 remains the sole cause and setup authority. |
| 2026-08-16 | Verified P35.1 Unified Dial-In Knowledge Spine | One content-addressed 92-effect bridge now connects the canonical P32 opportunity, P20 state, P35 mechanisms, P26 components, direction-neutral Dial-In knowledge, exact P19/P33 history, bounded discriminators, controlled workflow, and P19 without adding another observer or authority path. The coverage report contains 64 measurable hypotheses, 22 structurally P19-testable controls, six explicitly removed legacy Next Gen effects, and zero gaps; actionless knowledge remains visible but cannot carry a target. The isolated 2,709-test collection passed with 2,700 successes and nine protected skips, plus 11 focused backend hostiles, four frontend contracts, three executable trust guards, 30 UI behaviors, whole-repo Ruff, temporary bytecode compilation, TypeScript, the 2,207-module build, stable 86-path/94-operation OpenAPI, and diff integrity. P19 remains the sole cause, setup, controlled-test, Keep/Undo/Retest, and terminal authority. |
| 2026-08-16 | Verified P35.2 Semantic Precision and Release Trust locally | Exact effect/control/direction/factor matching, P26 relevance partitions, five distinct semantic roles, separate static/runtime truth axes, canonical session-bound producer ownership, fail-closed physical segment sets, diversity-aware Learning selection, and a compiler-pinned client registry close the precision findings without changing P19 authority. The isolated 2,723-test collection passed with 2,714 successes and nine protected skips, plus the permanent synthetic trust audit, whole-repo Ruff, three executable client guards, TypeScript, 30 UI behaviors, the 2,208-module build, CI-policy checks, and diff integrity. Remote `main` remains the prior failing SHA until these repairs are intentionally pushed and the new exact SHA passes Actions. |
| 2026-08-16 | Verified P35.3 Inner Crew Chief Cognitive Closure locally | The deterministic Crew now selects reachable typed evidence against exact subgoals, records request/result/cause/contradiction/critique traces, preserves typed driver-answer scope, stops bounded batch work at real evidence or driver boundaries, and exposes post-open operational consumption without changing P19 or frozen P34 authority. The complete 2,728-test collection passed with 2,723 successes and five protected skips, plus five new hostiles, the frozen P34 suite, whole-repository Ruff, TypeScript, 30 UI behaviors, executable and real-fixture client trust, the 2,208-module build, real Atlanta boundary proof, and diff integrity. Remote validation awaits an intentional push and green Actions result for the new exact SHA. |
| 2026-08-17 | Polished P35.3 end-to-end wiring locally | Typed driver scope now materially orders the next physical inspection while P19 cause truth remains unchanged; reconstructed and persisted critic state must agree; eligibility order, active relevance, exact selection receipts, strongest contradictions, and measured tool durations fail closed across server and client; and one persisted driver continue action remains one count even when bounded work emits multiple trace events. Learning Mode now exposes the active subgoal, evidence gate, eligibility, selection receipt, and post-open resource use. The full 2,734-test collection completed with 2,729 passes and five protected skips, plus 11 dedicated P35.3 tests, the frozen P34 suite, whole-repository Ruff, frontend contract fixtures, TypeScript, 30 UI behaviors, the 2,208-module build, real Atlanta boundary proof, and diff integrity. P19 and frozen P34 authority remain unchanged; remote validation still awaits an intentional push and green Actions result. |
| 2026-08-18 | Verified P35.4.1 Canonical Telemetry Truth Closure locally | Physical alignment is driver-input invariant; full source SHA owns recording independence; tick-primary timing is mandatory for eligible decisions; nominal diffuser geometry is unavailable; typed blockers scope authority; all 62 audited channels have explicit roles; Learning Telemetry Capabilities and executable chart truth are restored; and the first brake/throttle, surface-settling, and stint-migration response producers remain observation-only. The complete 2,839-test collection passed with 2,836 successes and three protected DuckDB skips, plus 214 focused hostiles, 38 UI behaviors, Ruff, TypeScript, the 2,209-module budgeted build, diff integrity, live 1,280/390-pixel Race/Learning verification, and the protected 26,556-record/277-channel Atlanta release audit. P19 remains sole setup authority and P36 remains data-locked. |
| 2026-08-18 | Verified P35.5 field-ready alpha hardening locally | Next Gen oval scope and ordinal evidence wording are honest; one compact cached shell move replaces eager full-intelligence run-open work; returning-session resume, continuous lap playback, exact zoom persistence, grouped evidence debt, shortcut disablement, generated contracts, locked dependencies, single-instance sidecar identity/restart, semantic real-file gates, Windows packaging, and lifecycle smoke are wired without changing P19 authority. The current 2,850-test Python collection is covered by the green definitive 2,847-test run plus focused closure of the three later additions, 43 UI behaviors, two Chromium flows, TypeScript, Ruff, Cargo, zero npm advisories, generated 88-path/96-operation OpenAPI parity, the 2,228-module budgeted build, MSI/NSIS bundles, and packaged ownership/shutdown smoke. Shell access is 13.173 ms unbuilt / 28.376 ms cached without starting intelligence; full first construction remains measured at 12.226 s, while digest-verified exact-semantic restart reuse is 104.327 ms with zero fresh build count. Null Session 01, real A/B/A2, P23/P36 evidence, and every statistical activation remain unearned. |
