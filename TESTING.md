# Testing — RaceLab Garage

## Fast Dev Loop (default)

```powershell
# Skip slow .ibt-dependent and integration tests (<1s)
python -B -m pytest -m "not slow and not integration" -q
```

Runs ~160 unit tests: comparison math, notebook CRUD, track matching, slip ratios, drag/scrub, geometry, session logic, constants, local-config checks, vectorized parity (83 fast), track map (20). All pure Python or synthetic data — no `.ibt` file needed.

## Full Suite (pre-commit / pre-push)

```powershell
# All tests including .ibt import and telemetry pipeline (~90s)
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

Runs ~52 tests that import real `.ibt` files: parser validation, telemetry normalization, calculated channels, platform events, API contracts, persistence.

## Vectorized Engine Benchmarks

```powershell
pip install pytest-benchmark
python -B -m pytest -m slow tests/test_vectorized_parity.py
```

Benchmark tests in `TestBenchmark` class skip gracefully if `pytest-benchmark` is not installed (class-level `pytest.importorskip`).

## Test Categories

| Marker | What | Count | Time |
|---|---|---|---|
| (none / unit) | Pure logic, mocks, synthetic data | ~160 | <1s |
| `slow` | Real `.ibt` import, telemetry pipeline, persistence | ~52 | ~90s |
| `integration` | Notebook/service integration | ~20 | ~2s |

## Skipping Slow Tests in CI

```yaml
# GitHub Actions example
- run: pytest -m "not slow"
- run: pytest -m "slow"  # only on full branches
```

## Writing New Tests

- Pure math/logic → no marker needed (runs in fast loop)
- `.ibt` dependent → add `pytestmark = pytest.mark.slow` at file level
- Service/API integration → add `@pytest.mark.integration`
- See `pyproject.toml` for registered markers
