from __future__ import annotations

from pathlib import Path


def test_workbench_trace_channels_include_platform_shock_channels() -> None:
    source = Path("ui/src/constants/workbenchChannels.ts").read_text(encoding="utf-8")
    required_channels = [
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
        "lf_shock_vel_in_s",
        "rf_shock_vel_in_s",
        "lr_shock_vel_in_s",
        "rr_shock_vel_in_s",
        "lf_shock_static_defl_in",
        "rf_shock_static_defl_in",
        "lr_shock_static_defl_in",
        "rr_shock_static_defl_in",
        "lf_shock_defl_delta_in",
        "rf_shock_defl_delta_in",
        "lr_shock_defl_delta_in",
        "rr_shock_defl_delta_in",
    ]

    for channel in required_channels:
        assert f'"{channel}"' in source, f"Workbench trace channels are missing {channel}"


def test_platform_shocks_fetches_reader_without_mounting_panel() -> None:
    source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")
    assert "fetchShockReader" in source
    assert "<ShockReaderPanel" not in source
    assert 'case "shocks": return renderShocksPanel();' in source
    assert "DialIn" not in Path("ui/src/components/ShockReaderPanel.tsx").read_text(encoding="utf-8")


def test_shock_reader_uses_inline_setup_recommendations() -> None:
    panel_source = Path("ui/src/components/ShockReaderPanel.tsx").read_text(encoding="utf-8")
    histogram_source = Path("ui/src/components/ShockHistogram.tsx").read_text(encoding="utf-8")
    platform_source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")

    assert "shock-reader-recommendation" not in panel_source
    assert "shock-reader-corner-card" not in panel_source
    assert "Shock Reader" not in panel_source
    assert "shock-setup-recommendation-badge" in histogram_source
    assert 'className={`shock-panel setup-${setupSide}`}' in histogram_source
    assert ".shock-panel-body" in Path("ui/src/styles.css").read_text(encoding="utf-8")
    assert ".shock-panel.setup-right .shock-panel-body" in Path("ui/src/styles.css").read_text(encoding="utf-8")
    assert "recommendationFor(\"LS Comp\")" in platform_source
    assert 'setupSide={corner.key === "lf" || corner.key === "lr" ? "left" : "right"}' in platform_source


def test_shock_zone_and_multilap_visuals_fail_closed() -> None:
    platform_source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")

    assert "if (!rawDistance || rawDistance.length !== rawValues.length) return [];" in platform_source
    assert "shockReaderLapWindow" in platform_source
    assert "Representative Lap Display · Decision uses laps" in platform_source
    assert "shockReaderLapWindow\n          ? null" in platform_source
    assert "Full-lap samples were not substituted." in platform_source


def test_shock_histograms_render_as_four_corner_grid() -> None:
    platform_source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")
    styles = Path("ui/src/styles.css").read_text(encoding="utf-8")

    corners_block = platform_source.split("const SHOCK_CORNERS: ShockCornerDefinition[] = [", 1)[1].split("];", 1)[0]
    assert corners_block.index('{ key: "lf", label: "LF"') < corners_block.index('{ key: "rf", label: "RF"')
    assert corners_block.index('{ key: "rf", label: "RF"') < corners_block.index('{ key: "lr", label: "LR"')
    assert corners_block.index('{ key: "lr", label: "LR"') < corners_block.index('{ key: "rr", label: "RR"')
    assert "shockCornerModels.map((corner)" in platform_source
    assert 'key={corner.key}' in platform_source
    assert "corner={corner.label}" in platform_source

    grid_block = styles.split(".shock-workstation-grid {", 1)[1].split("}", 1)[0]
    narrow_block = styles.split("@media (max-width: 980px)", 1)[1].split("@media (max-width: 860px)", 1)[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in grid_block
    assert "grid-auto-rows: minmax(340px, auto)" in grid_block
    assert ".shock-workstation-grid" in narrow_block
    assert "grid-template-columns: 1fr" in narrow_block


def test_shock_setup_panels_are_placed_by_car_side() -> None:
    platform_source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")
    styles = Path("ui/src/styles.css").read_text(encoding="utf-8")

    prop_line = 'setupSide={corner.key === "lf" || corner.key === "lr" ? "left" : "right"}'
    body_block = styles.split(".shock-panel-body {", 1)[1].split("}", 1)[0]
    right_body_block = styles.split(".shock-panel.setup-right .shock-panel-body {", 1)[1].split("}", 1)[0]
    medium_block = styles.split("@media (max-width: 1280px)", 1)[1].split("@media (max-width: 1180px)", 1)[0]

    assert prop_line in platform_source
    assert "grid-template-columns: minmax(190px, 220px) minmax(0, 1fr)" in body_block
    assert "grid-template-columns: minmax(0, 1fr) minmax(190px, 220px)" in right_body_block
    assert ".shock-panel.setup-left .shock-setup-strip" in medium_block
    assert ".shock-panel.setup-right .shock-setup-strip" in medium_block
    assert ".shock-panel.setup-left .shock-panel-main" in medium_block
    assert ".shock-panel.setup-right .shock-panel-main" in medium_block


def test_shock_histogram_header_uses_centered_grid_alignment() -> None:
    histogram_source = Path("ui/src/components/ShockHistogram.tsx").read_text(encoding="utf-8")
    styles = Path("ui/src/styles.css").read_text(encoding="utf-8")

    assert 'className="shock-chart-overlay"' in histogram_source
    assert 'className="shock-overlay-channel" style={{ color }}' in histogram_source
    assert 'className="shock-overlay-center-gap" aria-hidden="true"' in histogram_source
    assert 'className="shock-overlay-unit">[in/s]' in histogram_source
    assert histogram_source.index("<span>R Lo</span>") < histogram_source.index("shock-overlay-center-gap")
    assert histogram_source.index("shock-overlay-center-gap") < histogram_source.index("<span>B Lo</span>")

    overlay_block = styles.split(".shock-chart-overlay {", 1)[1].split("}", 1)[0]
    channel_block = styles.split(".shock-overlay-channel {", 1)[1].split("}", 1)[0]
    center_gap_block = styles.split(".shock-overlay-center-gap {", 1)[1].split("}", 1)[0]
    unit_block = styles.split(".shock-overlay-unit {\n  grid-area: unit;", 1)[1].split("}", 1)[0]
    value_block = styles.split(".shock-overlay-metric strong {", 1)[1].split("}", 1)[0]

    assert "display: grid" in overlay_block
    assert 'grid-template-areas: "channel avgR rHi rLo centerGap bLo bHi avgB unit"' in overlay_block
    assert "font-variant-numeric: tabular-nums" in overlay_block
    assert ".shock-overlay-metric.rebound-low { grid-area: rLo; }" in styles
    assert ".shock-overlay-metric.bump-low { grid-area: bLo; }" in styles
    assert "grid-area: centerGap" in center_gap_block
    assert "min-width: 18px" in center_gap_block
    assert "justify-self: start" in channel_block
    assert "text-align: left" in channel_block
    assert "justify-self: end" in unit_block
    assert "font-variant-numeric: tabular-nums" in value_block


def test_shock_setup_reader_uses_wide_structured_rows() -> None:
    histogram_source = Path("ui/src/components/ShockHistogram.tsx").read_text(encoding="utf-8")
    styles = Path("ui/src/styles.css").read_text(encoding="utf-8")

    grid_block = styles.split(".shock-workstation-grid {", 1)[1].split("}", 1)[0]
    body_block = styles.split(".shock-panel-body {", 1)[1].split("}", 1)[0]
    right_body_block = styles.split(".shock-panel.setup-right .shock-panel-body {", 1)[1].split("}", 1)[0]
    field_block = styles.split(".shock-setup-field {", 1)[1].split("}", 1)[0]
    value_block = styles.split(".shock-setup-field strong {", 1)[1].split("}", 1)[0]
    badge_block = styles.split(".shock-setup-recommendation-badge {", 1)[1].split("}", 1)[0]
    add_badge_block = styles.split(".shock-setup-recommendation-badge.add {", 1)[1].split("}", 1)[0]
    hold_badge_block = styles.split(".shock-setup-recommendation-badge.hold {", 1)[1].split("}", 1)[0]

    row_markup = histogram_source.split('className={`shock-setup-field${field.unavailable ? " unavailable" : ""}`}', 1)[1].split("</div>", 1)[0]
    assert row_markup.index('className="shock-setup-label"') < row_markup.index("<strong>{field.value}</strong>")
    assert row_markup.index("<strong>{field.value}</strong>") < row_markup.index("shock-setup-recommendation-badge")

    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in grid_block
    assert "grid-auto-rows: minmax(340px, auto)" in grid_block
    assert "grid-template-columns: minmax(190px, 220px) minmax(0, 1fr)" in body_block
    assert "grid-template-columns: minmax(0, 1fr) minmax(190px, 220px)" in right_body_block
    assert "grid-template-columns: minmax(72px, 1fr) max-content minmax(72px, 92px)" in field_block
    assert "column-gap: 6px" in field_block
    assert "padding: 3px 5px" in field_block
    assert "font-variant-numeric: tabular-nums" in value_block
    assert 'font-feature-settings: "tnum"' in value_block
    assert "text-align: right" in value_block
    assert "min-width: 68px" in badge_block
    assert "height: 18px" in badge_block
    assert "justify-self: stretch" in badge_block
    assert "text-align: center" in badge_block
    assert "rgba(34, 211, 238" in add_badge_block
    assert "rgba(148, 163, 184" in hold_badge_block


def test_shock_histogram_responsive_layout_protects_chart_size() -> None:
    styles = Path("ui/src/styles.css").read_text(encoding="utf-8")

    panel_main_block = styles.split("\n.shock-panel-main {", 1)[1].split("}", 1)[0]
    chart_stage_block = styles.split(".shock-chart-stage {", 1)[1].split("}", 1)[0]
    medium_block = styles.split("@media (max-width: 1280px)", 1)[1].split("@media (max-width: 1180px)", 1)[0]
    compact_block = styles.split("@media (max-width: 1180px)", 1)[1].split("@media (max-width: 980px)", 1)[0]
    narrow_block = styles.split("@media (max-width: 980px)", 1)[1].split("@media (max-width: 860px)", 1)[0]

    assert "min-width: 420px" in panel_main_block
    assert "min-height: 260px" in chart_stage_block
    assert ".shock-panel-body," in medium_block
    assert "grid-template-columns: 1fr" in medium_block
    assert "min-width: 0" in medium_block
    assert "grid-template-columns: repeat(2, minmax(180px, 1fr))" in medium_block
    assert "min-height: 240px" in medium_block
    assert "min-height: 230px" in compact_block
    assert ".shock-workstation-grid" in narrow_block
    assert "grid-template-columns: 1fr" in narrow_block


def test_platform_tab_defaults_event_filter_to_actionable_only() -> None:
    app_source = Path("ui/src/App.tsx").read_text(encoding="utf-8")
    platform_source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")

    assert 'useState<PlatformEventVisibilityMode>("actionable")' in app_source
    assert '<option value="actionable">Actionable</option>' in platform_source
    assert '<option value="proxy">Proxy / Internal</option>' in platform_source
    assert '<option value="all">All</option>' in platform_source


def test_platform_ui_hides_internal_events_by_default_but_keeps_note() -> None:
    rail_source = Path("ui/src/components/PriorityRail.tsx").read_text(encoding="utf-8")
    platform_source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")
    timeline_source = Path("ui/src/components/EventTimeline.tsx").read_text(encoding="utf-8")

    assert "No actionable platform events for this lap." in rail_source
    assert "Internal evidence is still available for analysis." in rail_source
    assert "No actionable platform events shown." in platform_source
    assert "Internal evidence is still preserved for analysis." in platform_source
    assert "Switch to Proxy/Internal to inspect hidden evidence." in platform_source
    assert "filterPlatformEvents" in rail_source
    assert "filterPlatformEvents" in timeline_source
