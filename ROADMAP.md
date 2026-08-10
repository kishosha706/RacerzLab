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
