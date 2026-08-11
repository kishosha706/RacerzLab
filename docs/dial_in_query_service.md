# Dial-In Query Service

## Evidence authority

Dial-In separates three different questions:

1. Did RacerZLab understand the driver's complaint?
2. Does the run contain channels capable of measuring the proposed mechanism?
3. Did eligible telemetry observe enough of that mechanism to make the
   hypothesis worth measuring under P19?

Channel availability answers only question 2. A candidate reaches
`observed_mechanism` only when a tuning-valid eligible event supplies source
channels, provenance, sufficient confidence, and no blocker. Capability-only
matches remain unverified hypotheses. Even observed-mechanism evidence cannot
bypass the canonical P19 identity, independence, traffic, history, mission,
legal-option, and workflow gates.

The verified workflow additionally accepts a selected physical track zone,
phase, objective, and priority. If no repeated opportunity exists inside the
selected scope, the server returns a measurement mission instead of silently
choosing a different corner.

Candidate evidence scores are ordinal and expose their components. They are not
probabilities or promised lap-time gains. Qualified exact-context personal
response models may influence internal P19 ordering only inside their observed
input envelope and exact target zone.

The Dial-In Query Service is the backend layer that turns a run-aware setup
query into a clean driver-facing guidance payload.

## Purpose

It sits on top of:

- local setup knowledge
- source-backed guide digestion
- the run-aware Evidence Adapter
- the Dial-In workspace

Input:

`run_id + complaint`

Output:

- interpreted symptom
- interpreted phase
- up to three non-directional control-area hypotheses
- the mechanism/counter-effect to measure
- compact confidence and data-profile labels
- clarification when the complaint is too generic

## Hidden Evidence Philosophy

Signals still drive:

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
- internal confidence values
- evidence IDs
- ranking scores

Default output stays short and driver-oriented. Debug detail is opt-in through
`include_debug_evidence=True` or `--debug-evidence`.

## Response Shape

`DialInHypothesisResponse`
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
- `clarification`
- `hidden_evidence_summary` optional
- `warnings`
- `evidence_state`
- `source_channels`
- `blocker_reasons`
- `evidence_strength`

`DialInHypothesisSwing`
- `id`
- `title`
- `setup_area`
- `candidate_control_label`
- `related_control_keys`
- `influence_label`
- `strength_label`
- `risk_label`
- `mechanism_to_verify`
- `counter_effect_to_watch`
- `validate_with`
- `validate_with_labels`
- `watch_for`
- `watch_for_labels`
- `readiness_label`
- `measurement_needed`
- `evidence_state`
- `source_channels`
- `observed_evidence_flags`
- `supporting_event_ids`
- `blocker_reasons`

## Clarification Behavior

Generic complaints such as `loose`, `tight`, `push`, `free`, `bad`, or `weird` return
clarification instead of pretending certainty.

Example:

```text
I need to narrow it down. Where is it happening?
```

No hypothesis list is returned until the phase is clear.

## API and UI

The service is exposed through:

```text
POST /api/runs/{run_id}/dial-in
```

The request accepts a driver complaint, optional compare run IDs, optional
car/track/package overrides, a result limit, and `include_debug_evidence`.

The Dial-In tab renders the clean response by default:

- interpreted complaint
- confidence/data profile
- non-authorizing setup-area hypotheses requested by the caller
- the mechanism and counter-effect that still require measurement
- channels and evidence locations to inspect
- a typed blocker until the controlled P19 workflow is built
- compact data profile
- subtle garage-lever helper text when the title needs extra garage context

Clarification options are shown when the complaint is too broad. Selecting an
option only refines the complaint text; RacerZLab never edits setup files.

## Public Hypothesis Language

The public Dial-In response may name a candidate control area, but it never
publishes a direction, increment, target, `Change this`, Keep, or Undo text.
It explains what mechanism must be measured and which counter-effect would
falsify the hypothesis. Only the immutable P19 workflow may expose one exact
legal target after run, session, setup, evidence, covariate, and history gates
all pass.

Internal target IDs such as `exit_yaw`, `rear_tire_trend`, and
`long_run_falloff` stay stable in JSON, but normal text/UI output formats them
as human labels like `exit yaw`, `rear tire trend`, and `long-run falloff`.
NASCAR-facing driver text uses `rear end ratio` for final-drive gearing.

## Terminology Remaster

The vocabulary parser accepts common oval and road-course phrases such as
`won't stay on bottom`, `RF is angry`, `nose is dragging`, `won't take a set`,
`aero wash`, `rear steps out`, `entry understeer`, `power oversteer`, and
`curb instability`. Ambiguous phrases keep a compact clarification question
instead of forcing certainty.

Normal Dial-In copy uses `Symptom Interpretation`, `Signals`, and `Data Profile`
language. Software-first recommendation, diagnosis, matcher-score, and raw
evidence identifier wording belongs outside normal driver output.

## Candidate Filtering

Default Dial-In results:

- return at most 3 hypotheses
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

## Authority handoff

The only action-bearing handoff is the canonical P19 report/workflow. Notebook
does not store Dial-In policy or create test plans, and public Dial-In cannot
learn itself into setup authority.
