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
    assert 'detail.title ?? fallback' in client
    assert 'detail.title ?? "Import failed"' not in client
    assert "No completed run was created." in app


def test_frontend_waits_for_local_engine_health_before_sessions_load() -> None:
    app = _read("ui/src/App.tsx")
    client = _read("ui/src/api/client.ts")

    assert "fetchHealth" in app
    assert "engineStatus" in app
    assert "Starting RacerZLab" in app
    assert "Connecting the decision cockpit to your local analysis engine." in app
    assert "Local engine failed to start." in app
    assert "Close and reopen RacerZLab, then retry." in app
    assert "Retry engine check" in app
    assert "send logs" not in app.lower()
    assert 'if (engineStatus === "starting")' in app
    assert 'if (engineStatus === "failed")' in app
    gated_block = app.split('if (engineStatus === "starting")', 1)[1].split('if (!sessionId)', 1)[0]
    assert "StartupScreen" not in gated_block
    assert "return <StartupScreen onSessionSelected={handleSessionSelected} />;" in app
    assert 'requestJson<HealthResponse>("/api/health"' in client


def test_packaged_startup_error_hides_dev_backend_command() -> None:
    app = _read("ui/src/App.tsx")
    startup = _read("ui/src/components/StartupScreen.tsx")

    assert "isTauri" in app
    assert "!desktop" in app
    assert "isBrowser" in startup
    assert "browser &&" in startup
    assert "Start backend:" in startup
    assert "python -m uvicorn api.main:app --reload" in startup
    assert "Start backend:" not in app.split("{!desktop &&", 1)[0]


def test_import_panel_hides_advanced_recent_folder_scan_and_manual_track_maps() -> None:
    panel = _read("ui/src/components/ImportPanel.tsx")

    assert "Choose run file" in panel
    assert "Bring in the next run" in panel
    assert "Local only" in panel
    assert "Decode archive" in panel
    assert "Qualify evidence" in panel
    assert "Open cockpit" in panel
    assert "Advanced" not in panel
    assert "Import Debug" not in panel
    assert "ImportDebugPanel" not in panel
    assert "Recent Telemetry Files" not in panel
    assert "Recent Track Maps" not in panel
    assert "Scan Telemetry Folder" not in panel
    assert "Review + Import Latest .ibt" not in panel
    assert "Manage Track Maps" not in panel
    assert "handleRecentClick" not in panel
    assert "handleScanFolder" not in panel
    assert "handleNativeMapPick" not in panel


def test_duplicate_import_ui_surfaces_existing_run_updated() -> None:
    backend = _read("racelab_engine/services/import_service.py")
    route = _read("api/routes_imports.py")
    app = _read("ui/src/App.tsx")

    assert "Existing run updated." in backend
    assert "Duplicate telemetry detected - updated the existing run record." in backend
    assert "existing_run_updated" in route
    assert "Same recording reused. Existing telemetry source and artifacts were updated in place." in app


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
    assert "Recorded garage context is unavailable until a setup snapshot is captured." in setup
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
