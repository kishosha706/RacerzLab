from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shell_clean_lap_and_long_run_readiness_stay_canonical() -> None:
    source = _read("ui/src/App.tsx")
    trust = _read("ui/src/utils/evidenceTrust.ts")
    context = _read("ui/src/components/RunContextBar.tsx")

    eligibility = source.split("const eligiblePaceLaps = useMemo", 1)[1].split(
        "const usefulLapCount", 1
    )[0]
    assert "bestUsefulLapMatchesRun(lap, overview.run_id)" in eligibility
    assert "bestUsefulLapMatchesRun(lap, runId)" in context
    assert "INVALID_PACE_LAP_TAGS" in trust
    for invalid_tag in (
        "PARTIAL",
        "SHORT_RUN",
        "OUT_LAP",
        "COOLDOWN",
        "PIT_ROAD",
        "OFF_TRACK",
        "WRECK_OR_SPIN",
        "INVALID_SPEED_EVENT",
        "CAUTION",
        "YELLOW",
        "RESET",
        "ACTIVE_RESET",
        "SAMPLE_DISCONTINUITY",
        "POSITION_DISCONTINUITY",
        "SPARSE_POSITION_COVERAGE",
        "NON_CREDIBLE_LAP_SAMPLING",
        "INCIDENT_COUNT_INCREASE",
        "INVALID_FOR_PLATFORM_TUNING",
        "NO_SETUP_CONCLUSION",
    ):
        assert f'"{invalid_tag}"' in trust
    assert "INVALID_PACE_LAP_TAGS.has(tag.trim().toUpperCase())" in trust

    continuity = source.split("function longestContinuousEligibleLapBlock", 1)[1].split(
        "function controlledWorkflowUpdatedAt", 1
    )[0]
    assert "new Set(laps.map((lap) => lap.lap_number))" in continuity
    assert "lapNumber === previous + 1 ? current + 1 : 1" in continuity
    assert "const LONG_RUN_REVIEW_MIN_LAPS = 10" in source
    assert "longestContinuousEligibleLapBlock(eligiblePaceLaps)" in source
    assert "Longest clean block" in source
    assert "bank ${longRunLapsNeeded} more consecutive lap" in source
    assert "A ${longestEligibleLapBlock}-lap clean block is available for long-run inspection." in source


def test_run_context_keeps_oval_run_conditions_and_readiness_visible() -> None:
    source = _read("ui/src/components/RunContextBar.tsx")

    assert "run.best_lap_time ?? run.best_lap_time_s" in source
    assert "bestUsefulLapMatchesRun(lap, runId)" in source
    assert "Best ${bestLapTime.toFixed(3)}s" in source
    assert "Track · ${session.track_temp.toFixed(0)}°C" in source
    assert '"Setup · Tech pass"' in source
    assert '"Setup · Tech failed"' in source
    assert "<h4>Run Readiness</h4>" in source
    assert "Clean pace laps" in source
    assert "Best clean lap" in source
    assert "Continuous block" in source
    assert "cleanReadinessLabel" in source
    assert 'data-readiness={cleanLapsNeeded === 0 ? "long-run-review" : "short-run"}' in source
    assert "The 10-lap gate opens long-run inspection" in source
    assert "it does not by itself prove tire degradation or a setup cause" in source


def test_overview_prioritizes_corner_area_and_long_run_without_new_authority() -> None:
    source = _read("ui/src/tabs/OverviewTab.tsx")

    assert "function explicitOvalPhase" in source
    assert "event.event_type" in source
    assert "event.event_subtype" in source
    assert "event.zone_name" in source
    assert "function eventLocationLabel" in source
    assert "bestUsefulLapMatchesRun(candidate, overview.run_id)" in source
    assert "const longestCleanBlock" in source
    assert "const cornerPriorityLabel" in source
    assert "No tuning-valid corner call" in source
    assert "const longRunReadinessLabel" in source
    assert 'data-long-run-state={longRunLapsNeeded === 0 ? "review-ready" : "short-run"}' in source
    assert 'data-oval-priority={topEvent ? priorityPhase?.toLowerCase() ?? "located" : "clear"}' in source
    assert 'data-driver-signal="long-run"><strong>Long run</strong> {longRunReadinessLabel}' in source
    assert 'data-driver-signal="corner-priority"><strong>Corner / area</strong> {cornerPriorityLabel}' in source
    assert 'aria-label="Overview evidence status"' in source
    assert "<strong>What next:</strong>" not in source
    assert "Import observations cannot authorize a setup change." in source
    assert "Hold the setup. If long-run pace matters" not in source
    assert "Invalid, pit, cooldown, wreck, reset, and partial laps break the chain." in source
    assert "they do not prove tire degradation or a setup cause" in source
    assert "That observation narrows the review but does not authorize a setup change." in source


def test_first_run_and_navigation_copy_teaches_the_driver_flow() -> None:
    source = _read("ui/src/App.tsx")

    assert "clean-lap readiness, setup identity" in source
    assert "Junk laps stay excluded; 10 consecutive clean laps open long-run inspection." in source
    assert "See the corner or area priority, then verify one trustworthy next step." in source
    assert "Driver flow" in source
    assert "Read · verify · test" in source
    assert "Session · {currentSession?.run_ids.length ?? sessionRunOptions.length} run" in source
