from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_laps_tab_renders_stint_intelligence_directly() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    client = (ROOT / "ui" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    types = (ROOT / "ui" / "src" / "types" / "laps.ts").read_text(encoding="utf-8")
    styles = (ROOT / "ui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "Stint Intelligence" in source
    assert "My Stints" in source
    assert "Lap averages, falloff, and long-run pace from your imported runs." in source
    assert "fetchStints" in source
    assert "compareStints" in source
    assert "const [showBestWindows, setShowBestWindows] = useState(false);" in source
    assert "Best Windows" in source
    assert "My Stints" in source
    assert "Fastest Lap" in source
    assert "Current Avg Lap" in source
    assert "stintAverageColumns.map" in source
    assert "L1-5" in source
    assert "L36-40" in source
    assert "L56-60" in source
    assert "stint-run-summary" in source
    assert "stint-window-card-row" in source
    assert "stint-selected-toolbar" in source
    assert "stint-graph-panel" in source
    assert "stint-summary-drawer" in source
    assert "Stint Summary" in source
    assert "stint-summary-lap-table" in source
    assert "stint-graph-tooltip" in source
    assert "stint-graph-detail-strip" in source
    assert "stint-chart-fastest-marker" in source
    assert "stint-chart-best-label" in source
    assert "stint-chart-selected-marker" in source
    assert "stint-chart-selected-guide" in source
    assert "stint-chart-zero-line" in source
    assert "stint-chart-bucket-guide" in source
    assert "graphRangeOverlays" in source
    assert "graphStatusesForPoint" in source
    assert "Selected Window -" in source
    assert "Baseline Window -" in source
    assert "Test Window -" in source
    assert "Delta to best" in source
    assert "Invalid reason" in source
    assert "Stint lap" in source
    assert "Flags " in source
    assert "chartX(tick, graphChart.xMin, graphChart.xMax)" in source
    assert "graphChart.xTicks.map" in source
    assert "graphChart.yTicks.map" in source
    assert "graphYLabel(tick, stintGraphMode)" in source
    assert "racePaceDomain" in source
    assert "percentile" in source
    assert "Include outliers in scale" in source
    assert "Scale: Race pace" in source
    assert "stint-graph-summary-strip" in source
    assert "Excluded from scale" in source
    assert "outlier excluded from pace scale" in source
    assert "stint-chart-range" in source
    assert "stint-chart-outlier-label" in source
    assert "const [showAdvancedControls, setShowAdvancedControls] = useState(false);" in source
    assert "Advanced Controls" in source
    assert "stint-advanced-panel" in source
    assert "stint-advanced-toggle" in source
    assert "Current run only" in source
    assert "Same car/track only" in source
    assert "Graphed only" in source
    assert "Hide invalid/caution laps" in source
    assert "exportSelectedStintsCsv" in source
    assert "Graph Selected Stints" not in source
    assert "Graph Selected" not in source
    assert "Export Selected CSV" not in source
    assert "Clear" in source
    assert ">Lap Time<" in source
    assert ">Delta to Best<" in source
    assert ">Rolling 5<" in source
    assert "Exclude invalid laps" in source
    assert "Session Runs" in source
    assert "Current run and runs added to this open session." in source
    assert "Runs from the loaded session." in source
    assert "Only the current run is shown. Add runs to this session to compare stints." in source
    assert "Load older session from startup to view previous runs." in source
    assert "Select a stint row to graph, compare, or export." in source
    assert "fetchRunList" not in source
    assert "Field Compare" in source
    assert "Other-driver stint data is not available yet." in source
    assert "Delta to My Best Equivalent" in source
    assert "showFieldCompare" in source
    assert "expandedRunIds" in source
    assert "historyStintData" in source
    assert "loadHistoryRunStints" in source
    assert "selectedStintId" in source
    assert "compactTrendLabel" in source
    assert "No eligible stint windows yet." in source
    assert "Need at least 3 valid laps to start short-run averages." in source
    assert "Need 50/60 valid laps for 50/60-lap averages." in source
    assert "Basket" in source
    assert "3-Lap Avg" in source
    assert "5-Lap Avg" in source
    assert "10-Lap Avg" in source
    assert "const [showEngineeringStintColumns, setShowEngineeringStintColumns] = useState(false);" in source
    assert 'aria-controls="stint-timing-sheet"' in source
    assert 'aria-expanded={showEngineeringStintColumns}' in source
    assert 'showEngineeringStintColumns ? "Fewer columns" : "More columns"' in source
    assert 'showEngineeringStintColumns ? "engineering-columns" : "decision-columns"' in source
    timing_sheet = source.split('id="stint-timing-sheet"', 1)[1].split("</table>", 1)[0]
    assert "stintAverageColumns.map((column) => <th scope=\"col\" key={column.size}>{column.label}</th>)" in timing_sheet
    assert '<th scope="col">Stint</th>' in timing_sheet
    assert '<th scope="col">Laps</th>' in timing_sheet
    assert '<th scope="col">Current Avg</th>' in timing_sheet
    assert '<th scope="col">Best Lap</th>' in timing_sheet
    assert '<th scope="col">Best Sustained</th>' in timing_sheet
    assert '<th scope="col">Falloff</th>' in timing_sheet
    assert '<th scope="col">Evidence</th>' in timing_sheet
    assert 'className="stint-decision-evidence"' in timing_sheet
    assert "bestSustainedAverage(stint)" in timing_sheet
    assert 'const sustainedAveragePriority = [60, 50, 40, 30, 25, 20, 15, 10] as const;' in source
    assert 'sustained != null ? `${sustained.size}-lap average` : "Need 10+ valid laps"' in timing_sheet
    assert 'className="stint-row-summary-button"' in timing_sheet
    assert 'aria-label={`Select ${stint.display_label_short} and open stint summary`}' in timing_sheet
    assert "setSelectedStintId(stint.stint_id);" in timing_sheet
    assert "setSummaryDrawerStintId(stint.stint_id);" in timing_sheet
    assert ".stint-intelligence-section .stint-row-summary-button:focus-visible" in styles
    assert ".stint-intelligence-section .timing-sheet-table.decision-columns" in styles
    assert ".stint-intelligence-section .timing-sheet-table.engineering-columns" in styles
    sticky_first_column = styles.split(".timing-sheet-table th:first-child,", 1)[1].split("}", 1)[0]
    assert "position: sticky" in sticky_first_column
    assert "left: 0" in sticky_first_column
    assert "L1-5" not in timing_sheet
    assert "L6-10" not in timing_sheet
    assert "My Stint Progression" not in timing_sheet
    assert "Best Rolling Windows" not in timing_sheet
    assert "Progression Buckets" in source
    assert "Evidence\" : view === \"windows\"" not in source
    assert "compare-subnav" not in source
    assert "setWorkspace(\"compare\"" not in source
    stint_section = source.split('className="workspace-section stint-intelligence-section"', 1)[1].split('{subview === "all_sessions" && (', 1)[0]
    assert "<th>Actions</th>" not in stint_section
    assert "export function fetchStints" in client
    assert "export function fetchSessionRunList" in client
    assert "export interface StintSummary" in types
    assert "export interface StintBucket" in types
    assert "export interface StintGraphPoint" in types
    assert "lap_points" in types
    assert "invalid_reason" in types
    assert "avg_speed_mph" in types
    assert "fuel" in types
    assert "export interface StintRunSummary" in types
    assert "best_avg_by_size" in types
    assert "rolling_50_avg_best" in types
    assert "rolling_60_avg_best" in types
    assert "best_average_size_flags" in types
    assert "stint_rows" in types
    assert "best_window_cards" in types
    assert "run_summary" in types
    assert "primary_stints" in types


def test_laps_best_time_ignores_artificially_fast_junk_laps() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    qualification = source.split("const usefulLaps = useMemo", 1)[1].split("const fastestUsableLap", 1)[0]

    assert "bestUsefulLapMatchesRun(lap, overview.run_id)" in qualification
    assert "authoritativeBestUsefulLap" in qualification
    assert "const times = usefulLaps" in qualification
    assert "Math.min(...times)" in qualification
    assert "laps.filter((lap) => lap.lap_time != null)" not in qualification


def test_laps_rejects_cross_run_or_incomplete_lap_candidates() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    trust = (ROOT / "ui" / "src" / "utils" / "evidenceTrust.ts").read_text(encoding="utf-8")

    assert "overview.laps.filter((lap) => lap.run_id === overview.run_id)" in source
    assert "bestUsefulLapMatchesRun(overview.best_useful_lap, overview.run_id)" in source
    assert "bestUsefulLapMatchesRun(lap, overview.run_id)" in source
    assert "lap.is_complete" in trust
    assert "Number.isFinite(lap.lap_time)" in trust
    assert '"PIT_ROAD"' in trust
    assert "INVALID_PACE_LAP_TAGS.has(tag.trim().toUpperCase())" in trust
    assert "overview.warnings.find(overviewWarningBlocksDecision)" in source
    assert 'blockingRunWarning\n    ? "NO CALL"' in source
    assert 'blockingRunWarning ? "Blocked"' in source

    hostile_laps = [
        {"lap_time": 1.0, "is_useful": False, "lap_type": "partial"},
        {"lap_time": 2.0, "is_useful": False, "lap_type": "invalid"},
        {"lap_time": 2.5, "is_useful": True, "lap_type": "timed", "tags": ["PIT_ROAD"]},
        {"lap_time": 90.0, "is_useful": True, "lap_type": "timed", "tags": []},
    ]
    qualified_times = [
        lap["lap_time"]
        for lap in hostile_laps
        if lap["is_useful"] and not set(lap.get("tags", [])) & {"PIT_ROAD"}
    ]
    assert min(qualified_times) == 90.0


def test_laps_session_history_uses_native_keyboard_controls() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "ui" / "src" / "styles.css").read_text(encoding="utf-8")
    history = source.split('<div className="stint-history-panel">', 1)[1].split(
        '<div className="field-compare-panel">',
        1,
    )[0]

    assert 'type="button"\n                      className="stint-history-header"' in history
    assert 'className={`stint-window-card compact ${isGraphed ? "graphed" : ""}`}' in history
    assert 'className={`stint-history-stint-row ${selectedStint?.stint_id === stint.stint_id ? "selected" : ""}`}' in history
    assert 'aria-label={`Select ${stint.display_label_short} ${formatStintRange(stint)}`}' in history
    assert 'role="button"' not in history
    assert "tabIndex={0}" not in history
    assert ".stint-intelligence-section .stint-history-header:focus-visible" in styles


def test_stint_pace_trace_has_premium_semantic_chart_layers() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    segmenter = source.split("function stintChartPolylineSegments", 1)[1].split(
        "function bestPointForGraphMode",
        1,
    )[0]
    metric_best = source.split("function bestPointForGraphMode", 1)[1].split(
        "function graphBestCueLabel",
        1,
    )[0]
    chart = source.split('data-visualization="stint-pace"', 1)[1].split(
        '{selectedStint ? (',
        1,
    )[0]

    assert "point.valid && !point.excludedFromScale" in segmenter
    assert "Math.abs(point.x - previousX - 1)" in segmenter
    assert "if (!drawable || (!consecutive" in segmenter
    assert 'mode === "rolling_5"' in metric_best
    assert "point.rolling5" in metric_best
    assert "point.deltaToBest" in metric_best
    assert "point.lapTime" in metric_best

    assert "Stint Pace Trace" in chart
    assert 'className="stint-graph-canvas telemetry-chart-shell"' in chart
    assert 'className="stint-chart-svg telemetry-line-chart"' in chart
    assert 'data-chart-kind="stint-pace"' in chart
    assert "data-chart-mode={stintGraphMode}" in chart
    assert 'aria-roledescription="interactive line chart"' in chart
    assert "aria-labelledby={`${chartDefinitionId}-title ${chartDefinitionId}-description`}" in chart
    assert "Use Tab to focus a point and Enter or Space to select it." in chart

    assert 'className="stint-chart-plot-backdrop"' in chart
    assert 'className="stint-chart-plot-glow"' in chart
    assert 'className="stint-chart-grid"' in chart
    assert 'className="stint-chart-range-layer"' in chart
    assert 'className="stint-chart-axis-layer"' in chart
    assert 'className="stint-chart-series-layer"' in chart
    assert 'className="stint-chart-line-halo"' in chart
    assert 'className="stint-chart-line"' in chart
    assert 'className="stint-chart-endpoint-marker"' in chart
    assert "data-series-role={seriesRole}" in chart
    assert "data-range-kind={overlay.className}" in chart

    assert 'className={`stint-chart-point-group ${pointSelected ? "selected" : ""}`}' in chart
    assert 'data-point-state={!point.valid ? "invalid" : point.excludedFromScale ? "excluded" : "eligible"}' in chart
    assert 'data-selected={pointSelected ? "true" : "false"}' in chart
    assert 'role="button"' in chart
    assert "tabIndex={0}" in chart
    assert 'event.key === "Enter" || event.key === " "' in chart
    assert 'className="stint-chart-point-hit-area"' in chart
    assert 'className="stint-chart-fastest-halo"' in chart
    assert 'data-cue="metric-best"' in chart
    assert 'className="stint-chart-selected-halo"' in chart
    assert 'data-cue="selected"' in chart
    assert 'className="stint-chart-selected-guide-halo"' in chart
    assert "!metricBestIsSelected" in chart
    assert 'selectedGraphPointIsMetricBest ? `${graphBestCueLabel(stintGraphMode)} · Selected` : "Selected"' in chart
    assert "stintChartPolylineSegments(series.points)" in chart
    assert "bestPointForGraphMode(series.points, stintGraphMode)" in chart
    assert "const baseRawPoints = series.filter((item) => !item.dashed)" in source
    assert "const visibleBaseRawPoints = baseRawPoints.filter" in source
    assert ".filter((item) => !item.dashed)" in source
    assert "const excludedBasePointIds = new Set(" in source
    assert "baseRawPoints.filter((point) => !point.valid)" in source
    assert "Valid pace outliers remain graphed" in source
    assert "excludedBasePointIds.add(point.id)" not in source

    assert 'className="stint-graph-stat primary"' in chart
    assert '<small>Fastest lap</small>' in chart
    assert '<small>Best rolling 5</small>' in chart
    assert '<small>Best rolling 10</small>' in chart
    assert 'className={`stint-graph-legend-item ${series.dashed ? "rolling" : "pace"}`}' in chart
    assert 'data-line-style={series.dashed ? "dashed" : "solid"}' in chart
