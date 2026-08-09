from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_platform_resources_are_keyed_cleared_and_recoverable() -> None:
    app = _read("ui/src/App.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    priority = _read("ui/src/components/PriorityRail.tsx")

    assert 'JSON.stringify({ run_id: overview.run_id, lap: platformTargetLap })' in app
    assert 'type PlatformLoadStatus = "idle" | "loading" | "ready" | "clear" | "unavailable" | "error";' in app
    assert 'platformEventsLoadState.requestKey === platformRequestKey' in app
    assert 'traceLoadState.requestKey === platformRequestKey' in app
    assert '["ready", "clear"].includes(platformEventsLoadState.status)' in app
    assert 'traceLoadState.status === "ready"' in app

    assert 'setPlatformEventsLoadState({ requestKey: platformRequestKey, status: "loading", error: null });' in app
    assert 'setTraceLoadState({ requestKey: platformRequestKey, status: "loading", error: null });' in app
    assert app.index("setPlatformEvents([]);") < app.index("fetchPlatformEventsReport(overview.run_id")
    assert app.index("setTrace(null);") < app.index("fetchTrace(overview.run_id")
    assert 'status: "error"' in app
    assert "setPlatformEventsRetryToken((token) => token + 1)" in app
    assert "setTraceRetryToken((token) => token + 1)" in app
    assert "nextTrace.run_id !== overview.run_id || nextTrace.lap !== platformTargetLap" in app
    assert "report.run_id === overview.run_id" in app
    assert "report.lap === platformTargetLap" in app
    assert "report.events.every((event) => event.lap === platformTargetLap)" in app
    assert "Platform findings did not match the selected run and lap." in app

    assert 'effectiveTraceLoadStatus === "error"' in platform
    assert "Trace data could not be loaded for this run and lap." in platform
    assert "Retry trace" in platform
    assert 'platformEventsLoadStatus === "error"' in platform
    assert "Platform evidence could not be loaded." in platform
    assert "Retry platform evidence" in platform
    assert platform.count("Retry platform evidence") == 1
    assert 'selection.selectedMode === "learning" && traceLoadError' in platform
    assert 'selection.selectedMode === "learning" && platformEventsLoadError' in platform
    assert "No platform diagnostic events were returned for this lap." in platform
    assert "missing telemetry remains unavailable, never safe or zero" in platform
    assert 'platformEventsLoadStatus === "unavailable"' in platform
    assert 'platformEventsLoadStatus === "clear"' in platform
    assert "Supported platform risk checks are clear for this eligible lap." in platform
    assert "other mechanisms are not implied safe" in platform

    assert "shockReaderRequestKey" in platform
    assert 'currentShockReaderLoadStatus === "error"' in platform
    assert 'currentShockReaderLoadStatus === "unavailable"' in platform
    assert "Retry shock analysis" in platform
    assert "const responseMatchesRequest = payload.run_id === overview.run_id" in platform
    assert "payload.lap_window === expectedLapWindow" in platform
    assert "payload.zone_start_pct === (selection.selectedZoneStartPct ?? null)" in platform

    assert 'loadStatus === "error"' in priority
    assert 'loadStatus === "ready" || (loadStatus === "clear" && eventVisibilityMode !== "actionable")' in priority
    assert "eventsRenderable && valid.length === 0" in priority
    assert "eventsRenderable && valid.map" in priority
    assert 'loadStatus === "unavailable"' in priority
    assert 'loadStatus === "clear"' in priority
    assert "Open Platform" in priority
    assert 'className="rail-empty rail-state"' in priority


def test_platform_failures_cannot_leak_stale_events_to_other_surfaces() -> None:
    app = _read("ui/src/App.tsx")

    for consumer in (
        "useKeyboardShortcuts(currentPlatformEvents",
        "platformEvents={currentPlatformEvents}",
        "<EventTimeline platformEvents={currentPlatformEvents}",
    ):
        assert consumer in app

    assert "platformEvents={platformEvents}" not in app
    assert "trace={currentTrace}" in app
    assert "trace={trace}" not in app


def test_run_context_opens_only_runs_attached_to_the_current_session() -> None:
    app = _read("ui/src/App.tsx")
    context = _read("ui/src/components/RunContextBar.tsx")

    assert "const attachedSessionRunIds = useMemo" in app
    assert "...sessionRuns.map((run) => run.run_id)" in app
    assert "runs.filter((run) => attachedSessionRunIds.has(run.run_id))" in app
    assert "if (currentSession && !attachedSessionRunIds.has(runId))" in app
    assert "That run is not attached to the open session." in app
    assert "void loadSelectedRun(runId);" in app
    assert "runs={sessionRunOptions}" in app
    assert "onSelectRun={openAttachedSessionRun}" in app
    assert "loadSelectedRunSeqRef.current" in app
    assert "sessionSelectionSeqRef.current" in app
    assert "sessionRunsRequestSeqRef.current" in app
    assert "if (!isLatestSelection()) return;" in app

    assert "runs: _runs" not in context
    assert "availableRuns.length > 0" in context
    assert 'value={overview.run_id}' in context
    assert 'value={run.run_id}' in context
    assert "onSelectRun(runId)" in context
    assert 'aria-label="Open a run attached to this session"' in context


def test_failed_session_attachment_never_opens_the_unattached_import() -> None:
    app = _read("ui/src/App.tsx")
    import_flow = app.split("const openImportedRun", 1)[1].split("const handleFileSelected", 1)[0]

    assert "let sessionAttachFailed = false;" in import_flow
    assert "sessionAttachFailed = true;" in import_flow
    assert "updatedSession?.session_id === sessionId && updatedSession.run_ids.includes(runId)" in import_flow
    assert "if (sessionAttachFailed)" in import_flow
    assert "The current session was left unchanged" in import_flow
    assert import_flow.index("if (sessionAttachFailed)") < import_flow.index('setWorkspace("overview", "manual")')


def test_leaving_a_session_prevents_a_late_import_from_reclaiming_the_ui() -> None:
    app = _read("ui/src/App.tsx")

    assert "const importOpenIntentRef = useRef(0);" in app
    assert "const isLatestImportIntent = () => expectedIntent === importOpenIntentRef.current;" in app
    assert "if (!isLatestImportIntent()) return;" in app
    assert "const leaveCurrentSession = useCallback" in app
    leave_block = app.split("const leaveCurrentSession = useCallback", 1)[1].split("}, []);", 1)[0]
    for generation in (
        "sessionSelectionSeqRef.current += 1",
        "sessionRunsRequestSeqRef.current += 1",
        "loadSelectedRunSeqRef.current += 1",
        "importOpenIntentRef.current += 1",
    ):
        assert generation in leave_block
    assert "onClick={leaveCurrentSession}" in app
    assert "openImportedRun(runId, trackMap, renderedImportIntent)" in app


def test_session_change_intent_immediately_fails_closed_before_loading() -> None:
    app = _read("ui/src/App.tsx")

    clear_block = app.split("const clearCurrentRunState = useCallback(() => {", 1)[1].split(
        "}, [selectRun]);",
        1,
    )[0]
    for stale_run_state in (
        "setOverview(null)",
        "setTrace(null)",
        'setTraceLoadState({ requestKey: null, status: "idle", error: null })',
        "setChannels([])",
        "setChannelsHaveFullCatalog(false)",
        "setPlatformEvents([])",
        'setPlatformEventsLoadState({ requestKey: null, status: "idle", error: null })',
        "setTelemetryCapabilities(null)",
        "setActiveControlledWorkflow(null)",
        "setActiveControlledWorkflowRequestKey(null)",
        "setExplicitControlledWorkflowId(null)",
        "setTimelineOwnsKeyboard(false)",
        "setMapOverlayZoomRange(null)",
        "setMapOverlayOpen(false)",
        "selectRun(null)",
    ):
        assert stale_run_state in clear_block

    select_block = app.split("const handleSessionSelected = useCallback", 1)[1].split(
        "// ",
        1,
    )[0]
    assert select_block.index("clearCurrentRunState()") < select_block.index("setSessionId(sid)")
    assert select_block.index("clearCurrentRunState()") < select_block.index("fetchSession(sid)")
    assert "setOverview(null)" not in select_block  # centralized clear cannot be omitted piecemeal
    assert "setCurrentSession(null)" in select_block
    assert "sessionPayloadMatchesRequest(session, sid)" in select_block
    assert "refreshSessionRuns(sid, session.run_ids)" in select_block
    assert "sessionRunListMatchesMembership(scopedRuns, expectedRunIds)" in app
    assert "setLoading(true)" in select_block

    leave_block = app.split("const leaveCurrentSession = useCallback", 1)[1].split(
        "const handleImportClick",
        1,
    )[0]
    assert leave_block.index("clearCurrentRunState()") < leave_block.index("setSessionId(null)")
    assert "setSessionSelectionSource(null)" in leave_block
    assert "if (loading && !overview)" in app

    # Session- and request-key guards keep every shared shell consumer empty
    # while the new session identity is still loading.
    assert "currentSession?.session_id === sessionId" in app
    assert "activeControlledWorkflowRequestKey === controlledWorkflowRequestKey" in app
    assert "platformEventsStateOwnsRequest" in app
    assert "traceStateOwnsRequest" in app
