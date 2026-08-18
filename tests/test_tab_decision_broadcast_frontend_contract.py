from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_overview_broadcast_uses_one_fail_closed_decision_contract_in_both_modes() -> None:
    source = _read("ui/src/tabs/OverviewTab.tsx")

    assert 'className="tab-decision-broadcast"' in source
    assert 'className="tab-decision-facts"' in source
    assert 'className="tab-handoff-actions"' in source
    assert "const decisionContextReady = Boolean(lap && setupAvailable && setupTechReady && dataTrustReady);" in source
    assert "actionableRecommendations" not in source
    assert "evidenceQualifiedRecommendations" not in source
    assert "const trustedPrimaryFindings = topEvent && dataTrustReady ? overview.primary_findings : [];" in source
    assert "const broadcastWarning = blockingOverviewBlockers[0]?.message ?? overview.warnings[0] ?? null;" in source
    assert "const topObservedEvent = useMemo" in source
    assert "Evidence only - this signal does not authorize a setup call." in source
    assert "Only the current P19 report can authorize one controlled setup test." in source
    assert 'l.lap_type === "timed" || l.lap_type === "flying"' in source
    assert source.count("{decisionBroadcast}") == 2


def test_overview_handoffs_preserve_scope_and_do_not_offer_setup_when_blocked() -> None:
    source = _read("ui/src/tabs/OverviewTab.tsx")
    evidence = source.split("const buildOverviewEvidence", 1)[1].split("const openTopEvent", 1)[0]
    broadcast = source.split('aria-label="Supporting evidence views"', 1)[1].split("</section>", 1)[0]

    assert 'lapScope: event.lap_number != null ? "single_lap" as const : "run" as const' in evidence
    assert "lapWindowStart: null" in evidence
    assert "lapWindowEnd: null" in evidence
    assert "representativeLap: null" in evidence
    assert "buildZoneEvidence(selection, { lapPct })" in evidence
    assert "channelId: null" in evidence
    assert 'focusEvidence(buildOverviewEvidence(topEvent), "engineer")' in source
    assert "{isLearning && topEvent && decisionContextReady && (" in broadcast
    assert 'data-role="supporting-evidence-navigation"' in broadcast
    assert "Setup impact" in broadcast
    assert "Exact scope: {decisionScope}" in source
    assert 'const visibleRunLabel = isLearning ? `Run ${overview.run_id}` : "Current run"' in source
    assert 'data-run-id={overview.run_id}' in source


def test_laps_broadcast_separates_lap_short_run_and_sustained_pace_authority() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")

    assert 'className="tab-decision-broadcast"' in source
    assert 'className="tab-decision-facts"' in source
    assert 'className="tab-handoff-actions"' in source
    assert 'bestSustainedStint?.run_id === overview.run_id' in source
    assert 'bestWindow?.run_id === overview.run_id' in source
    for state in ["NO CALL", "LAP ONLY", "SHORT RUN", "GUARDED", "PACE READY"]:
        assert f'"{state}"' in source
    assert "paceDecisionWindow.valid_lap_count >= 10" in source
    assert "paceDecisionWindow.window_size >= 10" in source
    assert 'currentStintData?.run_summary?.data_status === "Ready"' in source
    assert "This does not identify a tire or setup cause." in source
    assert "observed falloff alone does not establish tire degradation or a setup cause" in source


def test_laps_broadcast_hands_only_qualified_exact_scope_to_other_tabs() -> None:
    source = _read("ui/src/tabs/LapsTab.tsx")
    handoff = source.split("const openPaceEvidence", 1)[1].split("const openPaceMap", 1)[0]

    assert "if (paceDecisionWindow)" in handoff
    assert "focusWindowEvidence(paceDecisionWindow, workspace)" in handoff
    assert "if (paceDecisionLap)" in handoff
    assert "focusLapEvidence(paceDecisionLap, workspace)" in handoff
    assert 'if (workspace === "engineer")' in handoff
    assert 'lapScope: "run"' in handoff
    assert 'valueBasis: "run_level"' in handoff
    assert 'selectionSource: "laps"' in handoff
    assert "zoneId: null" in handoff
    assert "channelId: null" in handoff
    assert "Exact scope: {paceDecisionScope}" in source
    assert 'selection.selectedMode === "learning"' in source
    assert ': "Current run"' in source
    assert 'disabled={!paceDecisionWindow && !paceDecisionLap}' in source
