from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_line_charts_share_one_open_telemetry_visual_system() -> None:
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")
    chart_styles = styles.split("/* Premium telemetry visualization system */", 1)[1]

    for selector in (
        ".delta-traces-surface",
        ".delta-traces-stage",
        ".delta-chart-tooltip",
        ".stint-graph-panel.telemetry-visualization-panel",
        ".stint-chart-svg.telemetry-line-chart",
        ".stint-chart-plot-backdrop",
        ".stint-chart-series[data-series-role=\"selected\"]",
        ".stint-chart-point-group:focus-visible",
        ".platform-whole-lap-disclosure",
        ".platform-telemetry-surface",
        ".platform-telemetry-canvas.trace-panel",
        ".platform-telemetry-canvas.trace-panel:focus-visible",
        ".platform-local-trace",
        ".platform-local-trace-grid",
    ):
        assert selector in chart_styles

    assert "--telemetry-canvas:" in chart_styles
    assert "--telemetry-grid:" in chart_styles
    assert "radial-gradient" in chart_styles
    assert "backdrop-filter: blur(10px)" in chart_styles
    assert "border: 0" in chart_styles


def test_chart_polish_keeps_selected_proxy_and_reduced_motion_states_visible() -> None:
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")
    chart_styles = styles.split("/* Premium telemetry visualization system */", 1)[1]

    assert ".delta-traces-key-line.is-proxy" in chart_styles
    assert "border-top-style: dashed" in chart_styles
    assert '[data-point-state="invalid"]' in chart_styles
    assert '[data-point-state="excluded"]' in chart_styles
    assert '[data-chart-selection="locked"]' in chart_styles
    assert ".stint-chart-fastest-marker" in chart_styles
    assert ".stint-chart-selected-marker" in chart_styles
    assert "@media (prefers-reduced-motion: reduce)" in chart_styles
    reduced_motion = chart_styles.rsplit(
        "@media (prefers-reduced-motion: reduce)", 1
    )[1]
    assert "transition: none" in reduced_motion


def test_chart_surfaces_reflow_without_hiding_units_or_status() -> None:
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")
    chart_styles = styles.split("/* Premium telemetry visualization system */", 1)[1]

    assert "@media (max-width: 1080px)" in chart_styles
    assert "@media (max-width: 760px)" in chart_styles
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in chart_styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in chart_styles
    assert ".stint-chart-axis-title" in chart_styles
    assert ".delta-traces-scope" in chart_styles
    assert ".stint-graph-detail-strip" in chart_styles
