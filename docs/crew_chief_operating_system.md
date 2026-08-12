# P27-P30 deterministic Crew Chief operating system

## Boundary

The Crew Chief is a deterministic executive over already-produced engineering
artifacts. It can schedule an inspection, ask one typed contextual question,
track an objective, present a success contract, and monitor eligible laps. It
cannot rank a new physical cause, choose a setup value, publish Keep/Undo, or
stop a measurement mission. P19 remains the only setup and policy authority.

The optional generative adapter is `shadow_only`, disabled, and has authority
`none`. The production Crew Chief requires no LLM, remote service, or API key.
P30 adaptive experimentation is explicitly `data_locked`; the production test
protocol remains one P19-authorized factor under A/B/A2.

## Atomic workspace and identity

`GET /api/runs/{run_id}/crew-chief-workspace` builds P19 once and projects P20
and P26 from that same private bundle. Its `CrewChiefWorkspaceIdentity` freezes:

- exact run and saved-session membership plus selected-scope hash;
- canonical P19 reasoning hash;
- P20 state revision/profile hash;
- P26 graph/content/reasoning identities;
- setup ID and snapshot hash;
- verified vehicle-runtime identity;
- active workflow ID/revision;
- objective, investigation, and event-history head.

The response includes references and summaries only—never raw telemetry. The UI
validates it against the already-trusted public P19 report before rendering.
An authorized controlled test must exactly equal P19 title, instruction,
control, current value, proposed value, event IDs, workflow, and revision.

## Persistence and operations

Investigations are immutable origins plus ordered, content-hashed typed events.
Every mutation supplies the expected workspace revision; stale writes fail with
conflict and require an explicit rebase. Durable tables cover investigations,
events, objectives, success contracts, exact-context component response
records, complaint/context-only driver memory, and effectiveness counts. Run
deletion cascades dependent Crew Chief state. No raw trace is copied.

Public operations are deliberately bounded:

- open an investigation;
- continue one deterministic inspection step;
- record an answer to the pending typed question;
- select an objective;
- abandon;
- rebase to current P19/P20/P26 identity.

Request models forbid extra keys, including client-authored setup actions,
targets, policy verdicts, and stop-testing claims.

## Success Contract

The Success Contract copies its target phase, repetitions, metrics, thresholds,
stop rule, and rollback rule from the canonical P19 information plan or exact
controlled card. Hard protections cover lap integrity, traffic/context, setup
isolation, driver repeatability, and exact run/session/setup scope. It cannot
authorize a setup change by itself.

## Run Sentinel

The sentinel observes the current P19 measurement or A/B/A2 mission. A lap is
accepted only when its exact lap ID is present in the P19 eligible-lap set and
its canonical lap context carries no blocker. Rejected laps retain their exact
eligibility/context reasons and cannot advance the stage counter. Missing
coverage is not treated as zero or clean.

## P29 memory

The Component Response Atlas admits only exact-context controlled P26 history
with all A/B/A2 run identities. Mechanism result, control response, policy,
component/control, car/build/track, objective, phase, setup hash, and evidence
identity remain separate. Atlas records are historical observations, not new
policy authority.

Driver reports and typed answers are stored separately as
`complaint_prior_only`. They may scope a later inspection but cannot mutate P19
cause truth or authorize a setup action. The effectiveness ledger contains
operational counts only and makes no probability claims.

## UI

The existing Engineer workspace owns the command deck; there is no new top-level
tab or selection context. Race Mode presents WHAT, WHERE, WHY IT MATTERS, WHAT
WE KNOW, WHAT REMAINS UNCERTAIN, and NEXT. Learning Mode expands the mission,
critic, success contract, sentinel, evidence index, response atlas, driver
memory, and locked research boundary. Evidence buttons use the canonical
`focusEvidence` path.
