from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_setup_tab_no_longer_owns_full_dial_in_panel() -> None:
    setup_tab = (PROJECT_ROOT / "ui/src/tabs/SetupTab.tsx").read_text(encoding="utf-8")
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "analyzeRunDialIn" not in setup_tab
    assert "Crew Chief Dial-In" not in setup_tab
    assert "analyzeRunDialIn" in dial_in_tab
    assert "Crew Chief Dial-In" in dial_in_tab


def test_dial_in_tab_requests_ranked_hypotheses_but_caps_learning_mode_at_three() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "const DIAL_IN_INITIAL_LIMIT = 9" in dial_in_tab
    assert "const SHOW_MORE_STEP = 9" in dial_in_tab
    assert "const DIAL_IN_REQUEST_LIMIT = DIAL_IN_INITIAL_LIMIT + SHOW_MORE_STEP" in dial_in_tab
    assert "const MAX_VISIBLE_UNVERIFIED_HYPOTHESES = 3" in dial_in_tab
    assert "limit: DIAL_IN_REQUEST_LIMIT" in dial_in_tab
    assert "response?.top_swings.slice(0, 1)" in dial_in_tab
    assert "response?.top_swings.slice(1, MAX_VISIBLE_UNVERIFIED_HYPOTHESES)" in dial_in_tab
    assert "include_debug_evidence: false" in dial_in_tab
    assert "Show {nextRevealCount} more setup changes" not in dial_in_tab


def test_dial_in_tab_sends_explicit_decision_context_to_both_server_paths() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    client = (PROJECT_ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")

    assert "selected_zone_start_pct" in dial_in_tab
    assert "selected_zone_end_pct" in dial_in_tab
    assert "selected_zone_label" in dial_in_tab
    assert "selected_phase: selectedPhase || undefined" in dial_in_tab
    assert "objective," in dial_in_tab
    assert "priority," in dial_in_tab
    assert dial_in_tab.count("...decisionContext") >= 3
    assert "& DialInDecisionContext" in client
    assert "export type DialInObjective" in telemetry_types
    assert "export type DialInPriority" in telemetry_types


def test_dial_in_tab_distinguishes_decision_kinds_from_verified_results() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert 'label: "Measurement mission"' in dial_in_tab
    assert 'label: "Exploratory test"' in dial_in_tab
    assert 'label: "Fix recommendation"' in dial_in_tab
    assert 'workflow.quality.verdict === "keep"' in dial_in_tab
    assert "not yet a proven fix" in dial_in_tab
    assert "Mechanism proof" in dial_in_tab
    assert "response.evidence_strength.reason" in dial_in_tab
    assert "Ranking basis:" in dial_in_tab
    assert "workflow?.reproduction_snapshot?.decision_context" in dial_in_tab
    assert "setObjective(context.objective as DialInObjective)" in dial_in_tab
    assert "setPriority(context.priority as DialInPriority)" in dial_in_tab
    assert "displayedDecisionContext.selected_zone_label" in dial_in_tab
    assert "workflowContextMatches" in dial_in_tab
    assert "Decision context changed. Build a new verified plan" in dial_in_tab
    assert 'workflow ? "Build new verified plan"' in dial_in_tab
    assert "workflowBusy || !workflowContextMatches" in dial_in_tab
    assert "current == null ? true : persisted != null" in dial_in_tab
    assert "persistedDecisionContext.selected_lap != null" in dial_in_tab
    assert "setComplaint(workflow.complaint)" in dial_in_tab
    assert "normalizedComplaint === persistedComplaint" in dial_in_tab


def test_dial_in_tab_uses_backend_target_labels() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")

    assert "const TARGET_LABELS" not in dial_in_tab
    assert "garageLeverLabel" in dial_in_tab
    assert "Garage control" in dial_in_tab
    assert "dialin-garage-helper" in dial_in_tab
    assert "validate_with_labels" in dial_in_tab
    assert "swing.undo_if" in dial_in_tab
    assert "validate_with_labels" in telemetry_types
    assert "watch_for_labels" in telemetry_types


def test_dial_in_cards_render_exact_change_this_and_garage_lever() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "change_this: string" in telemetry_types
    assert "garage_lever: string" in telemetry_types
    assert "dialin-change-this" in dial_in_tab
    assert "Make this setup change:" in dial_in_tab
    assert "{swing.change_this}" in dial_in_tab
    assert "{swing.garage_lever}" in dial_in_tab
    assert ".dialin-change-this" in styles
    assert ".dialin-garage-note" in styles


def test_dial_in_tab_uses_direct_setup_change_vocabulary() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "verify whether one specific setup test is justified" in dial_in_tab
    assert "Pick one change. Just one." in dial_in_tab
    assert "Server-verified Test Director" in dial_in_tab
    assert "Ideas awaiting evidence-gated approval" in dial_in_tab
    assert "Other hypotheses" in dial_in_tab
    assert "Expected improvement" in dial_in_tab
    assert "Trade-off" in dial_in_tab
    assert "Why this size" in dial_in_tab
    assert "What this control does" in dial_in_tab
    assert "Related settings to recheck" in dial_in_tab
    assert "Test plan" in dial_in_tab
    assert "Evidence signals" in dial_in_tab
    assert "Keep it if" in dial_in_tab
    assert "Undo it if" in dial_in_tab
    assert "swing.change_size_label" in dial_in_tab

    for vague_phrase in [
        "Feel polish",
        "Balance shift",
        "Possible swings",
        "Best first swings",
        "Other possible swings",
        "setup swings to test",
        "What to watch for",
        "Your Next Test",
    ]:
        assert vague_phrase not in dial_in_tab
