from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_chart_annotation_source_filters_events_by_display_scope() -> None:
    source = _read("ui/src/utils/platformChartAnnotations.ts")

    assert "filterPlatformEvents(platformEvents, mode)" in source
    assert "buildPlatformChartAnnotations" in _read("ui/src/tabs/PlatformTab.tsx")


def test_internal_events_do_not_render_chart_markers_in_actionable_mode() -> None:
    visibility = _read("ui/src/utils/platformEventVisibility.ts")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'return (scope === "actionable" || scope === "watch") && Boolean(event.is_visible_default);' in visibility
    assert "const visiblePlatformEvents = filterPlatformEvents(platformEvents, mode);" in chart
    assert "visiblePlatformEvents" in chart


def test_highest_shock_activity_does_not_render_chart_marker_by_default() -> None:
    backend_test = _read("tests/test_platform_events.py")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'HIGHEST_SHOCK_ACTIVITY' in backend_test
    assert 'assert event.display_scope == "internal"' in backend_test
    assert 'assert event.is_visible_default is False' in backend_test
    assert "filterPlatformEvents(platformEvents, mode)" in chart


def test_highest_platform_compression_does_not_render_chart_marker_by_default() -> None:
    backend_test = _read("tests/test_platform_events.py")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'HIGHEST_PLATFORM_COMPRESSION' in backend_test
    assert 'test_highest_platform_compression_is_internal_without_contact_gate' in backend_test
    assert "filterPlatformEvents(platformEvents, mode)" in chart


def test_highest_rake_does_not_render_chart_marker_by_default() -> None:
    backend_test = _read("tests/test_platform_events.py")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'HIGHEST_RAKE' in backend_test
    assert 'test_highest_center_rake_is_internal_without_driver_facing_impact' in backend_test
    assert "filterPlatformEvents(platformEvents, mode)" in chart


def test_true_contact_bottoming_event_still_renders_in_actionable_mode() -> None:
    backend_test = _read("tests/test_platform_events.py")
    visibility = _read("ui/src/utils/platformEventVisibility.ts")

    assert "test_true_contact_events_remain_visible" in backend_test
    assert 'assert _event(events, "WHOLE_CAR_BOTTOMING_RISK").display_scope == "actionable"' in backend_test
    assert 'scope === "actionable" || scope === "watch"' in visibility


def test_proxy_internal_mode_renders_internal_events_muted() -> None:
    visibility = _read("ui/src/utils/platformEventVisibility.ts")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'if (mode === "proxy") return scope === "actionable" || scope === "watch" || scope === "internal";' in visibility
    assert "isMutedPlatformEvent(event, mode)" in chart
    assert "opacity: event.muted ? 0.42 : 1" in chart
    assert "opacity: event.muted ? 0.04 : 0.08" in chart


def test_all_mode_renders_debug_events_if_present() -> None:
    visibility = _read("ui/src/utils/platformEventVisibility.ts")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'if (mode === "all") return true;' in visibility
    assert "filterPlatformEvents(platformEvents, mode)" in chart


def test_hidden_events_do_not_create_raw_event_label_spam() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert 'formatter: "event"' not in platform
    assert "showLineLabels: false" in chart
    assert "label: { show: eventAnnotations.showLineLabels" in platform


def test_ride_height_panels_receive_increased_density_aware_heights() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'heightDetailed: 154, heightCompact: 108, yAxisUnit: "in"' in platform
    assert 'heightDetailed: 138, heightCompact: 104, yAxisUnit: "in"' in platform
    assert 'heightDetailed: 118, heightCompact: 96, yAxisUnit: "in"' in platform
    assert 'type ChartDensity = "detailed" | "compact"' in platform
    assert 'const [chartDensity, setChartDensity] = useState<ChartDensity>("detailed")' in platform
    assert "buildPanelLayout(rows, preset, chartDensity, fallbackRowHeight(preset), 54)" in platform
    assert "layoutTotalHeight(panelLayout, 42)" in platform


def test_chart_uses_separated_grid_panels_without_wheel_scroll_trap() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "rowGap(preset, density)" in platform
    assert 'return density === "compact" ? 12 : 18' in platform
    assert 'stroke: "rgba(15,23,42,0.95)"' in platform
    wrapper_block = styles.split(".trace-panel-wrapper {", 1)[1].split("}", 1)[0]
    assert "overflow: visible" in wrapper_block
    assert "max-height" not in wrapper_block
    assert "overflow: auto" not in wrapper_block


def test_rake_panels_include_zero_line() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'zeroLine: true' in platform
    assert 'name: "Zero"' in platform
    assert "yAxis: 0" in platform
    assert 'color: "rgba(203,213,225,0.58)"' in platform


def test_only_bottom_x_axis_shows_full_distance_labels() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "show: index === rows.length - 1" in platform
    assert "hideOverlap: true" in platform
    assert "formatter: (value: number) => `${Math.round(value).toLocaleString()} ft`" in platform
    assert "axisTick: { show: index === rows.length - 1 }" in platform


def test_cursor_readout_includes_ride_height_rake_and_event_context() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "<div><dt>CFS</dt>" in platform
    assert "<div><dt>LF/RF</dt>" in platform
    assert "<div><dt>LR/RR</dt>" in platform
    assert "<div><dt>Front/Rear Avg</dt>" in platform
    assert "<div><dt>Center Rake FS</dt>" in platform
    assert "<div><dt>Side Rake</dt>" in platform
    assert "<div><dt>Event</dt><dd>{selectedPlatformEvent.title}</dd></div>" in platform
    assert "<div><dt>Hidden</dt><dd>{hiddenPlatformEventCount} internal</dd></div>" in platform


def test_missing_channel_does_not_render_as_zero() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "channelHasNumericData" in platform
    assert "!channelHasNumericData(trace, channel.name)" in platform
    assert '`${channel.label} unavailable`' in platform
    assert "trace-missing-note" in platform
    assert "connectNulls: false" in platform


def test_selected_event_or_zone_draws_subtle_cross_panel_context() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "selectedBandAreaData" in platform
    assert "selectedOverlayEvent" in platform
    assert "selection.selectedZoneStartPct" in platform
    assert "selection.selectedZoneEndPct" in platform
    assert 'color: "#38bdf8", opacity: 0.055' in platform
    assert "channelIndex === 0 ? selectedBandAreaData : []" in platform


def test_ride_height_series_do_not_use_hover_focus_or_blur_emphasis() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'emphasis: { disabled: true }' in platform
    assert 'focus: "self"' not in platform
    assert 'focus: "series"' not in platform
    assert "blur: { lineStyle" not in platform
    assert "legendHoverLink: false" in platform
    assert 'inactiveColor: "#475569"' in platform
    assert "itemGap: 8" in platform


def test_chart_config_includes_x_axis_data_zoom_across_stacked_grids() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'type: "slider", xAxisIndex: rows.map((_, i) => i)' in platform
    assert "xAxisIndex: rows.map((_, i) => i)" in platform
    assert 'yAxisIndex: "none"' in platform
    assert 'filterMode: "none"' in platform
    assert 'type: "inside"' not in platform
    assert "zoomOnMouseWheel" not in platform
    assert "moveOnMouseWheel" not in platform
    assert "dataZoomIndex: 0" in platform


def test_drag_zoom_and_reset_zoom_controls_exist() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "dragZoomRef" in platform
    assert "trace-drag-zoom-band" in platform
    assert "Reset ride-height zoom" in platform
    assert "trace-reset-zoom" in platform
    assert "trace-zoom-status" in platform
    assert "Zoomed: ${start}-${end} ft" in platform
    assert ".trace-drag-zoom-band" in styles


def test_reset_zoom_does_not_clear_selected_event_or_session_state() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    reset_body = platform.split("const resetRideHeightZoom = useCallback(() => {", 1)[1].split("}, []);", 1)[0]

    assert 'chartRef.current?.dispatchAction({ type: "dataZoom", start: 0, end: 100 });' in reset_body
    assert "setSelectedPlatformEvent" not in reset_body
    assert "focusEvidence" not in reset_body
    assert "setWorkspace" not in reset_body


def test_escape_unlock_restores_live_cursor_hover_readout() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "lastPointerOffsetRef" in platform
    assert "restoreHoverAtPointerRef" in platform
    assert "cancelDragZoomRef.current()" in platform
    assert "clickedSampleIndexRef.current = null" in platform
    assert "hoverSampleIndexRef.current = index" in platform
    assert "setHoverSampleIndex(index)" in platform
    assert "const restoredHover = restoreHoverAtPointerRef.current()" in platform
    assert "if (!restoredHover) hideCursorLine()" in platform


def test_chart_annotation_data_comes_only_from_visible_events() -> None:
    chart = _read("ui/src/utils/platformChartAnnotations.ts")

    assert "const visiblePlatformEvents = filterPlatformEvents(platformEvents, mode);" in chart
    assert "visiblePlatformEvents\n    .filter((event) => event.lap_dist_ft != null)" in chart
    assert "platformEvents.length > 0\n    ? []" in chart
    assert "showLineLabels: false" in chart


def test_compare_basket_stale_items_are_marked_not_silently_removed() -> None:
    basket = _read("ui/src/store/CompareBasketContext.tsx")
    component = _read("ui/src/components/CompareBasket.tsx")
    app = _read("ui/src/App.tsx")

    assert "validateBasketStateAgainstRuns" in basket
    assert "stale_reason" in basket
    assert 'return { status: "not_valid", reason: "Missing one or more runs." };' in basket
    assert "Run unavailable" in component
    assert "This basket item points to a run that is not loaded in the current session." in component
    assert "disabled={hasStaleItems}" in component
    assert "validateAvailableRuns(runIds" in app


def test_selection_state_validates_run_ids_after_session_change() -> None:
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")
    app = _read("ui/src/App.tsx")

    assert '"VALIDATE_RUN_IDS"' in selection
    assert "validateSelectionRunIds" in selection
    assert "selectedEventId" in selection
    assert "validateSelectionRunIds(runIds)" in app


def test_platform_event_summary_strip_renders_visible_and_hidden_counts() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "platform-event-summary-strip" in platform
    assert "visiblePlatformEvents.length" in platform
    assert "hiddenPlatformEventCount" in platform
    assert "Top issue:" in platform
    assert "shown" in platform
    assert "hidden" in platform


def test_actionable_mode_hides_internal_events_but_counts_them_as_hidden() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    visibility = _read("ui/src/utils/platformEventVisibility.ts")

    assert 'return (scope === "actionable" || scope === "watch") && Boolean(event.is_visible_default);' in visibility
    assert "Math.max(0, platformEvents.length - visiblePlatformEvents.length)" in platform


def test_no_visible_events_state_displays_cleanly() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "No actionable platform events shown" in platform
    assert "internal evidence item" in platform
    assert "No platform diagnostic events for this lap" in platform


def test_hidden_selected_event_fallback_appears_when_selected_event_is_filtered_out() -> None:
    inspector = _read("ui/src/components/EvidenceInspector.tsx")

    assert "hiddenSelectedEvent" in inspector
    assert "Selected event is hidden by current filter." in inspector
    assert "HiddenSelectedEventInspector" in inspector


def test_hidden_selected_event_fallback_can_show_proxy_internal_or_clear_selection() -> None:
    inspector = _read("ui/src/components/EvidenceInspector.tsx")
    app = _read("ui/src/App.tsx")

    assert 'onEventVisibilityModeChange("proxy")' in inspector
    assert 'selectEvent(null, "manual")' in inspector
    assert "Show Proxy/Internal" in inspector
    assert "Clear Selection" in inspector
    assert "onEventVisibilityModeChange={setPlatformEventVisibilityMode}" in app


def test_platform_event_card_includes_supported_open_setup_and_stage_test_actions() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "handleOpenSetupFromPlatformEvent" in platform
    assert "handleStageTestFromPlatformEvent" in platform
    assert "Open Setup" in platform
    assert "Stage Test" in platform
    assert '"setup_impact"' in platform
    assert '"notebook"' in platform


def test_event_timeline_prefers_zone_labels_over_raw_percentages_when_available() -> None:
    timeline = _read("ui/src/components/EventTimeline.tsx")

    assert "timelineEventLocationLabel" in timeline
    assert "selection.selectedZoneLabel" in timeline
    assert "lapPctInRange" in timeline
    assert "percent lap" in timeline
    assert "aria-label={`${event.title}, ${locationLabel}" in timeline


def test_focus_visible_css_coverage_includes_platform_controls() -> None:
    styles = _read("ui/src/styles.css")

    assert ".secondary-button:focus-visible" in styles
    assert ".platform-event-button:focus-visible" in styles
    assert ".risk-strip-segment:focus-visible" in styles
    assert ".platform-event-filter select:focus-visible" in styles
    assert ".playback-btn:focus-visible" in styles
    assert ".playback-speed-btn:focus-visible" in styles
