# Testing - RaceLab Garage

## Fast Dev Loop (default)

```powershell
# Skip slow .ibt-dependent and integration tests
python -B -m pytest -m "not slow and not integration" -q
```

Runs the fast unit subset (exact count changes over time): comparison math,
observation-Notebook CRUD, track matching, slip ratios, drag/scrub, geometry,
session logic, constants, local-config checks, vectorized parity, and track map.
No real `.ibt` file required.

## Core Robustness Contracts

```powershell
python -B -m pytest tests/test_platform_events.py tests/test_platform_metrics.py tests/test_units.py tests/test_setup_diff.py tests/test_lap_detection.py tests/test_lap_classification.py tests/test_compare_math.py tests/test_did_it_work.py tests/test_target_zone_classifier.py tests/test_test_discipline.py tests/test_calculated_channels.py -q
```

This focused suite locks high-value pure logic behavior: platform event
visibility/context gates, missing/NaN handling, setup-diff discipline, lap
detection/classification, internal comparison evaluation math, public
observation classification, target-zone classification, and representative
calculated-channel formula contracts. `tests/test_calculated_channels.py` is
intentionally representative, not exhaustive coverage of every derived
channel.

`tests/test_evidence_contracts.py` and `tests/test_run_intelligence_api.py`
cover the observation-only import boundary and the sole P19 setup-authority
path.

## Greenfield Authority Gate

```powershell
python -B -m pytest `
  tests/test_compare_greenfield_contract.py `
  tests/test_non_p19_authority_frontend_contract.py `
  tests/test_notebook.py `
  tests/test_notebook_authority_frontend_contract.py `
  tests/test_shock_reader.py `
  tests/test_shock_reader_api.py `
  tests/test_dial_in_api.py `
  tests/test_dial_in_frontend_contract.py `
  tests/test_dial_in_service.py `
  tests/test_setup_knowledge.py `
  tests/test_setup_evidence_adapter.py `
  tests/test_engineering_awareness_projection.py `
  tests/test_engineering_awareness_service.py `
  tests/test_measurement_attempt_authority.py `
  tests/test_intelligence_response_identity.py `
  tests/test_intelligence_response_trust_frontend.py -q
```

This gate proves that non-P19 public surfaces cannot publish setup direction,
exact targets, Keep/Undo, stop-testing, or durable test policy; strict schemas
reject removed compatibility fields; and intelligence authority is identity
bound. Legacy Crew Chief/Test Director preview routes, Notebook test-plan/setup-
memory routes, and direct setup-query command surfaces are intentionally absent.

Additional dedicated high-impact analysis tests cover `shock_reader.py`, `stint_intelligence.py`, `tire_dynamics.py`, `vehicle_dynamics.py`, `aero_platform.py`, `aero_coefficients.py`, `pace_quality.py`, and `best_theoretical.py`. These are synthetic-data tests focused on unavailable states, non-finite numeric handling, proxy honesty, confidence behavior, and deterministic output.

Roadmap engineering contracts are covered by `test_evidence_contracts.py`,
`test_time_alignment.py`, `test_phase_engineering.py`,
`test_p3_engineering_systems.py`, `test_test_director.py`,
`test_crew_chief_packet.py`, `test_setup_learning_service.py`, and
`test_advanced_experimentation.py`. `test_test_director.py` and
`test_crew_chief_packet.py` exercise server-side P19 assembly internals; their
historical names do not define public preview endpoints. These suites include
hostile missing-data, mismatched-context, junk-lap, unsupported-causality, and
forged-client-evidence cases.

## Full Suite (pre-commit / pre-push)

```powershell
# Complete Python + UI quality gate
npm run check

# Python-only suite including .ibt import and telemetry pipeline
python -B -m pytest -p no:cacheprovider -q
```

P31 also requires the behavioral and truth-boundary gates:

```powershell
cd ui
npm test
npx tsc --noEmit
npm run build
cd ..

python -B -m pytest -q `
  tests/test_run_intelligence_snapshot.py `
  tests/test_controlled_workflow_service.py `
  tests/test_p19_release_proofs.py `
  tests/test_p3_engineering_systems.py `
  tests/test_p3_observation_bridge.py `
  tests/test_engineering_awareness_service.py `
  tests/test_vehicle_systems_intelligence.py `
  tests/test_crew_chief_contracts.py `
  tests/test_compare_math.py
```

The protected Atlanta source is re-imported when manifest schema changes. A
stale cache is a failed truth gate, not permission to lower the schema version.
Workflow catalog performance is tested with 10,000 unrelated histories and the
semantic snapshot is tested with concurrent equivalent requests.

The synthetic and contract suite runs without a private telemetry file. Tests that require a real Talladega `.ibt` fixture skip when the fixture is unavailable. For full fixture validation, set:
```
C:\Users\Soulj\Documents\iRacing\telemetry\stockcars camarozl12018_talladega 2026-05-07 15-05-45.ibt
```

Override via:
```powershell
$env:RACELAB_TALLADEGA_IBT="C:\path\to\baseline.ibt"
pytest
```

## Slow Tests Only

```powershell
python -B -m pytest -p no:cacheprovider -m "slow"
```

Runs the slow `.ibt`-dependent subset: parser validation, telemetry normalization, calculated channels, platform events, API contracts, and persistence.

## Vectorized Engine Benchmarks

```powershell
pip install pytest-benchmark
python -B -m pytest -m slow tests/test_vectorized_parity.py
```

Benchmark tests in `TestBenchmark` skip gracefully if `pytest-benchmark` is not installed.

## Test Categories

| Marker | What | Count | Time |
|---|---|---|---|
| (none / unit) | Pure logic, mocks, synthetic data | Varies | Fast |
| `slow` | Real `.ibt` import, telemetry pipeline, persistence | Varies | Slow |
| `integration` | Observation persistence and service/API integration | Varies | Moderate |

## Skipping Slow Tests in CI

```yaml
# GitHub Actions example
- run: pytest -m "not slow"
- run: pytest -m "slow"  # only on full branches
```

## Writing New Tests

- Pure math/logic -> no marker needed (runs in fast loop)
- `.ibt` dependent -> add `pytestmark = pytest.mark.slow` at file level
- Service/API integration -> add `@pytest.mark.integration`
- See `pyproject.toml` for registered markers

Last reviewed: 2026-08-13. Exact suite totals belong in the release/audit
evidence for the commit being tested; category counts intentionally remain
non-fixed here.
