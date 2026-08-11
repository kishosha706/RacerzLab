# Robustness Notes

## Import Cache Safety

Telemetry imports stage parquet/channel metadata under a temporary run id before saving run metadata. After the database save succeeds, staged cache artifacts are promoted to the final run id paths with an atomic replace. If the database save fails, staged artifacts are cleaned where possible and the previous completed run/cache is left intact.

Safe cleanup boundaries:

- Temp cache/upload artifacts from failed imports may be removed.
- Raw user `.ibt` files must not be deleted.
- Imported run records, setup snapshots, observational Notebook findings, P19
  workflows, immutable measurement attempts, and controlled outcomes must not
  be deleted by cache cleanup. Notebook test plans and setup-memory summaries
  are not current product records.

## Upload Handling

Multipart `.ibt` uploads are streamed to a unique local import copy instead of being read into memory all at once. Successful import copies are retained as local evidence. Failed import copies are removed when safe.

## Recovery UX

Import failures return user-safe recovery details:

- what happened: the telemetry file could not be processed
- why it matters: no completed run was created
- what to do next: try again or choose a different `.ibt`

Technical details stay in logs or secondary UI details. Normal driver-facing UI should not expose raw tracebacks.

Duplicate telemetry imports update the existing run record for the same generated run id and show that replacement honestly.

## Stale Frontend State

The Test Basket revalidates persisted baseline/test evidence against the active session run list. Unavailable items are marked stale and shown to the driver instead of being silently removed. Stale basket pairs are not valid for review.

Selection state also validates the selected run against the active run list so old lap/event/sample focus does not survive a session change.

When selection is cleared by an active-session change, the UI should present it as a calm state change and ask the driver to choose a run or stint from the current session.

## Platform Event Visibility

Backend Platform events remain in the structured Platform payload for evidence
use. Driver-facing chart markers, rails, timelines, and inspectors use shared
visibility filtering so internal events are hidden by default in Actionable
mode and can be shown through Proxy/Internal or All modes. Overview
`TelemetryEvent` observations are a separate contract and must never be used as
a fallback Platform event stream.

The `REAR_CONTACT_RISK` platform event type was removed from the active contract because no detector emitted it. Rear-platform evidence remains available through `MIN_REAR_RIDE_HEIGHT`, `REAR_PLATFORM_LOW`, `REAR_PLATFORM_SCRAPE`, and the `rear_platform_contact_risk` calculated channel.

`display_scope` currently supports `actionable`, `watch`, and `internal`. A previous unused `debug` scope was removed from backend and frontend contracts.

## Platform Detector Contracts

`racelab_engine.analysis.platform_events.detect_platform_events` is the
canonical rich PlatformEvent detector for Platform UI and track-map overlays.

The old duplicate TelemetryEvent platform detector and the frontend legacy-event
fallback are removed. Future code should import Platform event detection from
`platform_events.py`; there is no compatibility path back to a separate
detector or action-bearing event schema.

## Missing Data Policy

Missing telemetry/setup fields mean unavailable. They must not be converted to zero or used to create fake exact conclusions.

## Core Logic Coverage Pass

As of 2026-08-10, focused synthetic tests cover these high-value pure logic areas:

- `platform_events.py`: display classification, sustained contact support, front/rear/speed-loss/proxy context helpers, missing/NaN distance handling, and internal visibility defaults.
- `platform_metrics.py`, `units.py`, `setup_diff.py`: threshold boundaries, non-finite values, nested setup sections, and missing/unavailable behavior.
- `lap_detection.py`, `lap_classification.py`: complete/partial laps, invalid lap identifiers, missing lap columns, useful/junk lap tagging, and no setup conclusions for partial laps.
- `compare_math.py`, `did_it_work.py`, `target_zone_classifier.py`,
  `test_discipline.py`: non-finite aggregation, no fake zero deltas, internal
  evaluation math, target-zone gain/loss classes, and discipline scoring. The
  public Compare projection is observation-only and cannot publish Keep/Undo or
  a next setup step.
- `calculated_channels.py`: representative formula contracts for ride-height averages, center/side rake, tire deltas, speed/dynamic pressure, shock velocity fields, and missing/NaN handling.
- `evidence_contracts.py`, `intelligence_service.py`: no-events/no-candidate safety, observation-only import behavior, and no authority outside P19.
- `shock_reader.py`, `stint_intelligence.py`: missing/non-finite telemetry handling, unavailable/limited states, observation-only shock output, and no fake stint averages.
- `tire_dynamics.py`, `vehicle_dynamics.py`, `aero_platform.py`, `aero_coefficients.py`: representative proxy/formula boundaries, confidence behavior, non-finite-as-unavailable handling, proxy warning honesty, and no missing-to-zero behavior for covered helpers.
- `pace_quality.py`, `best_theoretical.py`: evidence caps/deductions, invalid-context caps, low-confidence segment exclusion, and no fake best-theoretical time when valid segment evidence is absent.

Remaining suggested next modules for dedicated tests include `sector_intelligence.py`, `trace_annotations.py`, `correlation_analysis.py`, `weather_context.py`, `drag_scrub.py`, `geometry.py`, `lap_windows.py`, and deeper exhaustive formula coverage for `calculated_channels.py`, `vehicle_dynamics.py`, and `aero_coefficients.py`.

The calculated-channel tests are representative formula contracts, not exhaustive coverage of every derived channel.
