# P20 engineering-awareness projection

Slice G exposes one bounded public read of the already-canonical P19 reasoning
snapshot and P20 producer artifacts. It does not rank causes, interpret raw
telemetry, select setup controls, or evaluate Keep/Undo policy.

## Ownership and authority

- `EngineeringAwarenessProjection` binds the exact run and session scope, canonical P19 snapshot
  SHA-256, state revision, profile hash, and analyzer/schema versions.
- The primary state can only resolve from the leading P19 cause to its exact
  qualified `MechanismObservation`. A missing mapping remains knowledge debt.
- All ten subsystem families are present exactly once. A failed producer stays
  blocked or unavailable even when a different producer succeeds.
- Setup leverage lists only controls already present in a P19 controlled outcome,
  exact authority envelope, or current controlled-test card. It never enumerates
  or ranks possible garage controls.
- Expected-versus-observed keeps mechanism truth, control response, and policy
  verdict as separate fields. An Undo cannot silently falsify a supported
  mechanism.
- Requested pit/control mutations remain requests unless a separate confirmation
  artifact proves service completion.

## API and performance boundary

`GET /api/runs/{run_id}/engineering-awareness` returns summary state only. Raw
traces remain lazy in existing telemetry endpoints. The service reuses the single
projected P19/P20 read, keeps at most eight exact-identity projections, and
invalidates on database/WAL or telemetry-manifest identity changes. A warm hit
retains the same run/snapshot/revision identity and reports its cache state.

The Atlanta Next Gen schema/capability run produced a 10-subsystem fail-closed
projection in about 29 ms cold and under 1 ms warm in a fresh local process. It
produced no temporal episode or state-drift finding, correctly preserving those
as unavailable rather than converting missing evidence into a stable state. This
fixture validates the endpoint, identity, update semantics, and bounded path; it
does not validate vehicle dynamics or performance physics.

## Existing UI surfaces

No top-level tab was added. Overview shows the primary state and next canonical
mission; Laps shows exact episode scopes and drift debt; Platform shows episode
chains; Setup shows P19-owned leverage labels; Compare keeps expected mechanism,
observed control response, and policy separate; Smart Engineer shows all ten
producer states and independent trust axes.

Every panel request is sequence guarded and checks both response run fields before
rendering. Exact evidence navigation continues through `focusEvidence`. Cockpit
startup does not await this read because the active workspace loads it lazily.

## Known limits and locked work

The clean-stint drift builder exists, but no canonical numeric drift ledger is yet
attached to the P19 snapshot. The public projection therefore exposes typed
`unavailable` debt rather than fabricating a ribbon. Body-sideslip observers,
bank/gravity compensation, geometry-corrected wheel disagreement, probability,
formal information gain, Bayesian optimization, and multi-control automation stay
shadow-only or data locked. No Slice H production authority is activated.
