# P35.6 — Unified Handling Intelligence: Physics Audit

Status: **P1 physics audit verified locally (2026-10-13)**; **P2 unified handling
investigation verified locally (2026-10-13)**; **P3 cross-workspace integration
and P4 Engineer → Dial-In handoff verified locally (2026-10-14)**; P5-P6
pending. This document is
the scientific record of the correction that moved the automatic
handling-balance producer from "impressive-looking dashboard" to
"engineering observation system", and of the integration that connects the
observation to the existing intelligence spine.

## 1. The physics identity that changed everything

In planar vehicle kinematics the course (trajectory) angle chi, heading psi,
and sideslip beta are related by:

```
chi = psi + beta
```

Differentiating and using d(chi)/dt = v * kappa (speed times actual-path
curvature) and d(psi)/dt = r (body yaw rate):

```
v * kappa - r = d(beta)/dt
```

The residual the producer originally computed — "expected yaw (speed x
path-curvature) minus measured yaw rate" — is therefore the **planar sideslip
rate**, not a rotation-response deficit per se. Two consequences drove the
audit:

1. **Steady-state blindness.** Once the car settles into steady-state
   cornering, beta is roughly constant and the residual is ~0 — no matter how
   persistently tight or loose the car is. A residual-based classifier cannot
   see the very condition it claims to detect.
2. **Transient confusion.** A nonzero residual appears while beta is changing
   (turn-in, exit, weight transfer). It cannot by itself establish understeer
   or oversteer.

The original producer also computed `lat_accel / speed - yaw_rate` as a
"sideslip-rate proxy" and used it as corroborating/contradicting evidence.
Planar kinematics gives `a_y = v * (r + d(beta)/dt)`, so that quantity is the
**same identity**. It was removed: an identity cannot corroborate itself.

## 2. What changed

### Producer (`racelab_engine/analysis/handling_balance.py`)

- The residual `v * kappa - r` is now reported as a **kinematic residual
  diagnostic** and documented as the planar sideslip rate.
- New diagnostic-only classifications:
  - `kinematic_residual_observation` — the residual exceeds the run-local
    noise envelope without steering-response corroboration. Cannot carry a
    canonical symptom.
  - `steering_demand_anomaly` — steering demand per achieved curvature
    diverges from the run-local reference without a corroborating residual.
    Cannot carry a canonical symptom.
- `rotation_response_deficit` / `rotation_response_excess` now require
  **two-strand corroboration**:
  - **Strand A:** the kinematic residual beyond the run-local reference
    envelope (leave-one-out lap medians, group robust scale).
  - **Strand B:** steering demand per achieved path curvature beyond the
    same envelope **under comparable conditions** (laps whose median phase
    speed is within 5 m/s of the group median participate).
  - Both strands use strict-majority unidirectional qualification, so a
    bimodal lap group (for example a 3/3 split) raises the group scale and
    cannot feed two opposing signatures into classification order.
- Only a corroborated deficit/excess may resolve a canonical Dial-In symptom,
  and even then the association remains telemetry-observed, observation-only.
- `no_significant_imbalance_qualified` now states the blind spot honestly:
  the residual cannot exclude a constant sideslip angle, so the absence of a
  qualified signature is not proof of neutral balance.

### Contract (`racelab_engine/analysis/handling_balance_contracts.py`)

- New operating condition `independent_response_corroboration`.
- New forbidden outputs: `single_strand_tight_loose`,
  `sideslip_rate_self_corroboration`.
- The scientific ceiling documents the d(beta)/dt identity.

### Models (`racelab_engine/models/handling_balance.py`)

- New `HandlingCorroboration` on each phase observation:
  `kinematic_residual_strand_qualified`, `steering_response_strand_qualified`,
  `steering_response_direction`, `aligned`, `corroborated`.
- New observation channels: `steering_demand_per_curvature_median_deg_per_inv_m`,
  `steering_demand_relative_deviation_scale_units`, `speed_median_mps`.
  The redundant `sideslip_rate_proxy_median_rad_s` was removed.
- Structural validator: a `canonical_symptom_id` on anything but a
  deficit/excess classification — or without a corroborated observation —
  fails model construction.
- Schema versions bumped to v2 (report and assessment).

### Symptom bridge (`racelab_engine/knowledge/setup/handling_symptom_bridge.py`)

- Blocker wording now requires a **corroborated** deficit/excess signature;
  the bridge has never mapped residual-only or demand-only classifications.

### Client (`ui/src/utils/handlingBalanceTrust.ts`, `HandlingBalancePanel.tsx`)

- The trust boundary rejects any assessment whose canonical symptom rides on
  a non-deficit/excess classification (mirrors the server validator).
- Learning mode shows the two-strand status per phase; the footnote explains
  the sideslip-rate identity and the corroboration requirement.

## 3. Real-telemetry validation

Run `recording-49662f01c50dbe2e36a32dbacf2831100f405a43523b38deafbc4097b0de65ac`
(Next Gen Talladega, 10 eligible laps, cohort integrity clear, 0.65
confidence cap):

| Producer | Run classification | center | full_throttle_exit |
|---|---|---|---|
| Pre-audit | `rotation_response_deficit` | `tight_center` | — |
| Post-audit | `kinematic_residual_observation` | residual +0.0283 rad/s, demand strand unavailable, no symptom | residual +0.0215 rad/s, demand deviation +0.087 scale units (below qualification), no symptom |

The post-audit conclusion: the residual cannot establish a tight/loose-family
symptom on its own. This is the honest scientific outcome, not a regression:
the pre-audit `tight_center` was not supported by the physics.

## 4. Why the residual is still kept

The observed difference remains useful as a kinematic response diagnostic:
it localizes where beta is changing, feeds the transient-anomaly screen, and
— when the steering-demand strand aligns under comparable conditions — is one
of two independent strands that can support an observation-only canonical
symptom. The demand strand is genuinely independent: it relates steering to
achieved curvature and does not involve the yaw/path identity at all.

## 5. What is still not established (and must not be claimed)

- A car-wide **uniform** balance offset is invisible to any run-local
  reference. Detecting it requires an independent external reference
  (historical same-car/same-track sessions or a reviewed vehicle-response
  model) — P6 of this milestone.
- This producer cannot separate driver behavior from vehicle behavior beyond
  what the two strands show; P2 (P35/P26/P32 investigation integration) owns
  that separation.
- Tight/loose remains an observation-level association, never a measurement,
  never a setup authorization. P19 is unchanged.

## 6. P2 — Unified handling investigation (verified locally 2026-10-13)

The qualified handling observation is now a first-class derived view inside
the canonical Engineering Case, connected to the existing scientific
intelligence spine without creating any new reasoning authority.

### What was built

- `racelab_engine/models/handling_investigation.py` — the typed projection:
  `HandlingInvestigationProjection` (`p356.handling-investigation.v1`,
  authority literal `derived_observation_view`, `setup_authorized` False,
  `p19_authority_unchanged` True, content-addressed `projection_sha256`).
  Per-assessment `HandlingAssessmentRef` structurally requires
  `corroborated == (canonical_symptom_id is not None)`. Findings carry
  WHAT/WHERE/DRIVER/RESPONSE, mechanism relations, component relations,
  performance associations, contradictions, unresolved notes, and the next
  inspection with its evidence channels.
- `HandlingMechanismRelation.support_declared`, `HandlingComponentRelation.
  malfunction_declared`, and `HandlingPerformanceAssociation.
  causation_declared` are all structural `False` literals — the ceiling is
  enforced by the schema, the model validator, and the client trust boundary.
- `racelab_engine/services/handling_investigation_service.py` — the derived
  view builder:
  - **P35:** mechanisms whose reviewed `relevant_phases` intersect the
    observation phase become relations with relevance `applicable`
    (direction-neutral), `informed_by_observation` (corroborated
    deficit/excess aligned with the reviewed deficit/excess mechanism
    direction AND no missing required channels), or `blocked` (required
    support channels absent, using the reviewed
    `_CHANNEL_CANONICAL_EQUIVALENTS` alias map). The kinematic residual
    alone can never inform a mechanism.
  - **P26:** component families from each mechanism's
    `p26_component_family_ids`, with relevance copied from the P26
    projection state (`supported`/`contradicted` surface P26's own
    finding; observable follows `live_response_observable` or available
    live channels; unavailable when P26 is fail-closed).
  - **P32:** co-occurrence association with P32-owned opportunities that
    match the phase family and are `repeatable` and
    `candidate_only`-attributed; the wording states co-occurrence and
    never causation.
  - **Alternatives:** driver demand, entry speed, traffic, tire-state
    progression, shared-source dependence, and missing channels, each
    classified `supported | contradicted | plausible_unresolved |
    not_observable` with explicit basis.
  - **Next:** the reviewed semantic-registry discriminator contract for the
    steering-to-yaw relation, with `steering_deg`/`yaw_rate` as the next
    evidence channels.
- Engineering Case wiring: `CanonicalEngineeringCase.handling_investigation`
  (optional, exact run/session/setup binding enforced by the case validator),
  included in `engineering_case_projection_revision_sha256`, in the Crew
  Chief workspace identity, and in the evidence index as neutral
  `p356.handling_balance` entries (no P20 mechanism kinds, no typed
  artifact, outside the P35 dynamics namespace, and outside P34
  qualified-artifact cohorts by state).
- `build_handling_balance_report` is now shared by the
  `GET /api/runs/{run_id}/handling-balance` route and the workspace build,
  with a bounded memo keyed by exact producer identity so warm workspace
  reads never re-read telemetry rows.
- Engineer workspace: Race Mode shows one compact "CENTER ROTATION — …
  Mechanical cause unresolved — Review matched traces" line; Learning Mode
  shows the full per-finding investigation with mechanism hypotheses,
  component families, performance co-occurrence, contradictions,
  unresolved notes, and the next inspection, all as a derived observation
  view with an "Observation only" badge. The client trust boundary
  validates the embedded projection inside the Engineering Case check.

### Dependence audit

Both producer strands consume measured path curvature, share the run-local
reference lap group, and share measurement noise. The projection declares
`evidence_dependence` explicitly, the corroborated confidence carries a
discount (0.55 / 0.45 instead of 0.6 / 0.5), and the two strands are never
counted as independent evidence units.

### Real-telemetry evidence (Next Gen Talladega, 10 eligible laps)

- The Engineering Case for the real run embeds the investigation with two
  findings (center, full-throttle exit), zero informed mechanisms (correct:
  residual-only), P26 component families, the steering-to-yaw discriminator
  as the next step, and two neutral evidence-index entries.
- Warm workspace reads measure ~0.166 s (handling memoized); the cold build
  adds the one-time handling producer pass to the existing intelligence
  build on this run.

### Verification

- 17/17 adversarial investigation tests (mechanism informing without
  support, residual-only informing nothing, component relevance without
  malfunction, performance co-occurrence without causation, no
  DriverIntent/setup language, dependence declaration, missing-channel
  limitations, contradiction carry-through, structural authority
  rejection, foreign-assessment case rejection, P34 cohort exclusion, P1
  classification invariance).
- 18/18 P1 handling tests, the full fast Python gate, whole-engine/API/tests
  ruff, frontend tsc, 116/116 Vitest behaviors, 2/2 Chromium flows, 7/7
  runtime trust guards, the budgeted production build, and real-data
  workspace validation all pass.

## 7. P3 + P4 — Cross-workspace integration and the Engineer → Dial-In handoff (verified locally 2026-10-14)

The same qualified handling observation now follows the user across every
existing workspace without any new reasoning system, state provider, or
authority.

### 7.1 One shared observation handoff

- `ui/src/utils/handlingObservationHandoff.ts` — the handoff travels through
  sessionStorage (the controlled-workflow handoff pattern), carrying the
  exact observation identity (`assessment_id`, phase, canonical symptom if
  legitimately established) and the exact case identity (`case_id`,
  `case_revision_sha256`, `case_sha256`). Dial-In validates it against the
  current Engineering Case before rendering; a stale revision, a foreign
  case, an unknown assessment, a phase mismatch, or a symptom mismatch
  discards the handoff silently. No new frontend state provider exists.

### 7.2 Workspace consumption (P3)

- **Overview:** a compact "Handling investigation" status line (findings
  count, primary phase, next inspection) with an Engineer handoff in both
  Race and Learning mode, next to the existing observation line.
- **Engineer:** Race Mode keeps one decision line with "Review matched
  traces" and "Dial-In knowledge"; Learning Mode exposes the complete
  WHAT → WHERE → DRIVER → RESPONSE → MECHANISMS → COMPONENTS →
  PERFORMANCE → CONTRADICTIONS → UNRESOLVED → NEXT chain plus per-finding
  handoffs: Review telemetry, Review laps (exact qualified lap window and
  phase zone), Setup relevance (exact case identity + mechanism/component
  focus), and Dial-In knowledge.
- **Laps:** the finding deep-links the qualified lap window and phase zone
  (e.g. `Window 10-11 · Rep Lap 10 · Area center` on the real Talladega
  run).
- **Platform:** the review-evidence handoff focuses the first reviewed
  next-evidence channel (`steering_deg`, `yaw_rate`) on top of the
  existing trace workbench; unavailable channels are never shown as zero
  (existing Platform invariant unchanged).
- **Setup:** a Learning-mode "Handling relevance" section lists candidate
  mechanisms and mechanically relevant component areas from the case
  investigation, with the explicit authority ladder: relevant control —
  none unless P19 authorizes one; supported evidence — none declared;
  authorized experiment — only the existing active P19 workflow, opened
  through Dial-In.
- **Dial-In:** see 7.3.

### 7.3 Dial-In telemetry-origin handoff (P4)

- New read-only endpoint
  `GET /api/runs/{run_id}/handling-knowledge?session_id=…&assessment_id=…`
  (`api/routes_p3_engineering.py`, `racelab_engine/models/
  handling_knowledge.py`, `racelab_engine/services/
  handling_knowledge_service.py`). It reuses the memoized Crew Chief
  workspace and projects one assessment-scoped, display-only
  `HandlingKnowledgeProjection` (`p356.handling-knowledge.v1`,
  authority `derived_observation_view`, `setup_authorized` structurally
  False, `p19_authority_unchanged` structurally True) with exact
  case-identity binding and a content-addressed `projection_sha256`.
- The projection carries exactly the five Dial-In sections:
  - **Observed behavior** — telemetry wording only; a canonical symptom
    appears only when the two-strand producer legitimately established it.
  - **Relevant knowledge** — current P35.1 hypotheses (supported /
    blocked candidates plus knowledge-only entries) merged with the
    reviewed static mechanism→setup bridges for mechanisms the current
    run cannot map (labeled `educational_only · catalog knowledge only`,
    structurally `setup_authorized: False`).
  - **Evidence status** — per-mechanism missing channels, contradictions,
    and unresolved notes.
  - **Countereffects** — exact countereffect ids plus reviewed static
    countereffect targets.
  - **Next action** — an inspection or measurement from the P2
    investigation, or `p19_authorized_experiment` only when the
    knowledge spine mirrors an exact P19 control (`p19_control` present,
    per-hypothesis `setup_authorized` True is P19's authority, reported
    not created).
- `HandlingKnowledgeCard` (Dial-In) is display-only: it never writes the
  driver complaint box, never fabricates driver wording, and never creates
  DriverIntent. The driver's own complaint flow remains untouched; the
  card states explicitly that a driver who agrees should describe it in
  their own words.
- Client trust (`ui/src/utils/handlingKnowledgeTrust.ts`) recomputes the
  projection hash and rejects rehashed payloads, foreign/stale case
  identity, symptoms without corroboration, drifted authority, and setup
  authorization without an exact mirrored P19 control.

### 7.4 Real-telemetry evidence (Next Gen Talladega, 10 eligible laps)

Live browser walk-through of the whole chain on the real run:

1. **Overview** shows the residual-only observation line and the
   investigation status card (2 findings).
2. **Engineer** shows the full investigation; the race line carries
   "Dial-In knowledge".
3. **Dial-In** shows the telemetry-observed card for the center
   assessment: observed behavior (+0.0283 rad/s sideslip-rate identity),
   **no canonical symptom** ("None — no tight/loose claim"), mechanism
   evidence status, catalog knowledge (Cross Weight, Spring Rate, Tire
   Pressure, ARB arms/diameter — all educational/catalog-only), 28
   countereffect targets, and the steering-to-yaw discriminator review as
   the next action. The complaint box stayed empty.
4. **Platform** opens the trace workbench with the focused channel.
5. **Setup** shows the handling relevance ladder (relevant control: none;
   supported evidence: none; authorized experiment: none; only P19 may
   authorize).
6. **Laps** lands on `Window 10-11 · Rep Lap 10 · Area center`.

### 7.5 Verification

- 17/17 handling-knowledge adversarial tests (corroborated symptom
  preserved; residual-only symptom-free; missing investigation/assessment
  fails closed; contradictions carried; foreign case identity fails
  closed; exact case identity bound; unsupported capability filtered;
  blocked mechanisms declare missing evidence; no causal language; no
  fabricated driver wording; P19 withholding keeps next action
  inspection/measurement; an exact P19-authorized experiment is reported
  not created; knowledge-only catalog entries stay visible and
  non-authorizing; static bridges cover unmapped mechanisms; structural
  rejection of symptom-without-corroboration and setup-without-control).
- Frontend: 19 new Vitest behaviors (trust guard ×9, Dial-In handoff
  ×5, panel handoffs ×4, overview card ×1) join the full 135/135 suite;
  tsc clean; the budgeted production build passes with zero new CSS rules;
  OpenAPI/TypeScript contracts regenerate in-tree (94 paths, 410 schemas).
- The full fast Python gate and whole-engine/API/tests ruff pass; real
  Talladega endpoint checks confirm the symptom-free, non-authorizing
  projection end to end.

