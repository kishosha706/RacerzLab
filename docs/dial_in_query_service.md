# Dial-In Query Service

The Dial-In Query Service is the backend layer that turns a run-aware setup
query into a clean driver-facing guidance payload.

## Purpose

It sits on top of:

- local setup knowledge
- source-backed guide digestion
- the run-aware Evidence Adapter

Input:

`run_id + complaint`

Output:

- interpreted symptom
- interpreted phase
- clean top setup swings
- one-change test language
- compact confidence and evidence-readiness labels
- clarification when the complaint is too generic

## Hidden Evidence Philosophy

Evidence factors still drive:

- ranking
- readiness
- conservative filtering
- capability gating
- missing-context hints

But default responses do not expose:

- raw channel names
- full evidence-group dumps
- internal scoring
- full ranking-reason lists

Default output stays short and crew-chief-like. Debug detail is opt-in through
`include_debug_evidence=True` or `--debug-evidence`.

## Response Shape

`DialInResponse`
- `run_id`
- `complaint_raw`
- `interpreted_symptom`
- `interpreted_phase`
- `balance_direction`
- `confidence_label`
- `readiness_label`
- `driver_message`
- `top_swings`
- `next_step`
- `validation_summary`
- `clarification`
- `hidden_evidence_summary` optional
- `warnings`

`DialInSwing`
- `id`
- `title`
- `setup_area`
- `strength_label`
- `risk_label`
- `effect`
- `counter_effect`
- `one_change_test`
- `validate_with`
- `watch_for`
- `readiness_label`
- `debug` optional

## Clarification Behavior

Generic complaints such as `loose`, `tight`, `push`, or `free` return
clarification instead of pretending certainty.

Example:

```text
I need the phase before I would call a swing. Where does the rear first step out?
```

No high-confidence swing list is returned until the phase is clear.

## Candidate Filtering

Default Dial-In results:

- return at most 3 swings
- stay diverse by setup area
- avoid more than one major package-level swing in the default set
- never show Next Gen-disabled legacy areas
- stay conservative for unknown car family

## CLI

```powershell
python -B scripts/query_dial_in.py --run-id <RUN_ID> --complaint "loose off"
python -B scripts/query_dial_in.py --run-id <RUN_ID> --complaint "tight center" --json
python -B scripts/query_dial_in.py --run-id <RUN_ID> --complaint "loose" --debug-evidence
```

## Debug Evidence Mode

`--debug-evidence` includes backend-only detail:

- evidence flags
- evidence groups
- present evidence
- missing evidence
- candidate readiness internals
- ranking reasons
- disabled-by-capability details

That mode is for development and inspection, not default driver-facing output.

## Why No UI Yet

This milestone is intentionally backend-only:

- no React panel
- no crew-chief chat surface
- no memory layer
- no survey flow

The service is meant to stabilize the response contract before a read-only UI
panel or API wrapper is added.

## Next Step

The natural next step is a read-only Dial-In UI panel that renders the clean
response by default and only exposes debug evidence in a developer mode.
