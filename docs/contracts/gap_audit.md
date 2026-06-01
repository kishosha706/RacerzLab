# RaceLab Garage - Contract Gap Audit

Last verified: 2026-06-01

This file tracks open or uncertain contract gaps. Historical "implemented" logs were removed to avoid stale status claims.

## Open or Needs-Verification Gaps

| ID | Area | Status | Note |
|---|---|---|---|
| GAP-NULL-001 | Null handling in UI math/render paths | Needs verification | Ensure null is not treated as numeric zero in all components. |
| GAP-CMP-001 | Comparison insight numeric coercion | Needs verification | Re-check all score/delta displays for null-safe truth handling. |
| GAP-LAP-UX-001 | Laps extended quality metadata visibility | Deferred | UX enhancement, not correctness-critical. |
| GAP-RAW-UX-001 | Raw channels advanced filters/drawer depth | Deferred | Feature polish; keep baseline metadata truth. |

## Guardrails

- No fake values.
- No missing-to-zero coercion.
- No fake setup diffs.
- Measured/derived/proxy labeling must remain explicit.

## Notes

- Use this file for current gap state only.
- Move historical completed-work narratives to changelog/release notes, not this audit file.

