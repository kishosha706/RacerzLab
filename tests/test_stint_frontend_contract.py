from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_laps_tab_renders_stint_intelligence_directly() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    client = (ROOT / "ui" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    types = (ROOT / "ui" / "src" / "types" / "laps.ts").read_text(encoding="utf-8")

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
    assert "stint-chart-fastest-marker" in source
    assert "stint-chart-selected-marker" in source
    assert "racePaceDomain" in source
    assert "percentile" in source
    assert "Include outliers in scale" in source
    assert "Scale: Race pace" in source
    assert "stint-graph-summary-strip" in source
    assert "Excluded from scale" in source
    assert "outlier excluded from pace scale" in source
    assert "stint-chart-range" in source
    assert "stint-chart-outlier-label" in source
    assert "stint-filter-bar" in source
    assert "Current run only" in source
    assert "Same car/track only" in source
    assert "Graphed only" in source
    assert "Hide invalid/caution laps" in source
    assert "Export Selected CSV" in source
    assert "exportSelectedStintsCsv" in source
    assert "Graph Selected Stints" in source
    assert "Graph Selected" in source
    assert "Clear Graph" in source
    assert "Show delta to best" in source
    assert "Exclude invalid laps" in source
    assert "Session Runs" in source
    assert "Current run and runs added to this open session." in source
    assert "Runs from the loaded session." in source
    assert "Only the current run is shown. Add runs to this session to compare stints." in source
    assert "Load older session from startup to view previous runs." in source
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
    assert "Add to Test Basket" in source
    assert "3-Lap Avg" in source
    assert "5-Lap Avg" in source
    assert "10-Lap Avg" in source
    timing_sheet = source.split('<table className="compact-table stint-table timing-sheet-table">', 1)[1].split("</table>", 1)[0]
    assert "stintAverageColumns.map((column) => <th key={column.size}>{column.label}</th>)" in timing_sheet
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
