# RaceLab Garage - Backend/Frontend Contract

Last verified: 2026-06-01

## Scope

Canonical contract notes for active backend/frontend integration. Historical migration notes and one-time rollout checkpoints were removed to reduce stale drift.

## Active Runtime Expectations

- Default import path: columnar decode + vectorized analysis.
- Row analysis path remains fallback/debug parity only.
- Frame-native consumers are preferred; no full row materialization in normal import.
- Draft detection/classification is removed from runtime and product decisions.

## Data Honesty Rules

- Missing stays missing; do not convert missing telemetry to zero.
- Proxy/estimate channels must remain labeled as proxy/estimate.
- Setup diffs must remain truthful and source-backed.

## Status/Enum Anchors

Keep these values stable unless coordinated backend+frontend updates are made:
- Verdict: `keep_direction`, `undo`, `retest`, `inconclusive`
- Basket readiness: `ready`, `caution`, `not_valid`, `reference_mode`
- Confidence tiers: `low`, `medium`, `high`
- Notebook status: `saved`, `confirmed`, `rejected`, `needs_retest`, `archived`

## Needs Verification

The following should be treated as pending re-validation if referenced elsewhere:
- Exact module-count and build-duration snapshots.
- Exact pytest totals/durations.
- Any statement that a deferred UX item is complete without current code evidence.

