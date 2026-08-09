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


def test_capability_authority_is_bound_to_the_requested_run() -> None:
    app = _read("ui/src/App.tsx")
    types = _read("ui/src/types/telemetry.ts")

    assert "run_id: string" in types.split("export type TelemetryCapabilitiesResponse", 1)[1].split("};", 1)[0]
    assert "capabilityPayload?.run_id === runId" in app
    assert "Telemetry capability identity mismatch" in app
    assert "setTelemetryCapabilities(capabilityMatchesRun ? capabilityPayload : null)" in app


def test_general_scope_cautions_do_not_permanently_block_overview() -> None:
    trust = _read("ui/src/utils/evidenceTrust.ts")

    assert "short runs cannot support strong tire degradation or cooling conclusions" in trust
    assert "do not overclaim exact aerodynamic drag force" in trust
    assert "NON_BLOCKING_RACE_WARNING_PREFIXES.some" in trust
    assert "Unknown warnings cannot silently earn a Race call." in trust


def test_unknown_future_overview_warning_fails_closed() -> None:
    trust = _read("ui/src/utils/evidenceTrust.ts")
    classifier = trust.split("function overviewWarningBlocksDecision", 1)[1].split("\n}", 1)[0]

    assert "return false" in classifier
    assert "return true" in classifier


def test_overview_setup_identity_is_shared_and_fails_closed() -> None:
    app = _read("ui/src/App.tsx")
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    trust = _read("ui/src/utils/evidenceTrust.ts")

    assert "snapshot.run_id === runId" in trust
    assert "setupSnapshotMatchesRun(setup, runId)" in app
    assert "Setup snapshot identity mismatch" in app
    assert "setupSnapshotMatchesRun(overview.setup_snapshot, overview.run_id)" in overview


def test_overview_and_shell_require_the_same_current_run_best_useful_lap() -> None:
    app = _read("ui/src/App.tsx")
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    trust = _read("ui/src/utils/evidenceTrust.ts")

    assert "lap.run_id === runId" in trust
    assert "lap.is_complete" in trust
    assert "lap.is_useful" in trust
    assert "Number.isFinite(lap.lap_time)" in trust
    assert "bestUsefulLapMatchesRun(overview.best_useful_lap, overview.run_id)" in app
    assert "bestUsefulLapMatchesRun(overview.best_useful_lap, overview.run_id)" in overview


def test_app_sanitizes_nested_run_payloads_before_any_tab_receives_them() -> None:
    app = _read("ui/src/App.tsx")

    assert "laps.filter((lap) => lap.run_id === runId)" in app
    assert "events.filter((event) => event.run_id === runId)" in app
    assert "base.recommendations.filter((recommendation) => recommendation.run_id === runId)" in app
    assert "bestUsefulLapMatchesRun(baseBestUsefulLap, runId)" in app
    assert "Cross-run lap rows were withheld" in app
    assert "Cross-run events were withheld" in app
    assert "Cross-run recommendations were withheld" in app
    assert "primary_findings: derivedIdentityMismatch ? []" in app
    assert "next_test: derivedIdentityMismatch ? null" in app


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

    assert "+{currentStintData.warnings.length - 4} more warnings" in laps
    assert "currentStintData.warnings.slice(4).map" in laps


def test_overview_and_inspector_fail_closed_on_untrusted_actions() -> None:
    trust = _read("ui/src/utils/evidenceTrust.ts")
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    inspector = _read("ui/src/components/EvidenceInspector.tsx")
    card = _read("ui/src/components/EvidenceCard.tsx")

    assert "telemetryEventIsActionable" in overview
    assert "recommendationIsActionable" in overview
    assert "recommendationIsActionable" in inspector
    assert "event.blocker_reasons.length === 0" in trust
    assert "event.source_channels.length > 0" in trust
    assert "recommendation.blocker_reasons.length > 0" in trust
    assert "recommendation.evidence_event_ids.length === 0" in trust
    assert "No recommendation is shown without supporting evidence." in overview
    assert "No recommendation is shown without supporting evidence." in inspector
    assert "Evidence only - no setup action is authorized." in card
    assert 'role="button"' not in card
    assert "Open Platform" in card
    assert "Show on map" in card
    assert "getChannelLabel" in card
    assert "getChannelPrecision" in card
