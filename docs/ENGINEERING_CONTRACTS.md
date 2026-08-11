# RaceLab Garage - Engineering Contracts

Last updated: 2026-08-10

## 1. One authority model

The telemetry pipeline may measure, calculate, classify, compare, and propose a
measurement. Only the canonical P19 reasoning/workflow path may authorize one
setup change or publish exact setup values, a direction/increment, Keep/Undo,
or stop-testing state.

The path is:

`owned telemetry -> eligible evidence -> canonical reasoning snapshot -> immutable mission -> controlled A/B/A2 workflow -> policy result`

P19 keeps mechanism truth, control response, and policy acceptability separate.
A failed control can be undone without falsely disproving the physical
mechanism. No other producer or UI component may recreate this decision from
prose, list order, confidence, or a setup difference.

## 2. Local-only operation

- The backend binds to `127.0.0.1`.
- Imported telemetry, setup snapshots, maps, reports, observations, workflows,
  and evidence history remain local.
- `.ibt` uploads are streamed, sanitized, restricted to the `.ibt` extension,
  and retained as local source evidence after a successful import.
- Path-based import is a local CLI/development operation, not a browser trust
  shortcut.

## 3. Telemetry ownership and normalization

- Decode and archive every channel declared by the `.ibt` header.
- Preserve the raw declaration and add canonical aliases without erasing source
  identity.
- Production normalization is frame-native. The row engine exists only for
  fallback/debug parity.
- A promoted cache must bind the original source hash, cache hash, schema
  fingerprint, run identity, and compatibility identity.
- Missing dependencies stay missing; they never become zero.
- Future comparisons align by physical track position, never sample index.

## 4. Evidence eligibility

Out-laps, cooldowns, pit-road laps, wrecks, spins, cautions, slowdowns,
invalid-speed laps, reset fragments, partial laps, and incomplete coverage are
not setup evidence. Short runs cannot support strong tire degradation or
cooling conclusions.

Every evidence-bearing result identifies its source channels, exact scope,
evidence state, blockers, and confidence limit. Channel presence is capability,
not proof of a mechanism.

Nearby-car context is a covariate and exclusion gate. Missing proximity data or
traffic inside the configured ahead/behind window blocks setup attribution. The
runtime does not create draft, tow, side-draft, or clean-air classifications.

## 5. Measurement and proxy truth

Raw channels are direct archived values. Calculated channels are reproducible
functions of measured values. Proxy channels depend on assumptions or missing
vehicle constants and must remain structurally marked as proxy.

In particular:

- `.ibt` data does not establish exact aerodynamic drag, CdA, downforce, spring
  force, damper force, wheel load, tire force, torque, or horsepower without the
  required measured channels and complete constants.
- Wheel-speed mismatch without verified tire geometry remains a
  geometry-contaminated proxy.
- Constant or pit-only carcass/wear values are snapshots, not live degradation
  trends.
- Shock histograms describe recorded motion. They do not prove that a damper
  setting is wrong.
- No absent channel may be interpolated into a false clear result.

## 6. Observation surfaces

### Run overview and events

`RunOverview` contains run/session facts, qualified best-lap context, laps,
observational `TelemetryEvent` records, the setup snapshot, primary findings,
and warnings. Neither the overview nor an event can contain free-form setup
actions, a crew-chief summary, or a next test.

Platform uses the structured `/api/runs/{run_id}/platform-events-report`
contract. Overview events are never a compatibility fallback for Platform.

### Compare

Compare reports aligned measured deltas, setup/context differences, test
discipline, simulator integrity, confidence, and an observation state. Same
run/lap comparison is reference-only. Compare may show what changed; it cannot
decide whether to keep or undo that change and cannot recommend a next setup
step.

`/api/compare/insights` returns annotations, correlations, target-zone
classification, confidence-weighted observation, sectors, takeaways, warnings,
and missing-channel debt. Those are observation fields, not policy fields.

### Shock Reader

`GET /api/runs/{run_id}/shock-reader` is observation-only. Current damper
settings are context. Its response fixes setup authority to `withheld` and
contains no target, delta, click direction, Keep/Undo, or test-plan field.

### Public Dial-In

`POST /api/runs/{run_id}/dial-in` returns a strict non-authorizing hypothesis
projection. It may name a candidate control area, mechanism to verify,
counter-effect to watch, evidence locations, and measurement debt. Direction,
increment, current/target values, and policy are withheld until P19 earns them.

### Engineering Awareness

The current `p20.awareness.v2` projection is fixed to
`authority: "observation_only"`. Its expected-versus-observed data may describe
mechanism and control response, but it carries no current mission, setup
leverage authorization, policy verdict/reason, or policy countereffect. P20
cannot proxy P19 authority.

### Notebook

Notebook is an observation archive. A finding may persist comparison identity,
lap/window scope, confidence context, evidence, takeaways, warnings, user notes,
tags, and `saved`/`archived` state. It must not recompute evidence and must not
store or synthesize a setup verdict, setup change, next step, test plan, or
setup-memory suggestion.

The current Notebook API is limited to save/list/get/update finding operations.
Deprecated test-plan and setup-memory routes are not part of the product.

## 7. Controlled P19 workflow

An exact setup action is publishable only when the server verifies all relevant
gates, including:

- exact run/session and source artifact identity;
- compatible car, track configuration, build, setup, fuel, tire, weather,
  traffic, driver, and simulator context;
- one physical setup factor with a sourced adjacent legal option;
- eligible, physically scoped, independently repeated evidence;
- an immutable measurement mission and non-overlapping run cohort;
- complete A/B/A2 procedure, guardrail metrics, rollback, and history checks;
- no unchanged same-policy Undo or stop-testing blocker.

The workflow routes under `/api/engineering/workflows` own stage attachment,
scoring, cancellation, reports, and the public authority projection. Client
payloads cannot attest a verdict or authorize themselves.

## 8. Identity and stale-response rules

API and UI must agree on canonical JSON hashing for setup and reasoning
identity. Public intelligence and citations bind the exact run, lap/phase/
physical region, setup hash, and reasoning-snapshot hash. The UI parses
intelligence responses through the shared runtime trust guard before any Race
or Learning surface consumes them.

Changing run, session, lap, zone, setup, workflow revision, or response identity
clears incompatible state. Late or foreign responses cannot render under the
new scope.

## 9. UI behavior

- Race Mode is short and decision-first.
- Learning Mode adds definitions, source channels, blockers, related systems,
  and caveats.
- Both modes use the same authority decision.
- Observation views may navigate to evidence or request a measurement; they may
  not turn a warning, confidence score, setup diff, or candidate rank into an
  exact setup action.

## 10. Track maps and charts

- Current map import is `/api/imports/mt2`; canonical maps use the current
  `track_map_v2`/`mt2` contract.
- Map and trace overlays align by lap percentage/physical distance, never sample
  index.
- Missing trace regions render as gaps. No smoothing or null-to-zero operation
  may create false continuity.
- Proxy channels remain visibly distinct from measured channels.

## 11. Removed compatibility surfaces

The following are intentionally absent from the current contract and must not
be restored from old docs, caches, or clients:

- import-time Crew Chief recommendations;
- Crew Chief or Test Director preview endpoints;
- `RunOverview.recommendations`, `crew_chief_summary`, or `next_test`;
- event `recommended_actions`, `recommended_action`, or
  `measurement_guidance` fields;
- public Shock Reader setting targets/actions;
- public Dial-In directional/target fields;
- public Compare Keep/Undo or next-step fields;
- Notebook verdict/setup-change/next-step fields;
- Notebook test plans and setup-memory summaries;
- channel metadata named `used_by_recommendations`.

Current strict contracts reject obsolete action-bearing input where applicable.
