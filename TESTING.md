# Testing — RaceLab Garage

## Fast Dev Loop (default)

```powershell
# Skip slow .ibt-dependent tests (~0.2s)
python -B -m pytest -p no:cacheprovider -m "not slow"
```

Runs ~118 unit tests: comparison math, notebook CRUD, track matching, slip ratios, drag/scrub, geometry, session logic, constants, local-config checks. All pure Python — no `.ibt` file needed.

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

## Test Categories

| Marker | What | Count | Time |
|---|---|---|---|
| (none / unit) | Pure logic, mocks, synthetic data | ~118 | <1s |
| `slow` | Real `.ibt` import, telemetry pipeline, persistence | ~52 | ~90s |

## Skipping Slow Tests in CI

```yaml
# GitHub Actions example
- run: pytest -m "not slow"
- run: pytest -m "slow"  # only on full branches
```

## Writing New Tests

- Pure math/logic → no marker needed (runs in fast loop)
- `.ibt` dependent → add `pytestmark = pytest.mark.slow` at file level
- See `pyproject.toml` for registered markers
