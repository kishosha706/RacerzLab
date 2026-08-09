from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compare_leads_with_an_oval_driver_brief() -> None:
    source = _read("ui/src/tabs/CompareTab.tsx")

    assert "function OvalComparisonBrief" in source
    assert 'className="oval-compare-brief"' in source
    assert 'data-authority="comparison-only"' in source
    for label in (
        "Clean-lap pace",
        "Where it changed",
        "Driver match",
        "Right-front watch",
        "Test discipline",
    ):
        assert label in source
    for detail in ("Where", "Driver", "RF / tires", "Setup delta"):
        assert f">{detail}<" in source
    assert "does not authorize a new setup change by itself" in source


def test_whole_car_compare_is_reachable_inside_the_laps_workflow() -> None:
    laps = _read("ui/src/tabs/LapsTab.tsx")

    assert 'const WholeCarCompareTab = React.lazy' in laps
    assert 'import("./CompareTab")' in laps
    assert "Whole-car comparison" in laps
    assert "Open whole-car workbook" in laps
    assert 'data-comparison-readiness={runHistory.length >= 2 ? "ready" : "needs-run"}' in laps
    assert "<WholeCarCompareTab runs={runHistory} currentRunId={overview.run_id} />" in laps
    assert "Match car, track, fuel, tire age, weather, and line" in laps


def test_oval_brief_keeps_short_run_and_noise_claims_honest() -> None:
    source = _read("ui/src/tabs/CompareTab.tsx")

    assert 'pace.is_significant === true' in source
    assert "does not clear the empirical noise floor" in source
    assert "Long-run read withheld" in source
    assert "too short for a strong wear or falloff conclusion" in source
    assert "observed comparison only" in source
    assert "observed speed, not a cause assignment" in source
    assert "Causal credit is limited" in source


def test_compare_result_is_bound_to_the_selected_runs_laps_and_zone() -> None:
    source = _read("ui/src/tabs/CompareTab.tsx")

    assert "const comparisonRequestSequenceRef = useRef(0);" in source
    assert "const sequence = ++comparisonRequestSequenceRef.current;" in source
    assert "if (sequence !== comparisonRequestSequenceRef.current) return;" in source
    for expression in (
        "res.baseline_run_id === request.baseline_run_id",
        "res.test_run_id === request.test_run_id",
        "res.baseline_lap === request.baseline_lap",
        "res.test_lap === request.test_lap",
        "res.target_zone_start_pct - request.target_zone_start_pct",
        "res.target_zone_end_pct - request.target_zone_end_pct",
    ):
        assert expression in source
    assert "No comparison metrics are shown" in source
    assert "JSON.parse(raw)" in source
    assert 'typeof parsed.detail === "string"' in source
    assert 'className="warning-banner compare-error-recovery" role="alert"' in source


def test_oval_brief_uses_responsive_open_visual_hierarchy() -> None:
    styles = _read("ui/src/styles.css")

    for selector in (
        ".oval-compare-brief",
        ".oval-compare-header",
        ".oval-compare-facts",
        ".oval-compare-fact",
        ".oval-compare-actions",
        ".oval-compare-coaching",
        ".oval-whole-car-launch",
        ".oval-whole-car-workbook",
    ):
        assert selector in styles
    brief_block = styles.split(".oval-compare-brief {", 1)[1].split("}", 1)[0]
    assert "radial-gradient" in brief_block
    assert "linear-gradient" in brief_block
    assert "overflow: hidden" in brief_block
    assert "@media (max-width: 1080px)" in styles
    assert "@media (max-width: 720px)" in styles
