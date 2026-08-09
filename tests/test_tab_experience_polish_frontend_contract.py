from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_overview_broadcast_leads_with_honest_pace_context_and_next_move() -> None:
    source = _read("ui/src/tabs/OverviewTab.tsx")
    trust = _read("ui/src/utils/evidenceTrust.ts")

    assert "const usefulTimedLapTimes = useMemo" in source
    assert "bestUsefulLapMatchesRun(candidate, overview.run_id)" in source
    assert "lap.is_useful" in trust
    assert "lap.is_complete" in trust
    assert "INVALID_PACE_LAP_TAGS" in trust
    assert "const bestToMedianDelta" in source
    assert "quicker than clean-lap median" in source
    assert "<p><strong>Why:</strong> {decisionDetail}</p>" in source
    assert "<p><strong>What next:</strong> {decisionNext}</p>" in source
    assert "The median is descriptive context, not evidence that setup caused the gap." in source
    assert "Inspect the exact event location" in source
    assert 'matches: ["setup", "snapshot", "carsetup"]' not in source
    assert '"setup snapshot",' in source
    assert '"carsetup unavailable",' in source


def test_laps_broadcast_compares_clean_lap_and_stint_without_inventing_cause() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    assert "const sustainedToBestGap" in source
    assert "const paceTrendLabel" in source
    assert "const paceDecisionNext" in source
    assert "vs fastest clean lap" in source
    assert "across this block" in source
    assert "pit-road, cooldown, wreck, invalid-speed, or partial-lap flags" in source
    assert "compare the next qualified run at matched track positions" in source
    assert "their gap is context, not a reason to change the car" in source
    assert "This does not identify a tire or setup cause." in source


def test_platform_race_broadcast_is_compact_and_learning_keeps_diagnostic_depth() -> None:
    source = _read("ui/src/tabs/PlatformTab.tsx")

    assert "const platformBroadcastWhy" in source
    assert "const platformBroadcastNext" in source
    assert "const platformSignalSummary" in source
    assert "<p><strong>Why:</strong> {platformBroadcastWhy}</p>" in source
    assert "<p><strong>What next:</strong> {platformBroadcastNext}</p>" in source
    assert 'selection.selectedMode === "learning" && (\n        <section\n          className="platform-decision-card"' in source
    assert "unmeasured mechanisms remain unknown" in source
    assert '`Current run · Lap ${traceLap}`' in source
    assert 'selection.selectedMode === "learning"' in source
    assert 'data-authority="withheld"' in source


def test_setup_broadcast_explains_reference_link_and_keeps_extra_handoffs_in_learning() -> None:
    source = _read("ui/src/tabs/SetupTab.tsx")

    assert "const setupDecisionWhy" in source
    assert "const setupDecisionNext" in source
    assert "const setupHeadlineMetric" in source
    assert "<p><strong>Why:</strong> {setupDecisionWhy}</p>" in source
    assert "<p><strong>What next:</strong> {setupDecisionNext}</p>" in source
    assert "The link narrows inspection; it does not choose a target." in source
    assert "Garage snapshot missing for this run" in source
    assert 'selection.selectedMode === "learning" && (\n        <div className="toolbar-actions tab-handoff-actions" aria-label="Continue this setup evidence">' in source
    assert "disabled={!hasQualifiedEvidenceLink}" in source
    assert "selectedEvent?.trusted_overview_event" in source
    assert "selectedEvent.valid_for_tuning" in source
    assert 'data-authority="withheld"' in source
