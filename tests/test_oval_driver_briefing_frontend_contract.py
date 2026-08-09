from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_laps_oval_brief_separates_short_run_from_race_run_without_estimation() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    assert "const shortRunAveragePriority = [5, 3] as const;" in source
    assert "const raceRunAveragePriority = [60, 50, 40, 30, 25, 20] as const;" in source
    assert "firstAvailableRunAverage(currentRunSummary, shortRunAveragePriority)" in source
    assert "firstAvailableRunAverage(currentRunSummary, raceRunAveragePriority)" in source
    assert "!blockingRunWarning && !stintRequestFailed" in source
    assert 'data-driver-briefing="oval-stint"' in source
    assert 'data-authority="observation-only"' in source
    assert "Short vs race run" in source
    assert "Need 20 clean laps" in source
    assert ".filter((stint) => stint.is_best_for_size && stint.lap_count >= 20)" in source
    assert '"Need 20 clean"' in source
    assert "The app will not estimate race-run hold from a short block." in source


def test_loaded_side_tire_reads_fail_closed_until_corner_and_long_run_evidence_exist() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")
    readiness = source.split("function cornerTireReadiness", 1)[1].split(
        "function stintBucket", 1
    )[0]

    assert "stint.valid_lap_count < 10" in readiness
    assert "stint.valid_lap_count !== stint.lap_count" in readiness
    assert "stint.end_lap - stint.start_lap + 1 !== stint.lap_count" in readiness
    assert "The app will not bridge separate blocks" in readiness
    assert "stint.lap_points.some((point) => !point.valid)" in readiness
    assert "will not bridge them" in readiness
    assert 'normalized.includes("LIMITED")' in readiness
    assert "!normalized.includes(corner)" in readiness
    assert "does not separate ${corner} temperature and wear history" in readiness
    assert "thermal and wear causes are not separated" in readiness
    assert 'cornerTireReadiness(\n    "RF"' in source
    assert 'cornerTireReadiness(\n    "RR"' in source
    assert "Boolean(blockingRunWarning || stintRequestFailed || !backendStintReady)" in source
    assert 'data-corner="RF" data-state={rfTireReadiness.state}' in source
    assert 'data-corner="RR" data-state={rrTireReadiness.state}' in source
    assert "[...bestWindowCards, ...stints]" in source
    assert "stint.end_lap - stint.start_lap + 1 === stint.lap_count" in source


def test_balance_drift_and_clean_lap_ledger_use_only_exact_qualified_evidence() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")
    observation = source.split("const balanceObservation = useMemo", 1)[1].split(
        "const openPaceEvidence", 1
    )[0]

    assert "paceDecisionWindow.valid_lap_count < 10" in observation
    assert "paceDecisionWindow.valid_lap_count !== paceDecisionWindow.window_size" in observation
    assert "new Set(cleanUsefulLaps.map((lap) => lap.lap_number))" in observation
    assert "event.run_id === overview.run_id" in observation
    assert "event.valid_for_tuning" in observation
    assert "eligibleLapNumbers.has(event.lap_number)" in observation
    assert "/YAW|ROTATION|BALANCE/.test(event.event_type)" in observation
    assert "event.source_channels.length > 0" in observation
    assert "This is an observation, not a tire or setup cause." in observation
    assert "bestUsefulLapMatchesRun(lap, overview.run_id)" in source
    assert "Out-laps, cooldowns, pit-road laps, wrecks, invalid-speed laps, and partial laps never drive the setup read." in source


def test_setup_driver_snapshot_is_run_owned_and_one_change_guard_is_non_authoritative() -> None:
    source = _read("ui/src/tabs/SetupTab.tsx")

    assert "overview.setup_snapshot.run_id !== overview.run_id" in source
    assert 'data-setup-reference="run-owned"' in source
    assert 'data-run-id={overview.run_id}' in source
    assert "Setup at a glance" in source
    assert "setupTechState" in source
    assert "setupModifiedState" in source
    assert "rfColdPressurePsi" in source
    assert "rrColdPressurePsi" in source
    assert "Oval decision anchors" in source
    assert 'data-one-change-state={changeGuard.state}' in source
    assert 'data-authority="withheld"' in source
    assert "setupComparisonContextMatches" in source
    assert "basket.baseline.car === currentCarIdentity" in source
    assert "basket.baseline.track === currentTrackIdentity" in source
    assert "A one-change audit requires the same known car and track configuration." in source
    assert 'headline: "No displayed changes"' in source
    assert 'headline: "One displayed change"' in source
    assert "${setupDiffRows.length} displayed changes" in source
    assert "Multiple tracked differences reduce causal confidence." in source
    assert "Displayed differences are an audit aid, never permission to change the car." in source
    assert "Dial-In must still verify the complete snapshot, legality, and evidence before a test." in source
