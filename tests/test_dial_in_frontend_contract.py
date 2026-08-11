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


def test_dial_in_resumes_only_current_run_or_explicit_session_workflows() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    resume_effect = dial_in_tab[
        dial_in_tab.index("void fetchControlledWorkflows(false).then"):
        dial_in_tab.index("}).catch", dial_in_tab.index("void fetchControlledWorkflows(false).then"))
    ]

    assert "touchesRun(item, currentRun)" in resume_effect
    assert "const directlyRelatedActiveTest" in resume_effect
    assert "const activeRelated = related.find(isActive);" in resume_effect
    assert "window.sessionStorage.getItem(workflowHandoffStorageKey)" in resume_effect
    assert "item.workflow_id === workflowId" in resume_effect
    assert "touchesRun(item, explicitScope)" in resume_effect
    assert "const activeTestInScope = explicitScope.has(overview.run_id)" in resume_effect
    assert 'item.packet.decision === "test"' in resume_effect
    assert "const nextWorkflow = directlyRelatedActiveTest" in resume_effect
    assert "?? handedOff" in resume_effect
    assert "?? activeTestInScope" in resume_effect
    assert "setWorkflow(nextWorkflow ?? null);" in resume_effect


def test_dial_in_tab_distinguishes_decision_kinds_from_verified_results() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert 'label: "Measurement mission"' in dial_in_tab
    assert 'label: "Exploratory test"' in dial_in_tab
    assert 'label: "Controlled result"' in dial_in_tab
    assert "workflow.quality.verdict" not in dial_in_tab
    assert "The workflow response itself cannot publish a target or Keep/Undo verdict." in dial_in_tab
    assert "make the server re-derive the exact current-session P19 outcome" in dial_in_tab
    assert "not yet a proven fix" in dial_in_tab
    assert "Mechanism proof" in dial_in_tab
    assert "response.evidence_strength.reason" in dial_in_tab
    assert "Ranking basis:" in dial_in_tab
    assert "readCompleteDecisionContext(workflow)" in dial_in_tab
    assert "setObjective(context.objective as DialInObjective)" in dial_in_tab
    assert "setPriority(context.priority as DialInPriority)" in dial_in_tab
    assert "displayedDecisionContext.selected_zone_label" in dial_in_tab
    assert "workflowContextMatches" in dial_in_tab
    assert "Decision context changed. Build a new verified plan" in dial_in_tab
    assert 'workflow ? "Build new verified plan"' in dial_in_tab
    assert "workflowBusy || !workflowContextMatches" in dial_in_tab
    assert "if (!persistedDecisionContext) return false" in dial_in_tab
    assert "persistedDecisionContext.selected_lap === (selectedLapForRequest ?? null)" in dial_in_tab
    assert "persistedDecisionContext.lap_scope === requestedLapScope" in dial_in_tab
    assert "setComplaint(workflow.complaint)" in dial_in_tab
    assert "normalizedComplaint === persistedComplaint" in dial_in_tab


def test_dial_in_tab_uses_backend_hypothesis_labels() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")

    assert "const TARGET_LABELS" not in dial_in_tab
    assert "garageLeverLabel" in dial_in_tab
    assert "Candidate control area" in dial_in_tab
    assert "dialin-garage-helper" in dial_in_tab
    assert "validate_with_labels" in dial_in_tab
    assert "swing.undo_if" not in dial_in_tab
    assert "validate_with_labels" in telemetry_types
    assert "watch_for_labels" in telemetry_types


def test_dial_in_cards_render_non_authorizing_hypotheses_only() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "mechanism_to_verify: string" in telemetry_types
    assert "candidate_control_label: string" in telemetry_types
    assert "change_this: string" not in telemetry_types
    assert "garage_lever: string" not in telemetry_types
    assert "proposed_value_label" not in telemetry_types
    assert "direction_sign" not in telemetry_types
    assert "dialin-change-this" in dial_in_tab
    assert "Hypothesis only:" in dial_in_tab
    assert "Make this setup change:" not in dial_in_tab
    assert "targetReady" not in dial_in_tab
    assert "swing.proposed_value_label" not in dial_in_tab
    assert "swing.keep_if" not in dial_in_tab
    assert "swing.undo_if" not in dial_in_tab
    assert "Needed before a setup test" in dial_in_tab
    assert "{swing.mechanism_to_verify}" in dial_in_tab
    assert "{swing.candidate_control_label}" in dial_in_tab
    assert "Only the controlled P19 workflow can expose an exact target" in dial_in_tab
    assert ".dialin-change-this" in styles
    assert ".dialin-garage-note" in styles


def test_resumed_and_fresh_workflows_keep_the_complete_test_protocol() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    # Both entry paths use the same complete, read-only protocol renderers so the
    # resumed and freshly built workflow cannot drift apart as the UX evolves.
    assert "function MeasurementMissionPanel" in dial_in_tab
    assert dial_in_tab.count("<MeasurementMissionPanel") == 2
    assert "mission.procedure.map" in dial_in_tab
    assert "mission.acceptance_thresholds.join" in dial_in_tab
    assert "mission.stop_rule" in dial_in_tab

    assert "function ControlledWorkflowProgress" in dial_in_tab
    assert dial_in_tab.count("<ControlledWorkflowProgress") == 2
    assert "test.stages.map" in dial_in_tab
    assert "workflow.stage_run_ids[stage.stage]" in dial_in_tab
    assert "workflow.stage_eligible_lap_numbers?.[stage.stage]" in dial_in_tab
    assert dial_in_tab.count("primary_test.rollback_rule") == 2
    assert dial_in_tab.count("primary_test.stop_rule") == 2
    assert "stage.warmup_laps" in dial_in_tab
    assert "stage.required_flying_laps" in dial_in_tab
    assert "stage.setup_instruction" in dial_in_tab
    assert "stage.purpose" in dial_in_tab
    assert 'role="list" aria-label="A B A2 controlled-test checklist"' in dial_in_tab
    assert 'aria-current={current ? "step" : undefined}' in dial_in_tab


def test_dial_in_tab_separates_hypotheses_from_controlled_setup_authority() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "verify whether one specific setup test is justified" in dial_in_tab
    assert "Pick one change. Just one." in dial_in_tab
    assert "Server-verified Test Director" in dial_in_tab
    assert "Ideas awaiting evidence-gated approval" in dial_in_tab
    assert "Other hypotheses" in dial_in_tab
    assert "Mechanism to verify" in dial_in_tab
    assert "Counter-effect to watch" in dial_in_tab
    assert "Needed before a setup test" in dial_in_tab
    assert "Authority boundary" in dial_in_tab
    assert "swing.control_expectation" not in dial_in_tab
    assert "swing.control_guardrail" not in dial_in_tab
    assert "swing.change_size_label" not in dial_in_tab
    assert "swing.keep_if" not in dial_in_tab
    assert "swing.undo_if" not in dial_in_tab

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


def test_dial_in_uses_quick_symptoms_and_progressive_diagnosis_controls() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "const SYMPTOM_PRESETS" in dial_in_tab
    assert 'aria-label="Common driver symptoms"' in dial_in_tab
    assert "chooseSymptomPreset" in dial_in_tab
    assert "aria-pressed=" in dial_in_tab
    assert "Refine diagnosis" in dial_in_tab
    assert 'selection.selectedMode === "learning" || advancedOpen' in dial_in_tab
    assert 'aria-label="Next action"' in dial_in_tab
    assert "dialin-decision-first" in dial_in_tab
    assert "Advisory only" in dial_in_tab
    assert ">Read-only<" not in dial_in_tab
    assert ".dialin-preset-block" in styles
    assert ".dialin-advanced-context" in styles
    assert ".dialin-decision-first" in styles


def test_dial_in_never_sends_a_stale_compare_baseline() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "!basket.baseline.stale" in dial_in_tab
    assert "baseline_run_id: usableBaseline" in dial_in_tab


def test_dial_in_enforces_one_active_controlled_test_with_confirmed_abandon() -> None:
    dial_in = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    client = (PROJECT_ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "cancelControlledWorkflow" in dial_in
    assert 'workflow?.packet.decision === "test"' in dial_in
    assert 'workflow.status !== "scored"' in dial_in
    assert 'workflow.status !== "cancelled"' in dial_in

    submit = dial_in.split("const submitDialIn = useCallback", 1)[1].split(
        "const clearDialIn",
        1,
    )[0]
    build = dial_in.split("const buildVerifiedWorkflow = useCallback", 1)[1].split(
        "const nextWorkflowStage",
        1,
    )[0]
    assert "if (!overview || !sessionId || !workflowCatalogReady || activeWorkflow || workflowAuthorityBlocked) return" in submit
    assert "startControlledWorkflow" in submit
    assert "if (!overview || !sessionId || !workflowCatalogReady || workflowBusy || activeWorkflow || workflowAuthorityBlocked) return" in build
    assert "session_id: sessionId" in submit
    assert "session_id: sessionId" in build
    assert "if (workflowResult.status === \"rejected\")" in submit
    assert "setResponse(dialResponse)" in submit
    assert "startControlledWorkflow" in build
    assert "&& workflowCatalogReady" in dial_in
    assert "&& complaint.trim().length > 0" in dial_in
    assert "&& !loading" in dial_in
    assert "&& !activeWorkflow" in dial_in
    assert "&& !workflowAuthorityBlocked" in dial_in
    assert "setWorkflowCatalogReady(false)" in dial_in
    assert "setWorkflowCatalogReady(true)" in dial_in
    assert "Checking test status" in dial_in

    clear = dial_in.split("const clearDialIn = useCallback", 1)[1].split(
        "const buildVerifiedWorkflow",
        1,
    )[0]
    assert 'setComplaint(activeWorkflow ? workflow?.complaint ?? "" : "")' in clear
    assert "if (!activeWorkflow) setWorkflow(null)" in clear
    assert "if (workflowBusy || !workflowCatalogReady) return" in clear

    cancel = dial_in.split("const abandonActiveTest = useCallback", 1)[1].split(
        "const recordCurrentRun",
        1,
    )[0]
    assert "if (!activeWorkflow || !workflow || workflowBusy) return" in cancel
    assert "cancelControlledWorkflow(workflowId)" in cancel
    assert "cancelledWorkflow.workflow_id !== workflowId" in cancel
    assert 'cancelledWorkflow.status !== "cancelled"' in cancel
    assert "currentWorkflowIdRef.current !== workflowId" in cancel
    assert "setWorkflow(cancelledWorkflow)" in cancel
    assert "setResponse(null)" in cancel

    for user_contract in (
        "Finish its remaining A/B/A2 stages before checking or building another plan.",
        "Abandon workflow",
        "Confirm abandon",
        "Keep workflow",
        "cancelled audit record",
        "no result was admitted as setup learning",
    ):
        assert user_contract in dial_in
    assert 'role="group" aria-label="Confirm abandoning selected workflow"' in dial_in
    assert 'workflow.status === "a2_recorded"' in dial_in
    assert ".dialin-tab .dialin-active-test-guard" in styles

    assert "export function cancelControlledWorkflow(workflowId: string)" in client
    assert "/api/engineering/workflows/${encodeURIComponent(workflowId)}/cancel" in client
    assert '{ method: "POST" }' in client
    assert "/api/engineering/test-director/score" not in client
    assert "/score`" in client


def test_dial_in_workflow_catalog_failure_has_an_in_tab_retry() -> None:
    dial_in = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "workflowCatalogRetryToken" in dial_in
    assert "setWorkflowCatalogRetryToken((token) => token + 1)" in dial_in
    assert "Retry workflow status" in dial_in
    assert "workflowCatalogRetryToken, workflowHandoffStorageKey" in dial_in
