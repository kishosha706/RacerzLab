# Test Audit - RaceLab Garage

Reviewed: 2026-08-10

This inventory groups current high-value contract coverage. Exact collection
counts change with the repository and are reported by the release run, not
frozen in this document.

## Telemetry ownership and parity

| Contract | Primary coverage |
|---|---|
| `.ibt` header, variable declarations, source fingerprint | `test_ibt_header.py`, `test_ibt_reader_warnings.py` |
| Lossless archive and capability manifest | `test_universal_telemetry.py` |
| Frame-native production path and row parity | `test_vectorized_parity.py`, `test_frame_native_overview_parity.py` |
| Canonical aliases, units, missing values | `test_calculated_channels.py`, `test_units.py`, `test_session_yaml.py` |
| Cache/source/schema identity | `test_repository_read_identity.py`, `test_persistence.py` |

Real-fixture tests remain protected and skip only when their explicitly named
external source is unavailable. A derived cache without its original `.ibt`
cannot prove reproducibility.

## Eligibility and physical alignment

| Contract | Primary coverage |
|---|---|
| Junk/partial/pit/reset lap exclusion | `test_lap_detection.py`, `test_lap_classification.py`, `test_lap_windows.py` |
| Nearby-car covariate and attribution block | `test_proximity_context.py`, `test_controlled_workflow_service.py` |
| Position-based alignment and gap truth | `test_time_alignment.py`, `test_comparison.py` |
| One-change and context discipline | `test_test_discipline.py`, `test_setup_controls.py` |

## Non-P19 authority denial

These regressions are mandatory because they prove that observational surfaces
cannot become a second setup-policy path.

| Surface | Protected behavior |
|---|---|
| Import/Overview/events | `test_evidence_contracts.py`, `test_run_intelligence_api.py`, `test_observation_intelligence.py`: no recommendation list, crew summary, next test, or event action fields |
| Compare | `test_compare_greenfield_contract.py`, `test_comparison.py`, `test_did_it_work.py`: measured observations only; no public Keep/Undo or next step |
| Platform | `test_platform.py`, `test_platform_chart_visibility.py`, `test_non_p19_authority_frontend_contract.py`: structured events only, no legacy-event/action fallback |
| Shock Reader | `test_shock_reader.py`, `test_shock_reader_api.py`: setup authority withheld; no click/direction/target/action fields |
| Dial-In/setup catalog | `test_dial_in_api.py`, `test_dial_in_frontend_contract.py`, `test_dial_in_service.py`, `test_setup_knowledge.py`, `test_setup_evidence_adapter.py`: public hypotheses may name control areas but not direction, increments, targets, or policy; direct-action command surfaces stay absent |
| Engineering Awareness | `test_engineering_awareness_projection.py`, `test_engineering_awareness_service.py`: `p20.awareness.v2` remains observation-only and carries no P19 mission/leverage/policy fields |
| Notebook | `test_notebook.py`, `test_notebook_authority_frontend_contract.py`: observation CRUD only; strict rejection of verdict/setup-change/next-step/test-plan/setup-memory fields |
| UI | `test_non_p19_authority_frontend_contract.py`, `test_navigation_frontend_contract.py`: no reachable stale authority surface |

Removed Crew Chief/Test Director preview endpoints and direct setup-query command
surfaces have no compatibility exemption. Route/CLI residual scans are part of
the audit.

## P19 authority and durable policy

| Contract | Primary coverage |
|---|---|
| Canonical reasoning and evidence independence | `test_intelligence_reasoning_hardening.py`, `test_internal_intelligence_service.py` |
| Immutable mission and attempt scope | `test_measurement_attempt_authority.py`, `test_controlled_workflow_service.py` |
| A/B/A2 stage ownership and scoring | `test_controlled_workflow_service.py`, `test_experiment_service.py` |
| Setup/reasoning identity and stale-response denial | `test_intelligence_response_identity.py`, `test_intelligence_response_trust_frontend.py` |
| Durable per-policy Keep/Undo and stop reconstruction | `test_controlled_workflow_service.py`, `test_intelligence_reasoning_hardening.py` |
| P26 graph/projection authority ceiling | `test_vehicle_systems_intelligence.py` |

The historical filenames `test_test_director.py` and
`test_crew_chief_packet.py` cover internal server-side workflow assembly. They
do not imply that public preview endpoints exist.

## Physics and semantic honesty

| Contract | Primary coverage |
|---|---|
| Proxy/measurement separation | `test_contract.py`, `test_evidence_contracts.py`, `test_drag_scrub.py` |
| Tire snapshots and short-run gates | `test_p3_engineering_systems.py`, `test_stint_intelligence.py` |
| Shock/platform observations | `test_platform_shock_channels.py`, `test_shock_reader.py` |
| Corner-weight and setup semantics | `test_vehicle_systems_intelligence.py`, `test_setup_page_contract.py` |
| Traffic-contaminated stint denial | `test_stint_state_intelligence.py`, `test_p3_observation_bridge.py` |

## Release gate

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q
python -m ruff check .
npm run typecheck:ui
npm run ui:build
git diff --check
```

For release-trust claims, also run the pinned real-fixture audit with exact
source SHA-256, schema fingerprint, record count, and declared-channel count.
The release is not proven by synthetic tests alone.
