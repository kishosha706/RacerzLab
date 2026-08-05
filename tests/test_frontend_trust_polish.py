from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_overview_race_call_requires_capability_and_warning_health() -> None:
    overview = _read("ui/src/tabs/OverviewTab.tsx")

    assert 'cache_compatibility.status === "current"' in overview
    assert "capability_summary.lossless_archive_complete" in overview
    assert "capability_summary.warning_channels === 0" in overview
    assert "blockingOverviewWarnings.length === 0" in overview
    assert ': "HOLD"' in overview
    assert 'key: "other", label: "Other data-quality warnings"' in overview


def test_general_scope_cautions_do_not_permanently_block_overview() -> None:
    overview = _read("ui/src/tabs/OverviewTab.tsx")

    assert "short runs cannot support strong tire degradation or cooling conclusions" in overview
    assert "do not overclaim exact aerodynamic drag force" in overview
    assert "NON_BLOCKING_RACE_WARNING_PREFIXES.some" in overview
    assert "Unknown warnings cannot silently earn a Race call." in overview


def test_unknown_future_overview_warning_fails_closed() -> None:
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    classifier = overview.split("function isDecisionBlockingWarning", 1)[1].split("\n}", 1)[0]

    assert "return false" in classifier
    assert "return true" in classifier


def test_session_context_uses_honest_wind_units() -> None:
    context = _read("ui/src/components/RunContextBar.tsx")

    assert "m/s" in context
    assert "* 2.236936" in context
    assert " mph @" not in context
    assert "value * 180 / Math.PI" in context
    assert "% 360 + 360) % 360" in context
    assert "windDirectionDegrees(session.wind_direction)" in context
    assert round(((math.pi * 180 / math.pi) % 360 + 360) % 360) == 180


def test_optional_track_map_confidence_defaults_unknown() -> None:
    track_map = _read("ui/src/tabs/TrackMapTab.tsx")
    styles = _read("ui/src/styles.css")

    assert 'match.match_confidence ?? "unknown"' in track_map
    assert 'match.match_confidence ?? "medium"' not in track_map
    assert '[data-confidence="unknown"]' in styles


def test_empty_and_failed_session_states_offer_recovery() -> None:
    app = _read("ui/src/App.tsx")

    assert "Import the first telemetry run" in app
    assert "Retry session" in app
    assert "Back to sessions" in app
    assert "send logs" not in app.lower()


def test_import_failure_does_not_masquerade_as_session_open_failure() -> None:
    app = _read("ui/src/App.tsx")

    assert "const [sessionOpenError, setSessionOpenError]" in app
    assert "const sessionOpenFailed = Boolean(sessionOpenError)" in app
    assert "const sessionOpenFailed = Boolean(error)" not in app
    assert 'errorScope: "general" | "session_open"' in app
    assert 'error={error}' in app


def test_embedded_analysis_loaders_do_not_use_full_viewport_empty_state() -> None:
    time_surface = _read("ui/src/components/TimeDeltaComparison.tsx")
    engineering_surface = _read("ui/src/components/EngineeringSystemsComparison.tsx")

    assert 'className="analysis-state"' in time_surface
    assert 'className="analysis-state"' in engineering_surface
    assert 'className="empty-state"' not in time_surface
    assert 'className="empty-state"' not in engineering_surface


def test_stint_warning_truncation_discloses_and_reveals_hidden_items() -> None:
    laps = _read("ui/src/tabs/LapsTab.tsx")

    assert "+{stintData.warnings.length - 4} more warnings" in laps
    assert "stintData.warnings.slice(4).map" in laps
