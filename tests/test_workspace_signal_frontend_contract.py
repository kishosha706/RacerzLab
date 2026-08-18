from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shell_broadcasts_each_workspace_status_from_current_owned_state() -> None:
    app = _read("ui/src/App.tsx")

    assert "type WorkspaceSignalTone" in app
    assert "const workspaceSignals = useMemo" in app
    assert "bestUsefulLapMatchesRun(lap, overview.run_id)" in app
    assert "bestUsefulLapMatchesRun(overview.best_useful_lap, overview.run_id)" in app
    assert 'currentPlatformEventsLoadStatus === "ready"' in app
    assert "setupSnapshotMatchesRun(overview.setup_snapshot, overview.run_id)" in app
    assert "overviewBlockerBlocksDecision" in app
    assert "performanceBlockerBlocksDecision" in app
    assert 'laps: performanceBlockingBlockers.length > 0' in app
    assert "overviewArchiveVerified" in app
    assert '!overviewArchiveVerified || overviewBlockingBlockers.length > 0' in app
    assert 'short: "Recover"' in app
    assert "overview?.events.filter(telemetryEventIsActionable).length" in app
    assert "currentControlledWorkflow" in app
    assert 'className="nav-rail-signal"' in app
    assert "Status: ${signal.short}. ${signal.detail}" in app
    assert 'className="shell-workspace-broadcast"' in app
    assert 'role="status"' in app
    assert "currentWorkspaceSignal.detail" in app


def test_workspace_content_reacts_to_complete_lap_and_window_scope() -> None:
    app = _read("ui/src/App.tsx")
    dependencies = app.split("const workspaceContent = useMemo", 1)[1].split(
        "if (engineStatus ===",
        1,
    )[0].rsplit("],", 1)[0]

    for dependency in (
        "selection.selectedLap",
        "selection.selectedLapScope",
        "selection.selectedLapWindowStart",
        "selection.selectedLapWindowEnd",
        "selection.selectedRepresentativeLap",
    ):
        assert dependency in dependencies


def test_shell_workspace_signals_never_claim_setup_authority() -> None:
    app = _read("ui/src/App.tsx")
    signal_block = app.split("const workspaceSignals = useMemo", 1)[1].split(
        "const signalWorkspace", 1
    )[0]

    assert "authorized" not in signal_block.lower()
    assert 'short: "Advisory"' in signal_block
    assert 'short: "No call"' in signal_block
    assert 'short: "Tech failed"' in signal_block
    assert "exact server-owned A/B/A2 workflow" in signal_block


def test_shell_withholds_arbitrary_workflow_when_session_has_multiple_active_tests() -> None:
    app = _read("ui/src/App.tsx")

    assert "const scopedActiveWorkflows = workflows.filter" in app
    assert "if (scopedActiveWorkflows.length > 1)" in app
    assert "setActiveControlledWorkflowAmbiguous(true)" in app
    assert 'short: "Resolve"' in app
    assert "Multiple active workflows share this session" in app
    assert 'short: "Measure"' in app


def test_dial_in_broadcasts_workflow_slot_scope_and_advisory_authority() -> None:
    dial_in = _read("ui/src/tabs/DialInTab.tsx")

    assert 'className="tab-decision-broadcast"' in dial_in
    assert 'data-authority={controlledTestAuthorityReady ? "server-verified" : "withheld"}' in dial_in
    assert 'data-run-id={broadcastRunId}' in dial_in
    assert 'data-current-run-id={overview.run_id}' in dial_in
    assert 'data-plan-run-id={workflow?.source_run_id}' in dial_in
    assert 'data-current-run-authority={currentRunIsUnverifiedStageCandidate ? "unverified-stage-candidate"' in dial_in
    assert "setupSnapshotMatchesRun(overview.setup_snapshot, overview.run_id)" in dial_in
    assert '{workflowPlanCrossesCurrentRun ? "Current setup" : "Setup"}' in dial_in
    assert '<strong>{setupAvailable ? "Recorded" : "Unavailable"}</strong>' in dial_in
    assert 'workflowValue?.status === "scored" && workflowValue.packet.decision === "test"' in dial_in
    assert '"Verified history"' in dial_in
    assert "Controlled test active · next stage" in dial_in
    assert "Measurement workflow active · no setup change approved" in dial_in
    assert "Build the server-verified plan before treating any setup direction as authorized." in dial_in
    assert "Dial-In will not create a second plan until the server-owned workflow catalog is known." in dial_in
    assert 'className="tab-decision-facts"' in dial_in
    assert 'className="tab-handoff-actions"' in dial_in
    assert 'setWorkspace("engineer", "manual")' in dial_in
    assert 'setWorkspace("laps", "manual")' in dial_in
    assert 'setWorkspace("setup_impact", "manual")' in dial_in


def test_engineer_broadcast_uses_the_same_exact_action_and_citation_gate() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert 'className="tab-decision-broadcast"' in engineer
    assert 'data-authority={actionAuthorized ? "server-verified" : "withheld"}' in engineer
    assert 'data-run-id={runId}' in engineer
    assert 'data-briefing-scope="run"' in engineer
    assert "Briefing scope <strong>Run</strong>" in engineer
    assert "Question scope <strong>{questionScopeLabel}</strong>" in engineer
    assert "const primaryEvidenceCitation = actionCitations[0]" in engineer
    assert "One controlled test is authorized" in engineer
    assert "Measure before changing the setup" in engineer
    assert "No setup action is authorized" in engineer
    assert "Setup authority <strong>{actionAuthorized ? \"Authorized\" : \"Withheld\"}</strong>" in engineer
    assert "onNavigateCitation(primaryEvidenceCitation)" in engineer
    assert 'setWorkspace(actionAuthorized ? "dial_in" : "platform_trace", "engineer")' in engineer
    assert "Evidence first · no engineering call" in engineer
    assert "Recover the missing laps or channels" in engineer


def test_broadcast_layout_stays_compact_and_responsive() -> None:
    styles = _read("ui/src/styles.css")

    assert ".tab-decision-broadcast" in styles
    assert ".tab-decision-facts" in styles
    assert ".tab-handoff-actions" in styles
    assert ".shell-workspace-broadcast" in styles
    assert ".nav-rail-signal" in styles
    assert "font-size: 0.68rem" in styles
    assert "width: 142px" in styles
    responsive = styles.split("@media (max-width: 820px)", 1)[1]
    assert ".shell-workspace-broadcast" in responsive
    assert "display: none" in responsive
    assert "grid-template-columns: 1fr" in responsive
