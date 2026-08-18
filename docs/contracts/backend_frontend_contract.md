# RaceLab Garage - Backend/Frontend Contract

Last verified: 2026-08-18

## Scope

This is the canonical contract for active backend/frontend integration. The
application is greenfield: removed fields and routes are not compatibility
surfaces. Backend and frontend changes that alter a current payload must land
together with executable contract coverage.

## Runtime and evidence

- Production import is columnar and frame-native through
  `normalize_telemetry_frame`; row normalization is fallback/debug parity only.
- Decoder path, actual analysis engine, and any expected row-fallback reason are
  persisted in the telemetry manifest. Unexpected vector failures are not hidden.
- Every conclusion keeps exact run, lap/window, physical-position, setup, and
  source-channel identity where those dimensions apply.
- Missing data stays unavailable. A proxy stays labeled as a proxy. An invalid,
  partial, pit, wreck, cooldown, or otherwise ineligible lap cannot authorize a
  setup conclusion.
- Nearby-car context that is missing or inside the configured exclusion window
  blocks setup attribution. The product does not classify drafts or clean air.

## Authority boundary

P19 is the sole source of setup direction, exact current/target values,
increments, controlled-test authorization, Keep/Undo policy, and stop-testing
state. The authority projection must match the current run/session, setup hash,
reasoning-snapshot hash, workflow revision, evidence set, and server-owned
mission contract. A mismatch fails closed.

All other public surfaces are observational or measurement-only:

- `RunOverview` has laps, observational telemetry events, setup context,
  findings, and warnings. It has no recommendation list, crew-chief summary, or
  next-test field.
- `TelemetryEvent` and `PlatformEventItem` carry evidence and blockers, not
  recommended actions or diagnostic follow-up prose.
- Compare reports measured deltas, setup/context differences, test discipline,
  and an observation classification. Compare cannot emit Keep/Undo policy or a
  recommended next step.
- Shock Reader reports recorded movement distributions and captured damper
  context with `setup_authority: "withheld"`. It exposes no click, direction,
  target, delta, Keep/Undo, or test-plan field.
- Public Dial-In may name candidate control areas and measurements needed. It
  exposes no direction, increment, current/target value, or Keep/Undo language.
- Engineering Awareness uses `p20.awareness.v2` with fixed
  `authority: "observation_only"`. It carries no current mission, setup-leverage
  authorization, or policy verdict.
- Notebook stores observation evidence plus user notes, tags, and
  `saved`/`archived` record state. It does not store setup-policy verdicts,
  setup changes, next steps, test plans, or setup memory.

Unexpected action-bearing fields on strict current schemas are rejected rather
than ignored.

## Active API families

- Run facts: `/api/runs/{run_id}/overview`, `/laps`, `/events`,
  `/platform-events-report`, `/setup`, `/trace`, and
  `/telemetry-capabilities`.
- Observation tools: `/api/compare`, `/api/compare/insights`,
  `/api/runs/{run_id}/shock-reader`, and `/api/runs/{run_id}/dial-in`.
- Canonical intelligence: `/api/runs/{run_id}/intelligence` and its scoped
  query/measurement-attempt operations. `/intelligence-shell` is a compact,
  cached, navigation-only projection and never starts cold intelligence.
- Controlled authority: `/api/engineering/workflows` and its stage, score,
  cancel, and report operations.
- Observation archive: `/api/notebook/findings` and
  `/api/notebook/findings/{finding_id}`.

There are no current Crew Chief preview, Test Director preview, Notebook test
plan, or Notebook setup-memory endpoints.

## UI modes

Race Mode and Learning Mode consume the same trusted response and authority
guard. Race Mode is concise; Learning Mode adds definitions, evidence detail,
and caveats. Mode selection must never change what is authorized.

## Stable current enums

- Evidence state: `measured`, `calculated`, `estimated_proxy`,
  `observed_correlation`, `controlled_test_effect`, `unavailable`,
  `blocked_by_context`, `needs_confirmation`.
- Notebook record state: `saved`, `archived`.
- Compare-basket readiness: `ready`, `caution`, `not_valid`,
  `reference_mode`.

Internal controlled-workflow verdict values are not a general-purpose public
Compare or Notebook contract.

The generated structural source is `docs/contracts/openapi.generated.json` and
its runtime-free TypeScript projection is
`ui/src/types/openapi.generated.d.ts`. Handwritten client guards remain
responsible for cross-field identity, digest, and authority semantics that an
OpenAPI type cannot prove.
