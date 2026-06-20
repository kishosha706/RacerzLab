from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_failed_import_ui_shows_user_safe_recovery_copy() -> None:
    panel = _read("ui/src/components/ImportPanel.tsx")
    client = _read("ui/src/api/client.ts")
    app = _read("ui/src/App.tsx")

    assert "ImportRecoveryMessage" in panel
    assert "The telemetry file could not be processed." in panel
    assert "No completed run was created." in panel
    assert "Try importing again, or choose a different .ibt file." in panel
    assert "Technical detail" in panel
    assert "errorMessageFromResponseText" in client
    assert "No completed run was created." in app


def test_duplicate_import_ui_surfaces_existing_run_updated() -> None:
    backend = _read("racelab_engine/services/import_service.py")
    route = _read("api/routes_imports.py")
    app = _read("ui/src/App.tsx")

    assert "Existing run updated." in backend
    assert "Duplicate telemetry detected - updated the existing run record." in backend
    assert "existing_run_updated" in route
    assert "Existing run updated. Duplicate telemetry detected - updated the existing run record." in app


def test_stale_selection_clears_with_calm_status_copy() -> None:
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")
    app = _read("ui/src/App.tsx")

    assert '"VALIDATE_RUN_IDS"' in selection
    assert "Selection cleared because the active session changed." in app
    assert "Choose a run or stint from the current session." in app


def test_missing_setup_snapshot_recovery_copy_is_visible() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")
    dial_in = _read("ui/src/tabs/DialInTab.tsx")

    assert "Setup snapshot unavailable." in setup
    assert "Garage-specific recommendations are limited until a setup snapshot is available." in setup
    assert "Import a telemetry file with setup data or attach a setup snapshot if supported." in setup
    assert "Setup snapshot unavailable." in dial_in
    assert "Dial-In will stay conservative" in dial_in


def test_missing_channel_states_are_unavailable_not_zero() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    inspector = _read("ui/src/components/EvidenceInspector.tsx")

    assert "Shock movement telemetry is unavailable for this run." in platform
    assert 'className="platform-risk-strip"' not in platform
    assert "Missing telemetry remains unavailable, never safe or zero." in platform
    assert "channel.missing_status" in inspector


def test_short_run_and_csv_missing_optional_fields_are_honest() -> None:
    laps = _read("ui/src/tabs/LapsTab.tsx")

    assert 'return value == null || Number.isNaN(value) ? "-" : value.toFixed(digits);' in laps
    assert 'if (value == null) return "";' in laps
    assert "Need 50/60 valid laps for 50/60-lap averages." in laps
    assert "Some optional fields were unavailable and exported blank." in laps
    assert '{avg != null ? formatTime(avg) : "\\u2014"}' in laps


def test_no_actionable_platform_events_state_explains_hidden_evidence() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert "No actionable platform events shown." in platform
    assert "Internal evidence is still preserved for analysis." in platform
    assert "Switch to Proxy/Internal to inspect hidden evidence." in platform
