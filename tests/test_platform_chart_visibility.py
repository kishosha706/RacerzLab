from __future__ import annotations

from pathlib import Path

from racelab_engine.services.import_service import build_trace_payload, write_telemetry_cache


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
    assert "isClearPlatformDiagnostic" in visibility
    assert "&& !isClearPlatformDiagnostic(event)" in visibility
    assert "isMutedPlatformEvent(event, mode)" in chart
    assert "opacity: event.muted ? 0.42 : 1" in chart
    assert "opacity: event.muted ? 0.04 : 0.08" in chart


def test_all_mode_keeps_internal_events_available_when_requested() -> None:
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
    assert "formatter: (value: number) => formatDistanceFt(value, decimalDistanceLabels ? 1 : 0)" in platform
    assert "labelFormatter: (value: number) => formatDistanceFt(value, decimalDistanceLabels ? 1 : 0)" in platform
    assert "formatter: (params: { value?: unknown })" in platform
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


def test_balance_default_removes_duplicate_ride_height_engineering_cards() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'case "balance": return null;' in platform
    assert 'workbenchView !== "balance" && renderEngineeringPanel()' in platform
    assert 'workbenchView !== "balance" && (' in platform
    assert 'EngineeringMetricCard title="CFS Ride Height"' not in platform
    assert 'EngineeringMetricCard title="Front Ride Heights"' not in platform
    assert 'EngineeringMetricCard title="Rear Ride Heights"' not in platform
    assert 'EngineeringMetricCard title="Front / Rear Avg RH"' not in platform
    assert 'EngineeringMetricCard title="Center Rake"' not in platform
    assert 'EngineeringMetricCard title="Side Rake"' not in platform
    assert 'EngineeringMetricCard title="Roll / Pitch"' not in platform


def test_platform_tabs_do_not_render_global_top_metric_card_strip() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "platform-summary-bar" not in platform
    assert "platform-summary-chip" not in platform
    assert "platformGeometrySummaryItems" not in platform
    assert "diagnosticSummaryItems" not in platform
    assert "summaryItems" not in platform
    assert ".platform-summary-bar" not in styles
    assert ".platform-summary-chip" not in styles


def test_balance_panel_readouts_replace_global_readout_strip() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "balancePanelReadouts" in platform
    assert "hasExplicitReadoutContext" in platform
    assert "balance-panel-readout-layer" in platform
    assert "balance-panel-cursor-readout" in platform
    assert "balance-panel-stat-readout" in platform
    assert "balanceChartReadout" not in platform
    assert ".balance-panel-readout-layer" in styles
    assert ".balance-chart-readout" not in styles
    assert "Hover or scrub the chart to inspect ride heights." not in platform


def test_balance_panel_cursor_readouts_include_required_labels_and_colors() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'return "CFSRideHeight [in]";' in platform
    assert 'return "LF Ride Height [in]";' in platform
    assert 'return "RF Ride Height [in]";' in platform
    assert 'return "LR Ride Height [in]";' in platform
    assert 'return "RR Ride Height [in]";' in platform
    assert 'return "Front Avg";' in platform
    assert 'return "Rear Avg";' in platform
    assert 'return "Center Rake";' in platform
    assert 'return "Side Rake";' in platform
    assert 'style={{ color: channel.color }}' in platform
    assert "channel.readoutLabel" in platform
    assert "fmtReadout(channel.cursorValue" in platform


def test_balance_panel_readout_prefers_hover_and_shows_no_cursor_helper() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "const balanceReadoutIndex = playbackIndex ?? transientHoverIndex ?? lockedIndex ?? selectedContextIndex ?? cursorIndex;" in platform
    assert "const balanceReadoutSource = playbackIndex != null" in platform
    assert "balanceReadoutLocationSummary" in platform
    assert "formatDistanceFt(balanceReadoutDistance)" in platform
    assert "panelIndex === 0 && lockedReadoutSummary" in platform
    assert '<span className="balance-selected-context">{lockedReadoutSummary}</span>' in platform
    assert "Cursor: hover or scrub" in platform
    assert platform.index('className="trace-panel" ref={chartNode}') < platform.index('className="balance-panel-readout-layer"')


def test_balance_panel_stats_include_accessible_motec_icons() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert 'title="Lowest visible value" aria-label="Lowest visible value">▼' in platform
    assert 'title="Highest visible value" aria-label="Highest visible value">▲' in platform
    assert 'title="Average visible value" aria-label="Average visible value">◆' in platform
    assert "balance-stat-low" in platform
    assert "balance-stat-high" in platform
    assert "balance-stat-avg" in platform
    assert ".balance-stat-low" in styles
    assert ".balance-stat-high" in styles
    assert ".balance-stat-avg" in styles


def test_balance_visible_stats_recalculate_from_zoom_range() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "visibleZoomRange" in platform
    assert "setVisibleZoomRange(nextRange)" in platform
    assert "setVisibleZoomRange(null)" in platform
    assert "visibleRangeForStats" in platform
    assert "x >= rangeStart" in platform
    assert "x <= rangeEnd" in platform
    assert "Math.min(...visibleValues)" in platform
    assert "Math.max(...visibleValues)" in platform
    assert "visibleValues.reduce((sum, value) => sum + value, 0) / visibleValues.length" in platform


def test_balance_visible_stats_use_raw_samples_inside_zoom_range() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout_body = platform.split("const balancePanelReadouts = useMemo(() => {", 1)[1].split("  }, [", 1)[0]

    assert "rawSeriesSamples(trace, channel.name)" in readout_body
    assert "Visible Balance stats are calculated from raw telemetry samples inside the current zoom window." in readout_body
    assert "x >= rangeStart" in readout_body
    assert "x <= rangeEnd" in readout_body
    stats_body = readout_body.split("const visibleValues: number[] = [];", 1)[1].split("const low =", 1)[0]
    assert "lineCursorDisplayValue" not in stats_body


def test_balance_cursor_readout_interpolates_display_value_only() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    helper_body = platform.split("function lineCursorDisplayValue(", 1)[1].split("\nfunction channelHasNumericData", 1)[0]
    readout_body = platform.split("const balancePanelReadouts = useMemo(() => {", 1)[1].split("  }, [", 1)[0]

    assert "function lineCursorDisplayValue" in platform
    assert "const ratio = (cursorDistanceFt - beforeX) / (afterX - beforeX);" in helper_body
    assert "return beforeY + ratio * (afterY - beforeY);" in helper_body
    assert "const fallback = numericSeriesValue(series, measuredSampleIndex);" in helper_body
    assert "Cursor values are display-only interpolation along the rendered line; stats below remain raw measured samples." in readout_body
    assert "lineCursorDisplayValue(trace, xs, channel.name, balanceCursorDistanceFt, balanceReadoutIndex)" in readout_body
    assert "cursorValue: typeof cursorDisplayValue === \"number\" && Number.isFinite(cursorDisplayValue) ? cursorDisplayValue : null" in readout_body


def test_balance_cursor_readout_uses_exact_hover_and_locked_distance() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "const balanceCursorDistanceFt = playbackIndex != null" in platform
    assert "hoverCursorDistanceFt ?? xs[transientHoverIndex] ?? null" in platform
    assert "clickedCursorDistanceFt ?? xs[lockedIndex] ?? null" in platform
    assert "const balanceReadoutDistance = balanceCursorDistanceFt;" in platform
    assert "positionCursorLineForIndex(selectedIndex, readoutSource === \"Locked\", balanceCursorDistanceFt)" in platform
    assert "setClickedCursorDistanceFt(cursorDistanceFt ?? xs[index] ?? null)" in platform
    assert "commitHoverSampleRef.current(index, cursorDistanceFt)" in platform
    assert "const updateCursorRef = useRef<(index: number | null, eventId?: string | null, cursorDistanceFt?: number | null) => void>" in platform


def test_balance_map_overlay_receives_precise_cursor_distance() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    map_body = platform.split("const handleOpenMapFromCursor = useCallback(() => {", 1)[1].split("  const handleOpenMapFromPlatformEvent", 1)[0]

    assert 'workbenchView === "balance" && balanceCursorDistanceFt != null' in map_body
    assert "const mapCursorDistanceFt" in map_body
    assert "mapCursorDistanceFt," in map_body


def test_balance_zoom_fetches_debounced_cached_raw_trace_windows() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    client = _read("ui/src/api/client.ts")
    route = _read("api/routes_runs.py")

    assert 'import { fetchPlatformEvents, fetchShockReader, fetchTrace } from "../api/client";' in platform
    assert 'import { TRACE_WORKBENCH_CHANNELS } from "../constants/workbenchChannels";' in platform
    assert "const [detailTrace, setDetailTrace] = useState<TraceResponse | null>(null)" in platform
    assert "const detailTraceCacheRef = useRef<Map<string, TraceResponse>>(new Map())" in platform
    assert "const detailTraceDebounceRef = useRef<number | null>(null)" in platform
    assert "window.setTimeout(() => {" in platform
    assert 'resolution: "raw"' in platform
    assert "downsample: 1" in platform
    assert "startFt: rawRange.start" in platform
    assert "endFt: rawRange.end" in platform
    assert "const trace = detailTraceActive ? detailTrace : overviewTrace;" in platform
    assert "rawTraceStatus(payload)" in platform
    assert "Loading raw zoom data..." in platform
    assert 'params.set("resolution", options.resolution)' in client
    assert 'params.set("start_ft", String(options.startFt))' in client
    assert 'params.set("end_ft", String(options.endFt))' in client
    assert 'effective_downsample = "1" if (resolution or "").lower() == "raw" else downsample' in route


def test_trace_payload_window_returns_raw_samples_without_bucket_stepping(tmp_path: Path) -> None:
    rows = [
        {
            "sample_index": index,
            "lap": 1,
            "lap_dist_ft": 6.14 if index in (6, 7) else 8.24 if index == 8 else 8.29 if index == 9 else float(index),
            "lap_dist_pct": index / 19,
            "lap_dist_pct_100": (index / 19) * 100,
            "session_time": index / 60,
            "cfs_ride_height_in": 2.0 + index * 0.01,
            "speed_mph": 150.0 + index,
        }
        for index in range(20)
    ]
    write_telemetry_cache("raw-window-run", rows, data_dir=tmp_path)

    payload = build_trace_payload(
        "raw-window-run",
        lap=1,
        channels=["cfs_ride_height_in", "speed_mph"],
        x_axis="lap_dist_ft",
        downsample=1,
        data_dir=tmp_path,
        start_ft=5.5,
        end_ft=8.5,
        raw_resolution=True,
    )

    assert payload["downsample"] == 1
    assert payload["sample_count"] == 4
    assert payload["x"] == [6.14, 6.14, 8.24, 8.29]
    assert payload["x_by_name"]["lap_dist_ft"] == [6.14, 6.14, 8.24, 8.29]
    assert payload["x_by_name"]["sample_index"] == [6, 7, 8, 9]
    assert payload["x_by_name"]["session_time"] == [0.1, 7 / 60, 8 / 60, 0.15]
    assert payload["channels"]["cfs_ride_height_in"]["values"] == [2.06, 2.07, 2.08, 2.09]
    assert payload["channels"]["speed_mph"]["values"] == [156.0, 157.0, 158.0, 159.0]
    assert payload["trace_meta"]["raw_resolution"] is True
    assert payload["trace_meta"]["downsample_applied"] is False
    assert payload["trace_meta"]["raw_source_row_count"] == 4
    assert payload["trace_meta"]["returned_row_count"] == 4
    assert payload["trace_meta"]["distance_duplicate_count"] == 1
    assert payload["trace_meta"]["distance_rounded_or_deduped"] is False
    assert abs(payload["trace_meta"]["approx_hz"] - 60) < 0.001


def test_balance_detail_trace_does_not_reset_hover_when_raw_window_loads() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "useEffect(() => {\n    setHoverSampleIndex(null);\n  }, [overviewTrace.run_id, overviewTrace.lap]);" in platform
    assert "setHoverSampleIndex(null);\n  }, [trace]);" not in platform


def test_balance_cursor_lookup_uses_nearest_raw_sample_by_distance() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "function nearestRawSampleIndexByFt" in platform
    assert "nearestRawSampleIndexByFt(latestXsRef.current, xValue, latestTraceRef.current, preferredIndex)" in platform
    assert 'traceAxisValues(trace ?? null, "sample_index")' in platform
    assert 'traceAxisValues(trace ?? null, "session_time")' in platform
    assert "const balanceReadoutIndex = playbackIndex ?? transientHoverIndex ?? lockedIndex ?? selectedContextIndex ?? cursorIndex;" in platform


def test_balance_ride_height_series_preserve_raw_zoom_detail() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'const preserveRawZoomDetail = preset === "Platform / Rake / Ride Height";' in platform
    assert "const channelValues = rawSeriesSamples(trace, channel.name);" in platform
    assert "activeSampleIndices[index] ?? index" in platform
    assert "activeSessionTimes[index] ?? null" in platform
    assert 'dimensions: ["lap_dist_ft", "value", "sample_index", "session_time"]' in platform
    assert "smooth: false" in platform
    assert 'sampling: preserveRawZoomDetail ? undefined : "lttb"' in platform
    assert "large: false" in platform
    assert "progressive: 0" in platform
    assert "progressiveThreshold: 0" in platform


def test_balance_readout_uses_unavailable_for_missing_values_not_zero() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "function fmtReadout" in platform
    assert 'return "—";' in platform
    assert 'return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;' in platform


def test_balance_setup_context_is_collapsed_below_chart() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "renderBalanceSetupContext" in platform
    assert '<details className="balance-setup-context">' in platform
    assert "<summary>Setup context</summary>" in platform
    assert "workbenchView === \"balance\" && renderBalanceSetupContext()" in platform
    assert ".balance-setup-context" in styles


def test_balance_setup_context_can_show_next_gen_lr_offset_note() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    telemetry_types = _read("ui/src/types/telemetry.ts")

    assert "function lrRideHeightOffsetNote" in platform
    assert "Next Gen LR ride-height offset applied: ${offset} in" in platform
    assert "meta?.lr_ride_height_offset_applied" in platform
    assert "{lrRideHeightOffsetNote(trace) && (" in platform
    assert "lr_ride_height_offset_applied?: boolean;" in telemetry_types
    assert "lr_ride_height_offset_car_path?: string | null;" in telemetry_types


def test_frontend_does_not_apply_lr_offset_math() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "lr_ride_height_in - 0.5" not in platform
    assert "lr_ride_height_in -0.5" not in platform
    assert "lr_ride_height_in -= 0.5" not in platform
    assert "lr_ride_height_mm - 12.7" not in platform


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
    assert "Zoomed: ${formatDistanceNumber(start)}-${formatDistanceNumber(end)} ft" in platform
    assert ".trace-drag-zoom-band" in styles


def test_map_overlay_formats_chart_window_to_tenths_without_rounding_range() -> None:
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")

    assert "function formatDistanceNumber(value: number): string" in overlay
    assert "minimumFractionDigits: 1" in overlay
    assert "maximumFractionDigits: 1" in overlay
    assert "return `${formatDistanceNumber(start)}-${formatDistanceNumber(end)} ft`;" in overlay
    assert "point.distanceFt >= start && point.distanceFt <= end" in overlay
    assert "Math.round(start)" not in overlay
    assert "Math.round(end)" not in overlay


def test_reset_zoom_does_not_clear_selected_event_or_session_state() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    reset_body = platform.split("const resetRideHeightZoom = useCallback(() => {", 1)[1].split("}, [onMapOverlayZoomRangeChange]);", 1)[0]

    assert 'chartRef.current?.dispatchAction({ type: "dataZoom", start: 0, end: 100 });' in reset_body
    assert "onMapOverlayZoomRangeChange?.(null)" in reset_body
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
    assert "All visible platform checks are clear." in platform
    assert "internal checks hidden/clear" in platform
    assert "internal evidence item" in platform
    assert "No platform diagnostic events for this lap" in platform


def test_actionable_mode_does_not_render_safe_legacy_platform_buttons() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "isSafeLegacyPlatformEvent" in platform
    assert 'severity === "safe"' in platform
    assert "visibleLegacyEvents" in platform
    assert "platformEvents.length === 0 && visiblePlatformEvents.length === 0 && visibleLegacyEvents.length > 0" in platform
    assert "visibleLegacyEvents.map((event)" in platform


def test_clear_platform_diagnostics_are_grouped_not_visible_events() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    rail = _read("ui/src/components/PriorityRail.tsx")
    visibility = _read("ui/src/utils/platformEventVisibility.ts")

    assert "export function isClearPlatformDiagnostic" in visibility
    assert 'event.severity === "info"' in visibility
    assert "clearPlatformDiagnostics" in platform
    assert "platform-clear-checks" in platform
    assert "Clear checks ({clearPlatformDiagnosticCount})" in platform
    assert "clearDiagnosticCount" in rail
    assert "internal checks hidden/clear." in rail


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
