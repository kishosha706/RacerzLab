from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _platform() -> str:
    return (ROOT / "ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")


def test_platform_chart_uses_open_telemetry_lanes_instead_of_boxed_rows() -> None:
    source = _platform()
    graphic = source.split("const graphic: any[] = [];", 1)[1].split(
        "const totalChartH", 1
    )[0]

    assert 'axisLine: { show: false }' in source
    assert 'color: "rgba(148, 163, 184, 0.11)"' in source
    assert 'type: "dashed" as const' in source
    assert 'stroke: row.channels[0]?.color ?? "#38bdf8"' in graphic
    assert 'type: "rect"' not in graphic
    assert 'x2: 9999' not in graphic


def test_platform_chart_preserves_raw_trace_shape_and_proxy_semantics() -> None:
    source = _platform()

    assert "smooth: false" in source
    assert "connectNulls: false" in source
    assert 'if (proxyChannel) lineType = "dashed";' in source
    assert 'data-proxy-semantics="dashed"' in source
    assert "sampling: preserveRawZoomDetail ? undefined : \"lttb\"" in source
    assert "const singleMeasuredTrace = row.channels.length === 1 && !proxyChannel" in source
    assert "opacity: 0.045" in source


def test_platform_chart_has_clear_static_hover_tooltip_and_line_emphasis() -> None:
    source = _platform()

    assert "function platformChartTooltipMarkup(" in source
    assert "function escapeChartTooltipText(" in source
    assert 'data-chart-tooltip="telemetry"' in source
    assert "formatTooltipValue(meta.channelName, value)" in source
    assert "meta.isProxy" in source
    assert 'trigger: "axis"' in source
    assert "transitionDuration: 0" in source
    assert 'focus: "none"' in source
    assert "width: baseLineWidth + 0.8" in source
    assert "blur: { lineStyle" not in source


def test_platform_chart_supports_keyboard_sample_inspection() -> None:
    source = _platform()

    assert 'aria-roledescription="interactive telemetry line chart"' in source
    assert "tabIndex={0}" in source
    assert "onKeyDown={handleChartKeyDown}" in source
    assert "const keyboardTraceIndices = useMemo" in source
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in source
    assert "jumpToIndex(keyboardTraceIndices[nextPosition] ?? null)" in source
    assert "Use Left and Right Arrow to inspect samples" in source


def test_platform_event_markers_and_zoom_have_premium_but_static_treatment() -> None:
    source = _platform()

    assert "const polishedEventMarkLines" in source
    assert "eventAnnotations.markAreas[index]?.color" in source
    assert "shadowColor: `${color}66`" in source
    assert 'type: "slider", xAxisIndex: rows.map((_, i) => i)' in source
    assert 'filterMode: "none"' in source
    assert "showDataShadow: true" in source
    assert "selectedDataBackground" in source
    assert "brushSelect: false" in source
    assert 'type: "inside"' not in source
    assert "animation: false" in source
    assert 'data-chart-motion="disabled"' in source


def test_local_platform_trace_layers_grid_glow_and_focus_without_smoothing_data() -> None:
    source = _platform()
    local_trace = source.split("function LocalPlatformTrace({", 1)[1].split(
        "/** Find the trace sample index", 1
    )[0]

    assert 'data-chart-kind="local-telemetry"' in local_trace
    assert 'className="platform-local-trace-field"' in local_trace
    assert 'className="platform-local-trace-grid"' in local_trace
    assert "platform-local-trace-glow" in local_trace
    assert "platform-local-trace-line" in local_trace
    assert 'className="platform-local-trace-focus"' in local_trace
    assert 'strokeLinecap="round"' in local_trace
    assert "signals auto-scaled independently" in local_trace
    assert 'isProxy: isProxyChannel(channelName)' in source
    assert 'data-channel-basis={channel.isProxy ? "proxy" : "measured"}' in local_trace
    assert 'strokeDasharray={channel.isProxy ? "7 6" : undefined}' in local_trace
    assert 'channel.isProxy && <b>Proxy</b>' in local_trace
    assert '" · proxies dashed"' in local_trace
    assert "getChannelUnit(channelName) || rowUnit(channelName)" in source
