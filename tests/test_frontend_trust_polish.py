from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ordinal_evidence_scores_never_render_as_probability_percentages() -> None:
    score_helper = _read("ui/src/utils/evidenceScore.ts")
    assert "Evidence strength" in score_helper
    assert 'return `${Math.round(bounded * 100)}/100`' in score_helper

    for path in (
        "ui/src/tabs/OverviewTab.tsx",
        "ui/src/components/EvidenceCard.tsx",
        "ui/src/components/DidItWorkCard.tsx",
        "ui/src/components/EngineeringSystemsComparison.tsx",
        "ui/src/components/TimeDeltaComparison.tsx",
        "ui/src/tabs/NotebookTab.tsx",
        "ui/src/utils/exportUtils.ts",
    ):
        source = _read(path)
        assert "% confidence" not in source
        assert "Observation confidence:" not in source

    readme = _read("README.md")
    assert "tire dynamics (slip angles, understeer gradient)" not in readme
    assert "Steering-wheel angle is driver demand" in readme


def test_overview_race_call_requires_capability_and_typed_blocker_health() -> None:
    overview = _read("ui/src/tabs/OverviewTab.tsx")

    assert 'cache_compatibility.status === "current"' in overview
    assert "capability_summary.lossless_archive_complete" in overview
    assert "capability_summary.warning_channels === 0" in overview
    assert "blockingOverviewBlockers.length === 0" in overview
    assert ': "NO FINDING"' in overview
    assert "This overview is observational and does not authorize a setup test." in overview
    assert "begin one small, controlled test" not in overview
    assert 'key: "other", label: "Other data-quality warnings"' in overview


def test_capability_authority_is_bound_to_the_requested_run() -> None:
    app = _read("ui/src/App.tsx")
    types = _read("ui/src/types/telemetry.ts")

    assert "run_id: string" in types.split("export type TelemetryCapabilitiesResponse", 1)[1].split("};", 1)[0]
    assert "capabilityPayload?.run_id === runId" in app
    assert "Telemetry capability identity mismatch" in app
    assert "setTelemetryCapabilities(capabilityMatchesRun ? capabilityPayload : null)" in app


def test_degraded_session_time_clock_stays_archival_and_never_decision_ready() -> None:
    app = _read("ui/src/App.tsx")
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    trust = _read("ui/src/utils/evidenceTrust.ts")
    types = _read("ui/src/types/telemetry.ts")

    assert "telemetryClockDecisionReady(telemetryCapabilities.capability_summary)" in overview
    assert "telemetryClockDecisionReady(" in app
    assert '["qualified", "degraded"].includes' not in app
    assert '["qualified", "degraded"].includes' not in overview
    assert 'summary.qualified_clock_state === "qualified"' in trust
    assert 'summary.qualified_clock_primary === "session_tick"' in trust
    assert "qualified_clock_decision_ready?: boolean" in types
    assert "SessionTime is preserved for archive inspection and corroboration only" in overview


def test_decision_scope_never_depends_on_warning_prose() -> None:
    trust = _read("ui/src/utils/evidenceTrust.ts")

    assert "engineeringBlockerBlocksAny" in trust
    assert "overviewBlockerBlocksDecision" in trust
    assert '["observation", "navigation"]' in trust
    assert "warning.toLowerCase" not in trust
    assert "startsWith(prefix)" not in trust


def test_unknown_future_typed_blocker_fails_closed() -> None:
    trust = _read("ui/src/utils/evidenceTrust.ts")
    validator = trust.split("function engineeringBlockersMatchRun", 1)[1].split(
        "export function engineeringBlockerBlocksAny", 1
    )[0]

    assert "ENGINEERING_BLOCK_TARGETS.has(target)" in validator
    assert "return false" in validator
    assert "identities.has(identity)" in validator


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
    assert "bestUsefulLapMatchesRun(baseBestUsefulLap, runId)" in app
    assert "Cross-run lap rows were withheld" in app
    assert "Cross-run events were withheld" in app
    assert "base.recommendations" not in app
    assert "primary_findings: derivedIdentityMismatch ? []" in app
    assert "crew_chief_summary" not in app
    assert "next_test:" not in app


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


def test_overview_and_inspector_keep_import_observations_non_authorizing() -> None:
    trust = _read("ui/src/utils/evidenceTrust.ts")
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    inspector = _read("ui/src/components/EvidenceInspector.tsx")
    card = _read("ui/src/components/EvidenceCard.tsx")

    assert "telemetryEventIsActionable" in overview
    assert "event.blocker_reasons.length === 0" in trust
    assert "event.source_channels.length > 0" in trust
    assert "recommendationIsActionable" not in trust
    assert "controlled P19 workflow" in overview
    assert "Setup changes are authorized only by the controlled P19 workflow." in inspector
    assert "Evidence only - no setup action is authorized." in card
    assert 'role="button"' not in card
    assert "Open Platform" in card
    assert "Show on map" in card
    assert "getChannelLabel" in card
    assert "getChannelPrecision" in card
