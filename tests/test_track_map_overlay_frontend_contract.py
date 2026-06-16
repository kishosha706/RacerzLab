from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_track_map_is_not_a_top_level_workspace_tab() -> None:
    app = _read("ui/src/App.tsx")

    assert '["map", "Track Map"' not in app
    assert "TrackMapTab = lazy" not in app
    assert "<TrackMapTab" not in app
    assert "TrackMapOverlay" in app
    assert "Toggle Map Overlay" in app


def test_stale_track_map_workspace_normalizes_to_overview() -> None:
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")

    assert '"map"' in selection
    assert 'if (workspace === "map") return "overview";' in selection
    assert "normalizeWorkspace(saved as Workspace)" in selection
    assert "normalizeWorkspace(action.workspace)" in selection


def test_platform_toolbar_drives_chart_linked_map_overlay() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "onToggleMapOverlay" in platform
    assert "Map Overlay" in platform
    assert "setHover(" in platform
    assert 'valueAt(trace, "lap_dist_pct_100", nextIndex)' in platform
    assert "onMapOverlayZoomRangeChange?.(nextRange)" in platform
    assert "onMapOverlayZoomRangeChange?.(null)" in platform
    assert 'focusEvidence(buildCardEvidence(), "map")' not in platform


def test_laps_toolbar_exposes_map_overlay_without_map_workspace_navigation() -> None:
    laps = _read("ui/src/tabs/LapsTab.tsx")

    assert "onToggleMapOverlay" in laps
    assert 'aria-label="Show track map overlay"' in laps
    assert "Map Overlay" in laps
    assert 'focusWindowEvidence(item.window, "map")' not in laps
    assert 'focusLapEvidence(item.lap, "map")' not in laps


def test_overlay_uses_local_track_map_package_and_no_external_map_api() -> None:
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")
    client = _read("ui/src/api/client.ts")

    assert "fetchRunTrackMapPackage" in overlay
    assert "/track-map-package" in client
    assert "Track map unavailable" in overlay
    assert "No local map data is available for this run." in overlay
    assert "Chart inspection still works." in overlay
    forbidden = ["mapbox", "google.maps", "leaflet", "openstreetmap", "tile.openstreetmap", "cdn"]
    assert not any(token in overlay.lower() for token in forbidden)


def test_overlay_quiet_defaults_hide_labels_events_and_legend() -> None:
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")
    styles = _read("ui/src/styles.css")

    assert "const [showLabels, setShowLabels] = useState(false)" in overlay
    assert "const [showEvents, setShowEvents] = useState(false)" in overlay
    assert "showLabels && sectionLabels.map" in overlay
    assert "showEvents && visibleEventMarkers.map" in overlay
    assert "track-map-overlay-legend" not in overlay
    assert "track-map-overlay-legend" not in styles
    assert "TURN 1" not in overlay
    assert "TURN 2" not in overlay


def test_overlay_renders_cursor_selected_event_and_zoom_window_layers() -> None:
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")

    assert "track-map-overlay-cursor-dot" in overlay
    assert "track-map-overlay-selected-dot" in overlay
    assert "track-map-overlay-window" in overlay
    assert "Current chart cursor marker" in overlay
    assert "Current chart zoom window" in overlay


def test_overlay_optional_events_respect_platform_visibility_filter() -> None:
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")

    assert "filterPlatformEvents(platformEvents, eventVisibilityMode)" in overlay
    assert "!isClearPlatformDiagnostic(event)" in overlay
    assert "visiblePlatformEventIds.has(overlay.source_id)" in overlay


def test_overlay_has_drag_resize_and_opacity_affordances() -> None:
    overlay = _read("ui/src/components/TrackMapOverlay.tsx")
    styles = _read("ui/src/styles.css")

    assert "beginOverlayInteraction(\"drag\", event)" in overlay
    assert "beginOverlayInteraction(\"resize\", event)" in overlay
    assert 'aria-label="Drag map overlay"' in overlay
    assert 'aria-label="Resize map overlay"' in overlay
    assert 'aria-label="Map overlay opacity"' in overlay
    assert "OVERLAY_MIN_WIDTH = 300" in overlay
    assert "OVERLAY_MIN_HEIGHT = 240" in overlay
    assert "--track-map-overlay-opacity" in styles
    assert "rgba(11, 18, 27, var(--track-map-overlay-opacity" in styles
    assert "cursor: grab" in styles
    assert "cursor: nwse-resize" in styles


def test_track_map_backend_route_remains_available() -> None:
    routes = _read("api/routes_track_map.py")

    assert '@router.get("/runs/{run_id}/track-map-package")' in routes
    assert '@router.get("/track-maps")' in routes
