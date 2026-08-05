from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compare_traces_intentionally_renders_physical_time_surface() -> None:
    traces = _read("ui/src/components/DeltaTracesView.tsx")
    surface = _read("ui/src/components/TimeDeltaComparison.tsx")
    laps = _read("ui/src/tabs/LapsTab.tsx")

    assert "<TimeDeltaComparison" in traces
    assert "fetchCompareTimeAnalysis" in surface
    assert 'aria-label="Physical-position time comparison"' in surface
    assert "Cumulative Time" in surface
    assert "showPhysicalTimeComparison" in laps
    assert "<TimeDeltaComparison" in laps
    assert "Where the Time Changed" in laps


def test_time_surface_preserves_honest_gaps_and_synchronized_cursor_evidence() -> None:
    surface = _read("ui/src/components/TimeDeltaComparison.tsx")

    assert "if (value == null)" in surface
    assert "if (current) paths.push(current)" in surface
    assert "data.phase_by_position[cursorIndex]" in surface
    assert "data.alignment[cursorIndex]" in surface
    assert "data.incremental_basis[cursorIndex]" in surface
    assert "Incomplete matched coverage: no whole-window time delta is reported." in surface
    assert 'aria-label="Explore the cumulative time delta by track position"' in surface


def test_time_surface_exposes_decision_metrics_and_learning_detail() -> None:
    surface = _read("ui/src/components/TimeDeltaComparison.tsx")

    for label in (
        "Selected time delta",
        "Theoretical opportunity",
        "Repeatable opportunity",
        "Largest phase effects",
    ):
        assert label in surface
    assert "+{data.warnings.length - 2} more warnings in Learning Mode" in surface
    assert 'selection.selectedMode === "learning"' in surface
    assert "data.noise.context_complete" in surface
    assert "data.gain_origin_pct" in surface
    assert "data.surrender_pct" in surface
