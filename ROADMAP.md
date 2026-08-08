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
- [ ] Add producer-owned typed observed-mechanism roles plus qualified yaw,
  brake, RPM/gear, tire, and driver-correction event detectors. Until those
  detectors exist, unsupported actions correctly produce measurement missions
  instead of borrowing meaning from raw provenance channels.
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
