from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_escape_reducer_rebuilds_from_scope_and_cannot_retain_hostile_focus() -> None:
    """An old event payload cannot survive Escape through an object spread."""
    source = _read("ui/src/store/TelemetrySelectionContext.tsx")
    clear_branch = source.split('case "CLEAR_EVIDENCE_FOCUS":', 1)[1].split(
        'case "RESET_SELECTION":',
        1,
    )[0]

    assert "...state" not in clear_branch
    assert "...DEFAULT_SELECTION" in clear_branch

    for durable_scope in (
        "selectedRunId: state.selectedRunId",
        "selectedCompareRunId: state.selectedCompareRunId ?? null",
        "selectedLap: state.selectedLap ?? null",
        "selectedMode: state.selectedMode",
        "selectedWorkspace: state.selectedWorkspace",
    ):
        assert durable_scope in clear_branch

    # Every prior cursor/location/event/zone/channel payload is overwritten.
    for stale_field in (
        "selectedEventId",
        "selectedSampleIndex",
        "selectedLapDistFt",
        "selectedLapDistM",
        "selectedLapPct",
        "selectedChannel",
        "selectedSetupKey",
        "selectedZoneId",
        "selectedZoneLabel",
        "selectedZoneStartPct",
        "selectedZoneEndPct",
        "selectedTrustTier",
        "hoverLapPct",
        "hoverSampleIndex",
    ):
        assert f"{stale_field}: null" in clear_branch

    assert 'selectedLockState: "none"' in clear_branch
    assert "playbackActive: false" in clear_branch
    assert 'selectionSource: "manual"' in clear_branch

    # A zone scope is not durable once its zone payload is gone. Only an exact
    # lap window, a current lap, or the current run can determine the new basis.
    assert 'state.selectedLapScope === "lap_window"' in clear_branch
    assert 'state.selectedLap != null' in clear_branch
    assert 'state.selectedRunId != null' in clear_branch
    assert 'selectedLapScope === "single_lap"' in clear_branch
    assert 'selectedLapScope === "run"' in clear_branch
    assert 'selectedValueBasis' in clear_branch
    assert '"selected_window"' in clear_branch
    assert '"full_lap"' in clear_branch
    assert '"run_level"' in clear_branch
    assert '"unavailable"' in clear_branch


def test_escape_uses_atomic_clear_and_resets_external_cursor_first() -> None:
    store = _read("ui/src/store/TelemetrySelectionContext.tsx")
    shortcuts = _read("ui/src/hooks/useKeyboardShortcuts.ts")

    clear_callback = store.split("const clearEvidenceFocus = useCallback", 1)[1].split(
        "const validateSelectionRunIds",
        1,
    )[0]
    assert clear_callback.index("resetCursor()") < clear_callback.index(
        'dispatch({ type: "CLEAR_EVIDENCE_FOCUS" })'
    )

    escape_branch = shortcuts.split('case "Escape":', 1)[1].split('case "[":', 1)[0]
    assert "e.preventDefault()" in escape_branch
    assert "clearEvidenceFocus()" in escape_branch
    assert "focusEvidence(" not in escape_branch


def test_escape_respects_typing_modal_and_timeline_keyboard_owners() -> None:
    shortcuts = _read("ui/src/hooks/useKeyboardShortcuts.ts")
    handler = shortcuts.split("function handler(e: KeyboardEvent)", 1)[1].split(
        'window.addEventListener("keydown", handler)',
        1,
    )[0]
    clear_position = handler.index("clearEvidenceFocus()")

    for editable_guard in (
        'tag === "input"',
        'tag === "textarea"',
        'tag === "select"',
        "isContentEditable",
    ):
        assert handler.index(editable_guard) < clear_position
    assert handler.index("e.ctrlKey || e.metaKey") < clear_position
    assert handler.index("if (options?.shortcutsOpen)") < clear_position
    assert "options.onHideShortcuts?.()" in handler
    assert handler.index("if (timelineOwnsEventKey") < clear_position
    assert '[data-event-timeline-keyboard-owner="true"]' in handler

    timeline = _read("ui/src/components/EventTimeline.tsx")
    timeline_handler = timeline.split("const handler = (e: KeyboardEvent) => {", 1)[1].split(
        'window.addEventListener("keydown", handler)',
        1,
    )[0]
    assert "document.querySelector('[role=\"dialog\"][aria-modal=\"true\"]')" in timeline_handler
    assert "HTMLInputElement" in timeline_handler
    assert "HTMLTextAreaElement" in timeline_handler
    assert 'select, [contenteditable=\'true\']' in timeline_handler
    assert 'if (e.key === "Escape")' in timeline_handler
    assert "setHover(null, null)" in timeline_handler


def test_platform_escape_clears_local_lock_without_reintroducing_focus() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    escape_handler = platform.split("const onKey = (e: KeyboardEvent) => {", 1)[1].split(
        'window.addEventListener("keydown", onKey)',
        1,
    )[0]
    clear_position = escape_handler.index("cancelDragZoomRef.current()")

    for ownership_guard in (
        'tag === "input"',
        'tag === "textarea"',
        'tag === "select"',
        "isContentEditable",
        "e.ctrlKey || e.metaKey",
        '[role="dialog"][aria-modal="true"]',
        '[data-event-timeline-keyboard-owner="true"]',
    ):
        assert escape_handler.index(ownership_guard) < clear_position

    assert "focusEvidence(" not in escape_handler
    assert "e.stopPropagation()" not in escape_handler
    assert "cancelAnimationFrame(hoverRafRef.current)" in escape_handler
    for stale_local_value in (
        "clickedSampleIndexRef.current = null",
        "hoverSampleIndexRef.current = null",
        "clickedCursorDistanceFtRef.current = null",
        "hoverCursorDistanceFtRef.current = null",
        "pendingHoverSampleIndexRef.current = null",
        "pendingHoverCursorDistanceFtRef.current = null",
        "setSelectedPlatformEvent(null)",
    ):
        assert stale_local_value in escape_handler
