from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_platform_trace_failure_states_broadcast_no_call_and_recovery() -> None:
    platform = _read("ui/src/tabs/PlatformTab.tsx")

    assert 'data-state="error" data-diagnostic-state="unavailable" data-authority="withheld"' in platform
    assert 'data-state="loading" data-diagnostic-state="loading" data-authority="withheld"' in platform
    assert 'data-state="blocked" data-diagnostic-state="unavailable" data-authority="withheld"' in platform
    assert "Old platform evidence is cleared while this exact run and lap load." in platform
    assert "No usable physical-position samples were returned" in platform
    assert "Explain evidence gap" in platform
    assert "Retry trace" in platform


def test_setup_broadcast_separates_recorded_values_from_action_authority() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    assert 'className="tab-decision-broadcast setup-decision-broadcast"' in setup
    assert 'selectedEvent ? evidenceScope : "Current run - recorded setup snapshot"' in setup
    assert "const evidenceLap = selectedEvent?.lap_number ?? null" in setup
    assert "const evidencePct = selectedEvent?.lap_pct_peak ?? null" in setup
    assert 'selectedEvent ? evidenceScope : "Current run - recorded setup snapshot"' in setup
    assert "const evidenceLap = selectedEvent?.lap_number ?? null" in setup
    assert "const evidencePct = selectedEvent?.lap_pct_peak ?? null" in setup
    assert 'data-diagnostic-state={setupDecisionState}' in setup
    assert 'data-authority="withheld"' in setup
    assert "These are recorded values, not a recommendation." in setup
    assert "No setup change is authorized by this tab." in setup
    assert "exact targets remain behind Dial-In's server-verified one-change workflow" in setup
    assert "const hasQualifiedEvidenceLink = Boolean(" in setup
    qualified = setup.split("const hasQualifiedEvidenceLink = Boolean(", 1)[1].split(");", 1)[0]
    assert "selectedEvent?.trusted_overview_event" in qualified
    assert "selectedEvent.valid_for_tuning" in qualified
    assert "relevantSetupKeys.size > 0" in qualified
    assert "Validate one change" in setup


def test_setup_handoff_and_baseline_identity_fail_closed() -> None:
    setup = _read("ui/src/tabs/SetupTab.tsx")

    assert "overview.setup_snapshot.run_id !== overview.run_id" in setup
    assert "setupIdentityMismatch ? null : overview.setup_snapshot" in setup
    assert "nextSetup.run_id !== baselineRunId" in setup
    assert "Baseline setup identity did not match the selected run." in setup

    handoff = setup.split(
        'window.sessionStorage.getItem("racelab_setup_evidence_focus")', 1
    )[1].split("} catch", 1)[0]
    assert "handoff.run_id !== overview.run_id || handoff.event_id !== selection.selectedEventId" in handoff
    assert "valid_for_tuning: false" in handoff
    assert "trusted_overview_event: false" in handoff

    assert 'setWorkspace("platform_trace", "setup_table")' in setup
    assert 'setWorkspace("engineer", "setup_table")' in setup
    assert 'setWorkspace("dial_in", "setup_table")' in setup
    assert "Trace evidence" in setup
    assert "Ask Engineer" in setup
    assert "Show exact location" in setup
