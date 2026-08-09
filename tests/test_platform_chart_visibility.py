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


def test_chart_uses_open_grid_lanes_without_wheel_scroll_trap() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "rowGap(preset, density)" in platform
    assert 'return density === "compact" ? 12 : 18' in platform
    assert 'stroke: row.channels[0]?.color ?? "#38bdf8"' in platform
    assert 'color: "rgba(148, 163, 184, 0.11)"' in platform
    wrapper_block = styles.split(".trace-panel-wrapper {", 1)[1].split("}", 1)[0]
    assert "overflow: visible" in wrapper_block
    assert "max-height" not in wrapper_block
    assert "overflow: auto" not in wrapper_block


def test_platform_workspace_fills_available_cockpit_width() -> None:
    app = _read("ui/src/App.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    platform_block = styles.split(".platform-workbench {", 1)[1].split("}", 1)[0]
    layout_block = styles.split(".platform-layout {", 1)[1].split("}", 1)[0]
    wrapper_block = styles.split(".trace-panel-wrapper {", 1)[1].split("}", 1)[0]
    trace_block = styles.split(".trace-panel {\n  height: auto;", 1)[1].split("}", 1)[0]
    cockpit_workspace_block = styles.split(".cockpit-workspace {\n  flex: 1;", 1)[1].split("}", 1)[0]
    cockpit_main_block = styles.split(".cockpit-workspace-main {", 1)[1].split("}", 1)[0]

    assert "const [inspectorOpen, setInspectorOpen] = useState(false);" in app
    assert "ResizeObserver" in platform
    assert "chart.resize({ width: chartNode.current.clientWidth, height: chartNode.current.clientHeight })" in platform
    assert "flex: 1 1 auto" in platform_block
    assert "width: 100%" in platform_block
    assert "max-width: none" in platform_block
    assert "width: 100%" in layout_block
    assert "max-width: none" in layout_block
    assert "min-width: 0" in layout_block
    assert "flex: 1 1 auto" in wrapper_block
    assert "width: 100%" in wrapper_block
    assert "max-width: none" in wrapper_block
    assert "width: 100%" in trace_block
    assert "min-width: 0" in cockpit_workspace_block
    assert "max-width: none" in cockpit_workspace_block
    assert "width: 100%" in cockpit_main_block
    assert "max-width: none" in cockpit_main_block


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
    assert "axisTick: {\n        show: index === rows.length - 1," in platform


def test_platform_charts_use_per_panel_readouts_without_side_cursor() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")
    styles = _read("ui/src/styles.css")

    assert "Cursor Readout" not in platform
    assert 'className="cursor-panel"' not in platform
    assert "Crosshair" not in platform
    assert ".cursor-panel" not in styles
    assert '<div className="balance-panel-readout-layer" aria-live="polite">' in readout
    assert "<PlatformChartPanelReadout" in platform
    assert 'className="platform-layout balance-chart-layout"' in platform
    assert 'workbenchView === "balance" && (\n            <div className="balance-panel-readout-layer"' not in platform
    assert "panels={balancePanelReadouts}" in platform
    assert "panels.map" in readout
    assert "panel.channels.map((channel)" in readout
    assert "channel.readoutLabel" in readout
    assert "fmtReadout(channel.cursorValue" in readout
    assert "balance-panel-stat-readout" in readout
    assert '<span className="balance-selected-context">Event {eventTitle}</span>' in readout


def test_balance_default_removes_duplicate_ride_height_engineering_cards() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'case "balance": return null;' in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView && renderEngineeringPanel()' in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView && (' in platform
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


def test_focused_platform_tabs_do_not_render_global_risk_strip() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'className="platform-risk-strip"' not in platform
    assert "riskSegments" not in platform
    assert "risk-strip-empty" not in platform
    assert "platform-event-summary-strip" in platform
    assert "Platform Diagnostic Events" in platform


def test_tires_view_removes_prototype_full_lap_distribution_panel() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    subnav = _read("ui/src/components/WorkbenchSubnav.tsx")
    styles = _read("ui/src/styles.css")
    visible_views = subnav.split("export const WORKBENCH_VIEWS", 1)[1].split("];", 1)[0]

    assert '{ id: "balance", label: "Balance", icon: "BAL" }' in visible_views
    assert '{ id: "rear_scrape", label: "Scrape / Scrub", icon: "SCR" }' in visible_views
    assert '{ id: "shocks", label: "Shocks", icon: "SHK" }' in visible_views
    assert 'label: "Tires"' not in visible_views
    assert 'icon: "TIR"' not in visible_views
    assert 'id: "tires"' not in visible_views
    assert 'label: "Diffuser"' not in visible_views
    assert 'icon: "DIF"' not in visible_views
    assert 'id: "diffuser"' not in visible_views
    assert 'view === "aero_load" || view === "grade_pull" || view === "tires" || view === "diffuser"' in subnav
    assert "CornerTireMap" not in platform
    assert "tireMapMode" not in platform
    assert "Tire map: Full-lap distribution" not in platform
    assert "CornerBarChart" not in platform
    assert 'const renderTiresPanel = () => null;' in platform
    assert "Tire temps are measured iRacing telemetry channels" not in platform
    assert "Tire Pressure / Camber Setup" not in platform
    assert "Bar charts show" not in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView' in platform
    assert "corner-tire-map" not in styles
    assert "tire-map-mode-select" not in styles
    assert "tire-map-mode-btn" not in styles
    assert "tire-map-grid" not in styles
    assert "tire-map-corner" not in styles
    assert "tire-corner-value" not in styles
    assert "tire-data-empty" not in styles

    tires_preset = platform.split('"Tires": [', 1)[1].split('  "Shocks": [', 1)[0]
    assert 'label: "Pressure Gain [psi]"' in tires_preset
    assert 'label: "Temp Spread [C]"' in tires_preset
    assert 'label: "Slip Ratio Proxy"' in tires_preset


def test_tire_backend_channels_remain_available_for_evidence() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    channels = _read("ui/src/constants/workbenchChannels.ts")
    channel_meta = _read("ui/src/utils/channelMeta.ts")
    calculated = _read("racelab_engine/analysis/calculated_channels.py")

    calculated_literal_channels = [
        "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
        "lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain",
        "lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread",
        "lf_wear_spread", "rf_wear_spread", "lr_wear_spread", "rr_wear_spread",
        "lf_camber_temp_bias_c", "rf_camber_temp_bias_c",
        "lr_camber_temp_bias_c", "rr_camber_temp_bias_c",
    ]
    generated_slip_channels = [
        "lf_slip_ratio_proxy", "rf_slip_ratio_proxy", "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
    ]

    for channel in [*calculated_literal_channels, *generated_slip_channels]:
        assert channel in channels
        assert channel in channel_meta

    for channel in calculated_literal_channels:
        assert channel in calculated

    assert 'f"{c}_slip_ratio_proxy"' in calculated
    assert "channelHasNumericData(trace, channel.name)" in platform


def test_diffuser_view_removes_engineering_metric_card_block() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    channels = _read("ui/src/constants/workbenchChannels.ts")
    channel_meta = _read("ui/src/utils/channelMeta.ts")
    calculated = _read("racelab_engine/analysis/calculated_channels.py")
    vectorized = _read("racelab_engine/analysis/vectorized_channels.py")

    assert "const renderDiffuserPanel = () => null;" in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView && renderEngineeringPanel()' in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView && (' in platform
    assert 'EngineeringMetricCard title="Front Center RH"' not in platform
    assert 'EngineeringMetricCard title="Rear Center RH"' not in platform
    assert 'EngineeringMetricCard title="Smooth Diffuser Volume"' not in platform
    assert 'EngineeringMetricCard title="Track Width Used"' not in platform
    assert 'EngineeringMetricCard title="Wheelbase Used"' not in platform
    assert "Diffuser Geometry Setup" not in platform
    assert "Jump to Min Smooth Diffuser Volume" not in platform

    diffuser_preset = platform.split("  Diffuser: [", 1)[1].split("],\n};", 1)[0]
    for label in [
        'label: "Front Center RH [in]"',
        'label: "Rear Center RH [in]"',
        'label: "Smooth Diffuser Volume [ft3]"',
    ]:
        assert label in diffuser_preset

    for channel in [
        "front_center_rh_in",
        "rear_center_rh_in",
        "smooth_center_rake_in",
        "diffuser_track_width_in",
        "diffuser_wheelbase_in",
        "diffuser_base_volume_ft3",
        "diffuser_wedge_volume_ft3",
        "diffuser_volume_ft3",
        "smooth_diffuser_volume_ft3",
    ]:
        assert channel in channels
        assert channel in channel_meta
        assert channel in calculated
        assert channel in vectorized


def test_aero_and_grade_views_are_backend_only_not_visible_platform_tabs() -> None:
    subnav = _read("ui/src/components/WorkbenchSubnav.tsx")
    channels = _read("ui/src/constants/workbenchChannels.ts")
    channel_meta = _read("ui/src/utils/channelMeta.ts")
    calculated = _read("racelab_engine/analysis/calculated_channels.py")

    visible_views = subnav.split("export const WORKBENCH_VIEWS", 1)[1].split("];", 1)[0]
    assert 'label: "Aero Load"' not in visible_views
    assert 'icon: "AER"' not in visible_views
    assert 'label: "Grade / Pull"' not in visible_views
    assert 'icon: "GRD"' not in visible_views
    assert 'view === "aero_load" || view === "grade_pull" || view === "tires" || view === "diffuser"' in subnav
    assert 'return "balance";' in subnav

    for channel in [
        "aero_load_index",
        "aero_load_index_180mph",
        "dynamic_pressure_psf",
        "dynamic_pressure_pa",
        "dynamic_pressure_lap_index",
        "dynamic_grade_rad",
        "dynamic_grade_deg",
        "grade_corrected_long_accel_mps2",
        "grade_force_proxy_n",
        "grade_context_label",
        "grade_corrected_speed_loss_mph_s",
    ]:
        assert channel in channels
        assert channel in channel_meta
        assert channel in calculated

    assert "Proxy - not a direct force measurement." in channel_meta
    assert "Estimated from acceleration vs speed derivative, not surveyed elevation." in channel_meta


def test_balance_panel_readouts_replace_global_readout_strip() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")
    styles = _read("ui/src/styles.css")

    assert "balancePanelReadouts" in platform
    assert "hasExplicitReadoutContext" in platform
    assert "balance-panel-readout-layer" in readout
    assert "balance-panel-cursor-readout" in readout
    assert "balance-panel-stat-readout" in readout
    assert 'className="platform-layout balance-chart-layout"' in platform
    assert "Cursor Readout" not in platform
    assert 'className="cursor-panel"' not in platform
    assert "balanceChartReadout" not in platform
    assert ".balance-panel-readout-layer" in styles
    assert ".cursor-panel" not in styles
    assert ".balance-chart-readout" not in styles
    assert "Hover or scrub the chart to inspect ride heights." not in platform


def test_balance_panel_cursor_readouts_include_required_labels_and_colors() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")

    assert 'return "CFSRideHeight [in]";' in platform
    assert 'return "LF Ride Height [in]";' in platform
    assert 'return "RF Ride Height [in]";' in platform
    assert 'return "LR Ride Height [in]";' in platform
    assert 'return "RR Ride Height [in]";' in platform
    assert 'return "Front Avg";' in platform
    assert 'return "Rear Avg";' in platform
    assert 'return "Center Rake";' in platform
    assert 'return "Side Rake";' in platform
    assert 'style={{ color: channel.color }}' in readout
    assert "channel.readoutLabel" in readout
    assert "fmtReadout(channel.cursorValue" in readout


def test_balance_panel_readout_prefers_hover_and_shows_no_cursor_helper() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")

    assert "const balanceReadoutIndex = playbackIndex ?? transientHoverIndex ?? lockedIndex ?? selectedContextIndex ?? cursorIndex;" in platform
    assert "const balanceReadoutSource = playbackIndex != null" in platform
    assert 'const balanceReadoutSourceLabel = balanceReadoutSource === "Locked"' in platform
    assert '"LOCKED \\u00b7 Esc unlocks hover"' in platform
    assert 'title={readoutSource === "Locked" ? "Press Esc to unlock hover" : undefined}' in readout
    assert 'aria-label={readoutSource === "Locked" ? "Locked cursor. Press Escape to unlock hover." : undefined}' in readout
    assert "balanceReadoutLocationSummary" in platform
    assert "formatDistanceFt(balanceReadoutDistance)" in platform
    assert "panelIndex === 0 && lockedSummary" in readout
    assert '<span className="balance-selected-context">{lockedSummary}</span>' in readout
    assert "Cursor: hover or scrub" in readout
    assert platform.index('className="trace-panel platform-telemetry-canvas"') < platform.index("<PlatformChartPanelReadout")


def test_balance_panel_stats_include_accessible_motec_icons() -> None:
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")
    styles = _read("ui/src/styles.css")

    assert 'title="Lowest visible value" aria-label="Lowest visible value">▼' in readout
    assert 'title="Highest visible value" aria-label="Highest visible value">▲' in readout
    assert 'title="Average visible value" aria-label="Average visible value">◆' in readout
    assert "balance-stat-low" in readout
    assert "balance-stat-high" in readout
    assert "balance-stat-avg" in readout
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


def test_balance_visible_stats_use_displayed_samples_inside_zoom_range() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout_body = platform.split("const balancePanelReadouts = useMemo(() => {", 1)[1].split("  }, [", 1)[0]

    assert "displaySeriesSamples(trace, channel.name)" in readout_body
    assert "rawSeriesSamples(trace, channel.name)" not in readout_body
    assert "Visible chart stats are calculated from displayed telemetry samples inside the current zoom window." in readout_body
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
    assert "Cursor values are display-only interpolation along the rendered line; stats below follow the displayed samples." in readout_body
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

    assert 'rawZoomTraceEnabled && balanceCursorDistanceFt != null' in map_body
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
    assert 'const rawZoomTraceEnabled = workbenchView === "balance" || scrapeScrubChartView;' in platform
    assert "if (!rawZoomTraceEnabled || visibleZoomRange == null)" in platform
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

    assert 'const preserveRawZoomDetail = preset === "Platform / Rake / Ride Height" || preset === SCRAPE_SCRUB_PRESET;' in platform
    assert "const channelValues = displaySeriesSamples(trace, channel.name);" in platform
    assert "activeSampleIndices[index] ?? index" in platform
    assert "activeSessionTimes[index] ?? null" in platform
    assert 'dimensions: ["lap_dist_ft", "value", "sample_index", "session_time"]' in platform
    assert "smooth: false" in platform
    assert 'sampling: preserveRawZoomDetail ? undefined : "lttb"' in platform
    assert "large: false" in platform
    assert "progressive: 0" in platform
    assert "progressiveThreshold: 0" in platform


def test_scrape_scrub_tab_is_chart_first_ride_height_vs_speed_loss() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")
    subnav = _read("ui/src/components/WorkbenchSubnav.tsx")
    channels = _read("ui/src/constants/workbenchChannels.ts")
    channel_meta = _read("ui/src/utils/channelMeta.ts")

    assert '{ id: "rear_scrape", label: "Scrape / Scrub", icon: "SCR" }' in subnav
    assert 'const SCRAPE_SCRUB_PRESET = "Ride Height vs Speed Loss";' in platform
    assert "rear_scrape: SCRAPE_SCRUB_PRESET" in platform
    assert "scrub_steering: SCRAPE_SCRUB_PRESET" in platform

    preset_block = platform.split("[SCRAPE_SCRUB_PRESET]: [", 1)[1].split("  Diffuser:", 1)[0]
    assert 'label: "Speed [m/s]"' in preset_block
    assert 'name: "speed_mps"' in preset_block
    assert 'label: "Front Ride Heights [in]"' in preset_block
    assert 'name: "cfs_ride_height_in"' in preset_block
    assert 'name: "lf_ride_height_in"' in preset_block
    assert 'name: "rf_ride_height_in"' in preset_block
    assert 'label: "Speed Loss [m/s²]"' in preset_block
    assert 'name: "speed_loss_mps2"' in preset_block
    assert 'label: "Rear Ride Heights [in]"' in preset_block
    assert 'name: "lr_ride_height_in"' in preset_block
    assert 'name: "rr_ride_height_in"' in preset_block
    assert 'name: "rear_min_ride_height_in"' in preset_block

    assert preset_block.index('label: "Speed [m/s]"') < preset_block.index('label: "Front Ride Heights [in]"')
    assert preset_block.index('label: "Front Ride Heights [in]"') < preset_block.index('label: "Speed Loss [m/s²]"')
    assert preset_block.index('label: "Speed Loss [m/s²]"') < preset_block.index('label: "Rear Ride Heights [in]"')
    speed_panel = preset_block.split('label: "Speed [m/s]"', 1)[1].split('label: "Front Ride Heights [in]"', 1)[0]
    loss_panel = preset_block.split('label: "Speed Loss [m/s²]"', 1)[1].split('label: "Rear Ride Heights [in]"', 1)[0]
    assert 'name: "speed_mps"' in speed_panel
    assert 'name: "speed_loss_mps2"' not in speed_panel
    assert 'name: "speed_loss_mps2"' in loss_panel
    assert 'name: "speed_mps"' not in loss_panel
    assert 'name: "speed_rate_mps2"' not in loss_panel
    assert "min: 0" in loss_panel
    assert 'zeroLine: true' in loss_panel
    assert 'name: "speed_mph"' not in preset_block
    assert 'name: "speed_rate_mph_s"' not in preset_block
    assert 'name: "speed_rate_mph_1000ft"' not in preset_block
    assert 'name: "speed_rate_mps2"' not in preset_block

    assert "front_scrub_proxy" not in preset_block
    assert "rear_scrub_proxy" not in preset_block
    assert "drag_scrub_suspicion" not in preset_block
    assert "full_throttle_resistance_index" not in preset_block
    assert "rear_scrape_risk_score" not in preset_block

    assert "const renderRearScrapeScrubPanel = () => null;" in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView && renderEngineeringPanel()' in platform
    assert 'workbenchView !== "balance" && workbenchView !== "tires" && workbenchView !== "diffuser" && !scrapeScrubChartView && (' in platform
    assert 'scrapeScrubChartView ? "Ride Height vs Speed Loss" : "Ride-height chart density"' in platform
    assert 'const MPH_TO_MPS = 0.44704;' in platform
    assert 'function displaySeriesSamples(trace: TraceResponse | null, channel: string)' in platform
    assert 'if (channel === "speed_loss_mps2") {' in platform
    assert 'rawSeriesSamples(trace, "speed_rate_mps2").map((value) => (' in platform
    assert "Math.max(0, -value)" in platform
    assert 'value * MPH_TO_MPS' in platform
    assert 'const channelValues = displaySeriesSamples(trace, channel.name);' in platform
    assert 'return displaySeriesSamples(trace, channel).some((value) => typeof value === "number" && Number.isFinite(value));' in platform
    assert "speedRateMps2: valueAt(trace, \"speed_rate_mps2\", selectedIndex)" in platform
    assert "panels={balancePanelReadouts}" in platform
    assert "panel.channels.map((channel)" in readout
    assert "fmtReadout(channel.cursorValue" in readout
    assert "fmtReadout(channel.low" in readout
    assert "fmtReadout(channel.high" in readout
    assert "fmtReadout(channel.avg" in readout
    assert '"speed_mps", "speed_mph"' in channels
    assert 'speed_mps: { label: "Speed", unit: "m/s"' in channel_meta
    assert 'speed_rate_mps2: { label: "Speed Rate", unit: "m/s^2"' in channel_meta
    assert 'speed_loss_mps2: { label: "Speed Loss", unit: "m/s^2"' in channel_meta

    for internal_channel in [
        "front_scrub_proxy",
        "rear_scrub_proxy",
        "drag_scrub_suspicion",
        "full_throttle_resistance_index",
        "rear_scrape_risk_score",
    ]:
        assert internal_channel in channels


def test_balance_readout_uses_unavailable_for_missing_values_not_zero() -> None:
    readout = _read("ui/src/components/PlatformChartPanelReadout.tsx")

    assert "function fmtReadout" in readout
    assert 'return "—";' in readout
    assert 'return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;' in readout


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


def test_ride_height_series_uses_nondimming_hover_emphasis() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "const baseLineWidth = channelIndex === 0 ? 1.8" in platform
    assert "width: baseLineWidth + 0.8" in platform
    assert 'focus: "none"' in platform
    assert "shadowColor: `${channel.color}73`" in platform
    assert "blur: { lineStyle" not in platform
    assert "legendHoverLink: false" in platform
    assert 'inactiveColor: "#475569"' in platform
    assert "itemGap: 11" in platform


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


def test_platform_event_selection_is_replaced_from_the_current_run_collection() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    event_load_effect = platform.split(
        "if (externalPlatformEvents) {", 1
    )[1].split("const visiblePlatformEvents", 1)[0]

    assert "setSelectedPlatformEvent(null);\n    setPlatformEvents([]);" in platform
    assert "}, [overview.run_id, overviewTrace.lap]);" in platform
    assert "setPlatformEvents([]);" in event_load_effect
    assert "platformEvents.find((event) => event.event_id === selected.event_id) ?? null" in event_load_effect
    assert "platformEvents.some((event) => event.event_id === selected.event_id) ? selected" not in event_load_effect


def test_escape_unlock_restores_live_cursor_hover_readout() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    escape_body = platform.split('if (e.key !== "Escape") return;', 1)[1].split("window.addEventListener", 1)[0]

    assert "lastPointerOffsetRef" in platform
    assert "restoreHoverAtPointerRef" in platform
    assert "cancelDragZoomRef.current()" in platform
    assert "clickedSampleIndexRef.current = null" in platform
    assert "hoverSampleIndexRef.current = index" in platform
    assert "setHoverSampleIndex(index)" in platform
    assert "const restoredHover = restoreHoverAtPointerRef.current()" in platform
    assert "if (!restoredHover) hideCursorLine()" in platform
    assert "e.preventDefault()" in escape_body
    # The local chart lock clears first, but the shell-level atomic evidence
    # clear must still receive Escape and erase zone/channel/trust context.
    assert "e.stopPropagation()" not in escape_body
    assert "focusEvidence(" not in escape_body
    assert "setVisibleZoomRange(null)" not in escape_body
    assert "dispatchAction({ type: \"dataZoom\"" not in escape_body
    assert "setSelectedRun" not in escape_body
    assert "setSession" not in escape_body


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
    assert "Supported platform risk checks are clear for this eligible lap." in platform
    assert "qualified clear checks hidden" in platform
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
    assert 'event.diagnostic_state === "clear_check"' in visibility
    assert "clearPlatformDiagnostics" in platform
    assert "platform-clear-checks" in platform
    assert "Clear checks ({clearPlatformDiagnosticCount})" in platform
    assert "clearDiagnosticCount" in rail
    assert "qualified clear checks hidden." in rail


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


def test_platform_event_card_hides_notebook_stage_test_action() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "handleOpenSetupFromPlatformEvent" in platform
    assert "Open Setup" in platform
    assert "handleStageTestFromPlatformEvent" not in platform
    assert "Stage Test" not in platform
    assert "Stage a notebook test" not in platform
    assert '"setup_impact"' in platform


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


def test_platform_decision_and_local_trace_precede_whole_lap_charts() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    decision = platform.index('className="platform-decision-card"')
    local_trace = platform.index("<LocalPlatformTrace", decision)
    disclosure = platform.index('className="platform-whole-lap-disclosure"', local_trace)
    whole_lap_chart = platform.index('className="platform-layout balance-chart-layout"', disclosure)
    assert decision < local_trace < disclosure < whole_lap_chart
    assert "Highest-priority platform evidence" in platform
    assert "platformEventPriority" in platform
    assert "recorded samples only" in platform
    assert "Whole-lap data is not substituted." in platform


def test_whole_lap_charts_are_accessibly_disclosed_by_mode() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    styles = _read("ui/src/styles.css")

    assert 'useState(selection.selectedMode === "learning")' in platform
    assert 'setWholeLapExpanded(selection.selectedMode === "learning")' in platform
    assert 'aria-expanded={wholeLapExpanded}' in platform
    assert 'aria-controls="platform-whole-lap-charts"' in platform
    assert '{wholeLapExpanded && (' in platform
    assert ".platform-whole-lap-toggle:focus-visible" in styles


def test_platform_decision_preserves_error_unavailable_and_clear_truth() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    decision = platform.split('className="platform-decision-card"', 1)[1].split("<WorkbenchSubnav", 1)[0]
    assert 'platformEventsLoadStatus === "error"' in decision
    assert 'platformEventsLoadStatus === "unavailable"' in decision
    assert 'platformEventsLoadStatus === "clear"' in decision
    assert "Missing telemetry remains unavailable, never safe or zero." in decision
    assert "Supported platform risk checks are clear for this eligible lap." in decision
    assert "other mechanisms are not implied safe" in decision
    assert "Proxy evidence only. It does not measure aerodynamic force." in decision
