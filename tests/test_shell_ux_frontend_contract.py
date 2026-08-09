from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _css_block(styles: str, selector: str) -> str:
    start = styles.index(selector)
    return styles[start:styles.index("}", start) + 1]


def test_run_header_is_two_tier_and_keeps_primary_controls_visible() -> None:
    context = _read("ui/src/components/RunContextBar.tsx")
    styles = _read("ui/src/styles.css")

    assert 'className="context-bar context-bar-two-tier"' in context
    assert 'aria-label="Run, lap, and mode controls"' in context
    assert '<span className="context-control-label">Run</span>' in context
    assert '<span className="context-control-label">Lap</span>' in context
    assert "mode-${selection.selectedMode}" in context
    assert "availableRuns.length > 0" in context
    assert "disabled={availableRuns.length === 1}" not in context

    assert "session?.source_file" in context
    assert "Source file: ${fullSourceFilename}" in context
    run_label = context.split("function runOptionLabel", 1)[1].split("function windDirectionDegrees", 1)[0]
    assert "imported_at" not in run_label
    assert "date unknown" not in run_label
    assert "rawSetup.length > 24" in run_label

    shell_styles = styles.split("/* Shell UX: responsive run context", 1)[1]
    assert ".cockpit-shell > .context-bar.context-bar-two-tier" in shell_styles
    assert "grid-template-rows: minmax(30px, auto) minmax(38px, auto)" in shell_styles
    assert "@media (max-width: 1280px)" in shell_styles
    assert ".context-run-control" in shell_styles
    assert ".context-lap-control" in shell_styles

    # The containing row must not clip the absolutely positioned Session details
    # popover; only individual text items may ellipsize at laptop widths.
    header_block = _css_block(shell_styles, ".cockpit-shell > .context-bar.context-bar-two-tier")
    left_block = _css_block(shell_styles, ".cockpit-shell > .context-bar-two-tier .context-bar-left {")
    item_block = _css_block(shell_styles, ".cockpit-shell > .context-bar-two-tier .context-bar-left .context-item")
    assert "position: relative" in header_block
    assert "z-index: 20" in header_block
    assert "overflow: visible" in header_block
    assert "overflow: visible" in left_block
    assert "overflow: hidden" in item_block
    assert "text-overflow: ellipsis" in item_block
    assert ".session-info-anchor" in shell_styles
    assert "className=\"session-info-popover\"" in context


def test_controlled_workflow_shell_uses_exact_scope_and_withholds_ambiguous_catalogs() -> None:
    app = _read("ui/src/App.tsx")
    ribbon = _read("ui/src/components/ControlledTestRibbon.tsx")
    dial_in = _read("ui/src/tabs/DialInTab.tsx")

    effect = app.split("const requestSeq = ++controlledWorkflowRequestSeqRef.current", 1)[1].split(
        "useEffect(() => {\n    let cancelled = false;",
        1,
    )[0]
    assert "setActiveControlledWorkflow(null)" in effect
    assert "requestedWorkflowKey = controlledWorkflowRequestKey" in effect
    assert "setActiveControlledWorkflowRequestKey(requestedWorkflowKey)" in effect
    assert "requestedRunId = overview?.run_id" in effect
    assert "requestedSessionId !== sessionId" in effect
    assert "!explicitScope.has(requestedRunId)" in effect
    assert "currentRefresh !== refreshSeq" in effect
    assert "const isActiveWorkflow" in effect
    assert 'workflow.status !== "scored"' in effect
    assert 'workflow.status !== "cancelled"' in effect
    assert "touchesRuns(uniqueScopedActiveWorkflow, currentRun)" in effect
    assert "racerzlab:controlled-workflow-handoff:${requestedSessionId}" in effect
    assert "uniqueScopedActiveWorkflow?.workflow_id === workflowId" in effect
    assert "touchesRuns(workflow, explicitScope)" in effect
    assert "const scopedActiveWorkflows = workflows.filter" in effect
    assert "if (scopedActiveWorkflows.length > 1)" in effect
    assert "setActiveControlledWorkflowAmbiguous(true)" in effect
    assert "setActiveControlledWorkflow(handedOff ?? uniqueScopedActiveWorkflow)" in effect
    assert "fetchControlledWorkflows(false, {" in effect
    assert 'selection.selectedWorkspace === "dial_in"' not in effect
    assert "setActiveControlledWorkflow(null)" in effect.split("catch", 1)[1]

    assert "currentSession?.session_id === sessionId" in app
    assert "activeControlledWorkflowRequestKey === controlledWorkflowRequestKey" in app
    assert 'currentControlledWorkflow?.packet.decision === "test" &&' in app
    assert '<ControlledTestRibbon' in app
    assert 'setWorkspace("dial_in", "manual")' in app
    ribbon_open = app.split("onOpen={(workflowId) => {", 1)[1].split("}}", 1)[0]
    assert "workflowId !== currentControlledWorkflow.workflow_id" in ribbon_open
    assert "currentSession?.session_id !== sessionId" in ribbon_open
    assert "setExplicitControlledWorkflowId(workflowId)" in ribbon_open
    assert "workflowOpenIntentId={explicitControlledWorkflowId}" in app
    assert "onOpen: (workflowId: string) => void" in ribbon
    assert "onClick={() => onOpen(workflow.workflow_id)}" in ribbon

    exact_branch = dial_in.split("if (workflowOpenIntentId) {", 2)[2].split("const related =", 1)[0]
    assert "item.workflow_id === workflowOpenIntentId" in exact_branch
    assert 'item.status !== "cancelled"' in exact_branch
    assert 'item.packet.decision === "test"' in exact_branch
    assert "touchesRun(item, explicitScope)" in exact_branch
    assert "setWorkflow(explicitlyRequested ?? null)" in exact_branch
    assert "selected controlled test is no longer available" in exact_branch
    assert "return;" in exact_branch

    # Exact workflow selection is a one-navigation intent, not a session pin.
    intent_lifecycle = app.split("const previousWorkspace = previousWorkspaceRef.current", 1)[1].split(
        "useEffect(() => {\n    if (!shortcutsOpen)",
        1,
    )[0]
    assert 'previousWorkspace === "dial_in"' in intent_lifecycle
    assert 'selection.selectedWorkspace !== "dial_in"' in intent_lifecycle
    assert "setExplicitControlledWorkflowId(null)" in intent_lifecycle

    # Disappeared/cancelled exact requests and list failures fail closed visibly;
    # neither may fall through to a newer workflow.
    assert "setWorkflow(null)" in dial_in.split("}).catch(() => {", 1)[1].split("});", 1)[0]
    assert "Controlled-test progress could not be loaded" in dial_in
    assert "workflowError && !workflow && !response" in dial_in
    assert "!response && !error && !workflow && !workflowError" in dial_in
    assert "workflow.packet.decision !== \"test\"" in ribbon
    assert "workflow.stage_run_ids.B != null && workflow.stage_run_ids.A == null" in ribbon
    assert "workflow.stage_run_ids.A2 != null && workflow.stage_run_ids.B == null" in ribbon
    for copy in (
        "Record baseline A",
        "Record changed run B",
        "Restore and record A2",
        "Score the controlled test",
    ):
        assert copy in ribbon
    assert ribbon.count("<button") == 1


def test_race_priority_rail_compacts_only_for_genuinely_clear_state() -> None:
    app = _read("ui/src/App.tsx")

    rail_effect = app.split("const genuinelyClearInRaceMode", 1)[1].split(
        "useEffect(() => {\n    const requestSeq",
        1,
    )[0]
    assert 'selection.selectedMode === "race"' in rail_effect
    assert 'currentPlatformEventsLoadStatus === "clear"' in rail_effect
    assert "setPriorityRailOpen(!genuinelyClearInRaceMode)" in rail_effect
    assert "if (!genuinelyClearInRaceMode) void loadPriorityRail()" in rail_effect
    assert 'currentPlatformEventsLoadStatus !== "clear"' in app
    assert "priorityRailExpanded = priorityRailMustStayOpen || priorityRailOpen" in app
    assert "collapseDisabled={priorityRailMustStayOpen}" in app
    assert "priorityRailIsGenuinelyClear" in app
    assert "Supported platform checks clear; expand Priority Rail" in app
    assert "<CheckCircle2" in app

    priority = _read("ui/src/components/PriorityRail.tsx")
    assert "disabled={collapseDisabled}" in priority
    assert "Priority Rail stays open until evidence is genuinely clear" in priority


def test_loaded_session_demotes_import_to_a_compact_toolbar_drawer() -> None:
    app = _read("ui/src/App.tsx")

    toolbar = app.split('className="workspace-toolbar shell-session-toolbar"', 1)[1].split(
        'id="session-import-drawer"',
        1,
    )[0]
    assert "Sessions" in toolbar
    assert "Add run" in toolbar
    assert "aria-expanded={sessionToolsOpen}" in toolbar
    assert "<ImportPanel" not in toolbar
    assert 'className="shell-import-drawer"' in app
    assert "sessionToolsOpen &&" in app
    assert "setSessionToolsOpen(false)" in app

    empty_state = app.split("if (!overview)", 1)[1].split('<div className="cockpit-shell">', 1)[0]
    assert "<ImportPanel" in empty_state


def test_timeline_defaults_to_contextual_compact_mode_without_losing_controls() -> None:
    app = _read("ui/src/App.tsx")
    timeline = _read("ui/src/components/EventTimeline.tsx")
    shortcuts = _read("ui/src/hooks/useKeyboardShortcuts.ts")

    assert "workspace={selection.selectedWorkspace}" in app
    assert "TRACE_HEAVY_WORKSPACES" in timeline
    for workspace in ("platform_trace", "speed_delta", "drag_scrub"):
        assert f'"{workspace}"' in timeline
    assert "setExpanded(TRACE_HEAVY_WORKSPACES.has(workspace))" in timeline
    assert 'expanded ? " expanded" : " compact"' in timeline
    assert 'aria-expanded={expanded}' in timeline
    assert 'aria-controls="event-timeline-details"' in timeline
    assert 'hidden={!expanded}' in timeline

    # Existing keyboard browsing and evidence-commit contracts remain present.
    for key in ('e.key === " "', 'e.key === "ArrowLeft"', 'e.key === "ArrowRight"', 'e.key === "Enter"', 'e.key === "Escape"'):
        assert key in timeline
    assert "focusEvidence(buildTimelineEvidence(event))" in timeline

    scope = timeline.split("const eventScopeKey", 1)[1].split("const ownsKeyboard", 1)[0]
    for identity in (
        "selection.selectedRunId",
        "selection.selectedLap",
        "eventVisibilityMode",
        "visibleEvents.map",
        "event.event_id",
        "event.sample_index",
        "event.lap_dist_ft",
        "event.event_type",
    ):
        assert identity in scope
    reset = timeline.split("if (playbackRef.current != null)", 1)[1].split(
        "}, [eventScopeKey, setPlaybackActive, setPreviewHover]);",
        1,
    )[0]
    for reset_action in (
        "cancelAnimationFrame(playbackRef.current)",
        "playbackRef.current = null",
        "indexRef.current = 0",
        "setPlaying(false)",
        "setBrowseIndex(null)",
        "setHoveredIndex(null)",
        "setPreviewHover(null)",
        "setPlaybackActive(false)",
    ):
        assert reset_action in reset

    keyboard = timeline.split("const handler = (e: KeyboardEvent) => {", 1)[1].split(
        'window.addEventListener("keydown", handler)',
        1,
    )[0]
    assert "!expanded || !timelineRef.current?.contains(document.activeElement)" in keyboard
    assert "document.querySelector('[role=\"dialog\"][aria-modal=\"true\"]')" in keyboard
    assert 'e.target.closest("button")' in keyboard
    assert "onKeyboardOwnershipChange?.(ownsKeyboard)" in timeline
    assert 'data-event-timeline-keyboard-owner={ownsKeyboard ? "true" : "false"}' in timeline
    assert "tabIndex={expanded ? 0 : -1}" in timeline
    assert "onFocusCapture={() => setFocusWithin(true)}" in timeline
    assert "onKeyboardOwnershipChange={setTimelineOwnsKeyboard}" in app

    modal_guard = shortcuts.split("if (options?.shortcutsOpen) {", 1)[1].split(
        "if (timelineOwnsEventKey",
        1,
    )[0]
    assert 'key === "Escape"' in modal_guard
    assert "options.onHideShortcuts?.()" in modal_guard
    assert modal_guard.rstrip().endswith("}")
    assert "eventTimelineOwnsKeyboard?: boolean" in shortcuts
    assert "timelineTargetOwnsKeyboard" in shortcuts
    assert '[data-event-timeline-keyboard-owner="true"]' in shortcuts
    assert "requestAnimationFrame(() => shortcutModalCloseRef.current?.focus())" in app
    assert 'if (event.key !== "Tab"' in app


def test_premium_shell_preserves_fast_scan_keyboard_and_reduced_motion_contracts() -> None:
    app = _read("ui/src/App.tsx")
    context = _read("ui/src/components/RunContextBar.tsx")
    priority = _read("ui/src/components/PriorityRail.tsx")
    styles = _read("ui/src/styles.css")

    assert 'className="cockpit-shell" data-mode={selection.selectedMode}' in app
    assert 'className="shell-skip-link" href="#primary-workspace"' in app
    assert 'id="primary-workspace" className="cockpit-workspace" tabIndex={-1}' in app
    assert 'className="nav-rail-heading"' in app
    assert 'className="nav-rail-copy"' in app
    assert 'className="shell-session-identity"' in app
    assert 'className="shell-workspace-heading"' in app
    assert '<h1 className="shell-workspace-name">{currentWorkspaceLabel}</h1>' in app
    assert 'aria-label={`${currentWorkspaceLabel} status:' in app
    assert 'className="workspace-placeholder shell-workspace-loading"' in app
    assert 'aria-busy="true"' in app
    assert 'function ShellLoadingState' in app

    assert 'aria-label="Current telemetry context"' in context
    assert 'className="context-brand-lockup"' in context
    assert 'className="context-item-copy"' in context
    assert 'className="context-control-position"' in context
    assert 'role="region"' in context

    assert 'className="rail-heading-copy"' in priority
    assert 'className="rail-empty rail-state"' in priority
    assert 'aria-keyshortcuts="Shift+Enter"' in priority
    assert 'aria-pressed={selection.selectedEventId === event.event_id}' in priority
    assert 'aria-expanded={showInvalid}' in priority
    assert 'aria-controls="low-confidence-priority-events"' in priority

    for selector in (
        ".shell-skip-link:focus",
        ".startup-value-grid",
        ".import-progress-track",
        ".rail-loading-bars",
        ".shell-workspace-loading-bars",
        ".nav-rail-copy",
    ):
        assert selector in styles
    assert "@media (max-width: 1280px)" in styles
    assert "@media (max-width: 1060px)" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
    premium_styles = styles.split("/* Premium shell and intake hierarchy */", 1)[1]
    reduced_motion = premium_styles.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "animation: none !important" in reduced_motion
    assert "transition: none !important" in reduced_motion


def test_priority_rail_never_relabels_old_local_events_under_a_new_scope() -> None:
    priority = _read("ui/src/components/PriorityRail.tsx")

    assert 'const internalRequestKey = `${runId}:${selectedLap ?? "all"}`;' in priority
    assert "externalEvents !== undefined" in priority
    assert "internalEvents.requestKey === internalRequestKey ? internalEvents.events : []" in priority
    assert "setInternalEvents({ requestKey: null, events: [] });" in priority
