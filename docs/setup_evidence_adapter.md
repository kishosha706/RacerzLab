# Setup Evidence Adapter

The setup Evidence Adapter connects a real RacerZLab run to the local setup
knowledge matcher. It stays backend-only, local, deterministic, and
non-authorizing. It supplies evidence context to P19; it does not publish a
setup action itself.

## Purpose

The adapter answers a simple question before ranking internal hypotheses:

For this run, what evidence do we actually have?

It inspects run metadata, setup snapshot metadata, cached channel metadata,
Parquet schema-backed channel summaries, local track-map availability, and
optional compare run IDs. Then it translates that run context into the evidence
flags already understood by `racelab_engine/knowledge/setup/matcher.py`.

Core flow:

`run_id + symptom -> build evidence context -> detect car/track family -> query matcher -> ranked hypothesis inputs with evidence readiness -> P19 revalidation`

Evidence readiness is not setup readiness. Only the canonical P19 reasoning and
controlled-workflow path may add direction, an exact legal target, Keep/Undo,
or stop-testing policy.

## Main Files

- `racelab_engine/knowledge/setup/evidence_schema.py`
- `racelab_engine/knowledge/setup/evidence_adapter.py`
- `tests/test_setup_evidence_adapter.py`

## Evidence Models

`RunEvidenceGroup`
- `group_id`
- `label`
- `status`
- `present_items`
- `missing_items`
- `channels_present`
- `channels_missing`
- `source`
- `notes`
- `confidence_boost`
- `can_support_setup_knowledge`

`RunEvidenceContext`
- `run_id`
- `car_name`
- `car_family`
- `track_name`
- `track_family`
- `setup_snapshot_status`
- `evidence_groups`
- `evidence_flags`
- `warnings`
- `unavailable_reasons`

`CandidateEvidenceReadiness`
- `effect_id`
- `readiness`
- `present_evidence`
- `missing_evidence`
- `warnings`
- `readiness_reason`

## Evidence Groups

The adapter supports these run-aware groups:

- `setup_snapshot`
- `lap_windows`
- `platform_trace`
- `front_ride_height_platform`
- `rear_ride_height_platform`
- `diffuser_proxy`
- `rear_scrape_scrub`
- `shock_histogram`
- `tire_pressure`
- `tire_temps`
- `tire_wear`
- `brake_trace`
- `throttle_trace`
- `steering_trace`
- `yaw_trace`
- `speed_trace`
- `rpm_gear_trace`
- `track_map`
- `compare_baseline`
- `compare_test`

Each group reports `ready`, `partially_ready`, `missing`, `unavailable`, or
`unknown`.

## Channel Mapping Summary

The adapter uses a deterministic channel-to-group map.

- `platform_trace`: CFS/front/rear ride-height, front/rear center ride height,
  rake channels
- `front_ride_height_platform`: CFS/front ride-height and front platform risk
  channels
- `rear_ride_height_platform`: rear ride-height, rear center, rear minimum
  height, rear platform risk channels
- `diffuser_proxy`: front/rear center height, smooth rake, diffuser volume
  proxy channels
- `rear_scrape_scrub`: rear minimum ride height, scrape margin, contact risk,
  scrub/drag suspicion, yaw scrub proxy channels
- `shock_histogram`: four shock velocity channels plus optional RMS/activity
  support channels
- `tire_pressure`: tire pressure and pressure-gain channels
- `tire_temps`: inner/middle/outer tire temperature channels
- `tire_wear`: tire wear and wear-spread channels
- `driver input traces`: throttle, brake, steering, yaw, speed, rpm, gear

The adapter emits matcher-friendly flags such as `platform_trace`,
`rear_platform`, `shock_histogram`, `pressure_gain`, `track_map_zone`, and
`compare_baseline_test`.

## Car Family Detection

Car-family resolution is intentionally conservative.

Outputs:
- `next_gen`
- `legacy_oval_generic`
- `unknown`

Inputs checked:
- run session car name
- run session car path
- setup snapshot name
- setup snapshot JSON text

Rules:
- known Next Gen names resolve to `next_gen`
- clear legacy oval hints resolve to `legacy_oval_generic`
- uncertain cases stay `unknown`

When the family remains `unknown`, the matcher only allows effects that apply
to `all` and disables legacy-only setup areas such as `track_bar`,
`truck_arm_mount`, `bump_stop`, and `packer`.

The public Dial-In request may supply a car-family hint for hypothesis
filtering. The hint never overrides persisted run identity or P19 applicability
checks and cannot authorize a setup action.

## Track Family Detection

Track-family hints are lightweight and non-fatal.

Outputs:
- `superspeedway`
- `intermediate_oval`
- `short_track`
- `road_course`
- `dirt_oval`
- `unknown`

Inputs checked:
- track display name
- track name
- layout hint from the track key

A public track-family hint affects hypothesis filtering only. Physical track,
layout, build, and run compatibility remain server-owned authority inputs.

## Readiness Behavior

The matcher still uses `ready`, `partially_ready`, and
`missing_key_evidence` for candidate ranking.

The adapter supplies the evidence flags. The matcher then:

- marks a candidate `ready` when required evidence is present
- marks a candidate `partially_ready` when some evidence exists but the key
  anchor is present and secondary evidence is still missing
- marks a candidate `missing_key_evidence` when the primary required evidence
  anchor is absent, even if some supporting context is present

Examples:
- shock changes stay `missing_key_evidence` without `shock_histogram`
- platform or diffuser calls stay `missing_key_evidence` without the platform
  anchor they require
- static garage controls can still rank as `partially_ready` hypotheses when
  setup context is present but secondary telemetry is still thin; that rank
  cannot become a public direction or test target

## Current access

The adapter has no standalone direct-action command. It is consumed by the
public non-authorizing Dial-In hypothesis route and by the server-owned P19
workflow assembly. Developers inspect its detailed evidence groups through
tests or explicit debug/Engineer output.

Example text shape:

```text
Run:
- car: NASCAR Cup Series Next Gen Chevrolet Camaro ZL1
- car_family: next_gen
- track: Charlotte 2025 Oval
- track_family: intermediate_oval

Evidence:
- setup_snapshot: ready
- platform_trace: ready
- shock_histogram: missing

Parsed symptom:
- loose_exit

Hypothesis 1: Cross weight
Mechanism: determine whether diagonal support contributes to the selected symptom
Evidence: measurement required
Authority: withheld until P19 revalidates an exact controlled mission
```

## Performance Guardrails

The adapter is designed to stay lightweight.

- no import-pipeline calls
- no telemetry normalization reruns
- no full row materialization in the normal path
- no missing-to-zero behavior
- no fake values
- no duplicate cache rereads

Preferred data sources:
- repository metadata
- cached channel metadata
- channel summary built from Parquet schema and cached metadata
- local track-map lookup

Tests include a guard that the adapter path does not fall back to
`read_telemetry_rows`.

## Warnings And Proxy Language

The adapter preserves conservative wording:

- diffuser context is reported as a derived geometry proxy; normal Dial-In
  output uses platform/support/front-feed/rear-outlet language instead of
  force-claim wording
- garage damper settings do not count as live shock telemetry
- unknown car family and unknown track family produce warnings rather than hard
  failure

## Dial-In Integration

The Dial-In Query Service and Dial-In workspace reuse this evidence context but
hide internals by default. Normal driver-facing output can say things like:

- `Data profile looks clean. High confidence.`
- `Data profile is partial.`
- `I need a cleaner run to be sure.`
- `Compare baseline is missing.`
- `Live shock data is missing.`
- `Tire data is too short for a strong read.`

Raw evidence flags, evidence groups, present/missing lists, ranking reasons,
source IDs, and channel IDs belong in explicit debug/engineer mode only.

Public Dial-In may name the candidate control area and measurement needed, but
never the direction, increment, current/target value, `Change this`, Keep, or
Undo text. There is no standalone run-context setup-action command.
