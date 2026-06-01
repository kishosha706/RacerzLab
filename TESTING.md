# Testing - RaceLab Garage

## Fast Dev Loop (default)

```powershell
# Skip slow .ibt-dependent and integration tests
python -B -m pytest -m "not slow and not integration" -q
```

Runs the fast unit subset (exact count changes over time): comparison math, notebook CRUD, track matching, slip ratios, drag/scrub, geometry, session logic, constants, local-config checks, vectorized parity, and track map. No real `.ibt` file required.

## Full Suite (pre-commit / pre-push)

```powershell
# All tests including .ibt import and telemetry pipeline
python -B -m pytest -p no:cacheprovider -q
```

Requires a Talladega `.ibt` fixture at:
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
| `integration` | Notebook/service integration | Varies | Moderate |

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

Last verified: 2026-06-01 (counts intentionally non-fixed to avoid stale status drift).
