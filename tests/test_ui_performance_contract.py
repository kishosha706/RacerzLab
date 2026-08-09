from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_heavy_cockpit_surfaces_are_loaded_on_demand() -> None:
    app = _read("ui/src/App.tsx")

    for surface in [
        "OverviewTab",
        "PriorityRail",
        "EvidenceInspector",
        "EventTimeline",
        "TrackMapOverlay",
        "CompareBasket",
    ]:
        assert f"const {surface} = lazy" in app

    assert "{mapOverlayOpen && (" in app
    assert "{hasCompareBasketItems && (" in app
    assert "priorityRailExpanded ? (" in app
    assert "inspectorOpen ? (" in app
    assert "onPointerEnter={() => preloadWorkspace(key)}" in app


def test_transient_chart_cursor_does_not_re_render_selection_consumers() -> None:
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")

    assert "useSyncExternalStore" in selection
    assert "publishCursor" in selection
    assert 'type: "SET_HOVER"' not in selection
    assert 'type: "SET_PLAYBACK_ACTIVE"' not in selection
    assert "useTelemetryCursor()" in platform
    assert "useTelemetryCursor()" in overlay
    assert "selection.hoverLapPct" not in platform
    assert "selection.hoverLapPct" not in overlay


def test_zoom_updates_do_not_rebuild_all_chart_series_or_closed_shell() -> None:
    app = _read("ui/src/App.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "    visibleZoomRange,\n    xs,\n  ]);" not in platform
    assert "const chartZoomRange = visibleZoomRange ?? zoomRangeRef.current;" in platform
    assert "if (mapOverlayOpenRef.current) setMapOverlayZoomRange(nextRange);" in app
    assert "node.style.height = `${initialHeight}px`;\n    node.style.minHeight = `${initialHeight}px`;\n    const chart = echarts.init" in platform


def test_launch_art_stays_below_optimized_weight_budget() -> None:
    banner = ROOT / "ui/src/assets/racerzlab-banner-1920.jpg"

    assert banner.stat().st_size < 500_000
