# Backend/Frontend Contract Reference

Last verified: 2026-06-01

This document captures active API/UI contract expectations. Historical implementation logs were moved out of this file.

## Current Contract Truths

- Import path defaults: columnar decode + vectorized analysis.
- Row path remains fallback/debug parity only.
- Normal runtime import avoids full row materialization.
- Draft detection/classification is removed from runtime and must not appear in API-driven decisions.
- Missing data must remain missing (`null`/unavailable), never coerced to zero.
- Proxy/estimate values must be labeled as proxy/estimate in UI.

## Workspace IDs

- `overview`
- `map`
- `laps`
- `platform_trace`
- `setup_impact`
- `compare`
- `notebook`
- `channels`

## Compare Basket Readiness

- `ready`
- `caution`
- `not_valid`
- `reference_mode`

## Verdict Values

- `keep_direction`
- `undo`
- `retest`
- `inconclusive`

Frontend-only convenience states may exist, but backend payloads must remain explicit.

## Known Backend-Only Fields

Examples intentionally not surfaced directly in normal UI:
- Internal file/hash paths
- Internal cache/raw JSON blobs
- Internal debug-only lap boundary fields

## Needs Verification

- Any section previously claiming exact build/test timing snapshots.
- Any claim that a specific deferred gap is closed unless backed by current code/tests.
- Any RawChannels UX parity claim beyond baseline channel listing and metadata usage.

## Contract Guardrails

- No fake values.
- No missing-to-zero coercion.
- No fake setup diffs.
- Preserve measured/derived/proxy honesty.

