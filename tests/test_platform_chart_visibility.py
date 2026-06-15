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
