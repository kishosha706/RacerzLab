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
