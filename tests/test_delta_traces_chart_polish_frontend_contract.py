from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACES = (ROOT / "ui/src/components/DeltaTracesView.tsx").read_text(encoding="utf-8")


def test_delta_traces_exposes_a_premium_open_chart_surface() -> None:
    for hook in (
        'data-chart-surface="delta-comparison"',
        'data-chart-density="trace-lanes"',
        "delta-traces-surface",
        "delta-traces-header",
        "delta-traces-key",
        "delta-traces-stage",
        'data-chart-engine="echarts"',
        "delta-chart-tooltip",
    ):
        assert hook in TRACES

    assert 'aria-label="Full-lap signal delta traces"' in TRACES
    assert 'role="img"' in TRACES
    assert "Full-Lap Delta Traces" in TRACES
    assert "Matched track position · test minus baseline" in TRACES


def test_delta_traces_uses_clear_axis_cursor_and_tooltip_hierarchy() -> None:
    assert "show: true,\n        trigger: \"axis\"" in TRACES
    assert 'triggerOn: "mousemove|click"' in TRACES
    assert 'confine: true' in TRACES
    assert 'link: [{ xAxisIndex: available.map((_, i) => i) }]' in TRACES
    assert 'formatter: "0 Δ"' in TRACES
    assert 'formatter: "TARGET ZONE"' in TRACES
    assert "compactAxisValue" in TRACES
    assert "channelData.unit" in TRACES
    assert "deltaData.x_unit" in TRACES
    assert "Test − baseline" in TRACES
    assert "Gap · no paired sample" in TRACES
    assert 'value == null || value === ""' in TRACES


def test_delta_traces_preserves_gap_proxy_and_physical_position_truth() -> None:
    assert 'x_axis: "lap_dist_ft"' in TRACES
    assert 'connectNulls: false' in TRACES
    assert 'smooth: false' in TRACES
    assert 'type: chData.is_proxy ? "dashed" : "solid"' in TRACES
    assert 'chData?.is_proxy ? "PROXY DELTA" : "CHANNEL DELTA"' in TRACES
    assert 'data-trace-key="proxy"' in TRACES
    assert 'areaStyle: ch === "speed_mph" && !chData.is_proxy' in TRACES
    assert "origin: 0" in TRACES
    assert "target_zone_start_pct: startPct" in TRACES
    assert "target_zone_end_pct: endPct" in TRACES


def test_delta_traces_resizes_with_its_container_and_respects_motion_preferences() -> None:
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in TRACES
    assert "animation: !reduceMotion" in TRACES
    assert "new ResizeObserver(resize)" in TRACES
    assert "resizeObserver?.observe(node)" in TRACES
    assert "resizeObserver?.disconnect()" in TRACES
    assert "window.requestAnimationFrame" in TRACES
    assert "window.cancelAnimationFrame" in TRACES
    assert 'aria-label="Reset delta trace zoom"' in TRACES
    assert 'dispatchAction({ type: "dataZoom", start: 0, end: 100 })' in TRACES


def test_delta_traces_commits_only_the_latest_exact_scope_response() -> None:
    assert "const requestSequenceRef = useRef(0)" in TRACES
    assert "const latestRequestRef = useRef" in TRACES
    assert "const deltaRequestKey = useMemo(() => JSON.stringify(deltaRequest)" in TRACES
    assert "deltaResult?.requestKey === deltaRequestKey" in TRACES
    assert "setDeltaResult(null)" in TRACES
    assert "if (!isLatestRequest()) return" in TRACES
    assert "data.baseline_run_id === deltaRequest.baseline_run_id" in TRACES
    assert "data.test_run_id === deltaRequest.test_run_id" in TRACES
    assert "data.baseline_lap === deltaRequest.baseline_lap" in TRACES
    assert "data.test_lap === deltaRequest.test_lap" in TRACES
    assert "data.x_axis === deltaRequest.x_axis" in TRACES
    assert "data.target_zone_start_pct - deltaRequest.target_zone_start_pct" in TRACES
    assert "data.target_zone_end_pct - deltaRequest.target_zone_end_pct" in TRACES
    assert "requestedChannels.every" in TRACES
    assert "if (isLatestRequest()) setLoading(false)" in TRACES
