from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_smarter_report_fields_are_optional_and_structurally_typed() -> None:
    source = _read("ui/src/types/intelligence.ts")

    for field in (
        "opportunity_signature",
        "mechanism_observations",
        "session_ledger",
        "hypothesis_lifecycle",
        "next_trustworthy_move",
        "test_preflight",
        "driver_focus",
        "anomalies",
        "measurement_debt",
        "telemetry_health",
    ):
        assert f"{field}?:" in source

    for contract in (
        "IntelligenceNextTrustworthyMove",
        "IntelligenceTestPreflight",
        "IntelligenceMeasurementDebt",
        "IntelligenceOpportunitySignature",
        "IntelligenceMechanismObservationReport",
        "IntelligenceDriverFocus",
        "IntelligenceAnomalyReport",
        "IntelligenceSessionLedger",
        "IntelligenceHypothesisLifecycle",
    ):
        assert f"export type {contract}" in source

    assert 'authority: "navigation_only" | "setup_authorized"' in source
    assert "workflow_id?: string | null" in source
    assert "workflow_updated_at?: string | null" in source
    assert "control_key?: string | null" in source
    assert 'authority: "observation_only"' in source
    assert 'authority: "driver_coaching_only"' in source
    assert "setup_authorized: false" in source
    assert "causal_claim: false" in source


def test_next_move_navigation_fails_closed_on_identity_scope_and_authority() -> None:
    helper = _read("ui/src/utils/intelligenceNavigation.ts")
    app = _read("ui/src/App.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert "move.run_id !== runId" in helper
    assert "workflowRevisionIsCanonical" in helper
    assert "moveRevision.workflowId !== expectedWorkflow.workflowId" in helper
    assert "moveRevision.workflowUpdatedAt !== expectedWorkflow.workflowUpdatedAt" in helper
    assert "!intelligenceWorkspaceTarget(move.workspace)" in helper
    assert "!intelligenceMoveScope(move)" in helper
    assert "move.window_start_lap > move.window_end_lap" in helper
    assert "move.lap_number < move.window_start_lap" in helper
    assert "move.lap_pct_start >= move.lap_pct_end" in helper
    assert "!positiveInteger(move.lap_number)" in helper
    assert 'move.authority === "navigation_only"' in helper
    assert 'move.kind === "controlled_test"' in helper
    assert 'move.workspace === "dial_in"' in helper
    assert "move.source_event_ids.length > 0" in helper
    assert "move.blocker_reasons.length === 0" in helper

    assert "report.run_id === requestedRunId" in app
    assert "(report.session_id ?? null) === requestedSessionId" in app
    assert 'report.next_trustworthy_move?.authority === "navigation_only"' in app
    assert 'data-authority={currentIntelligenceShellMove.authority}' in app
    assert 'data-scope={intelligenceShellScope.kind}' in app
    assert "Opens the evidence view only" in app
    assert "openIntelligenceShellMove" in app
    assert "focusEvidence({" in app

    assert "setupActionAuthorized={actionAuthorized}" in engineer
    assert "authorizedSetupAction={authorizedSetupAction}" in engineer
    assert "workflowRevision={workflowRevision}" in engineer
    assert "openNextTrustworthyMove" in engineer
    assert 'selectionSource: "engineer"' in engineer
    assert "eventId: null" in engineer
    assert "zoneId: null" in engineer
    assert 'zoneLabel: scope.pctStart != null ? "Server-ranked window" : null' in engineer
    assert "zoneStartPct: scope.pctStart" in engineer
    assert "channelId: null" in engineer


def test_shell_next_move_refreshes_on_exact_controlled_workflow_revision() -> None:
    app = _read("ui/src/App.tsx")

    request_key = app.split("const intelligenceShellRequestKey = JSON.stringify({", 1)[1].split(
        "});",
        1,
    )[0]
    assert "session_run_scope: controlledWorkflowScopeKey" in request_key
    assert "selected_lap: selection.selectedLap ?? null" in request_key
    assert 'selected_lap_scope: selection.selectedLapScope ?? "unknown"' in request_key
    assert "selected_lap_window_start: selection.selectedLapWindowStart ?? null" in request_key
    assert "selected_lap_window_end: selection.selectedLapWindowEnd ?? null" in request_key
    assert "selected_representative_lap: selection.selectedRepresentativeLap ?? null" in request_key
    assert "guidance_workflow_id: currentGuidanceWorkflow?.workflow_id ?? null" in request_key
    assert "guidance_workflow_status: currentGuidanceWorkflow?.status ?? null" in request_key
    assert "guidance_workflow_updated_at: currentGuidanceWorkflowUpdatedAt" in request_key
    assert "active_workflow_ambiguous: currentControlledWorkflowAmbiguous" in request_key

    updated_at = app.split("function controlledWorkflowUpdatedAt", 1)[1].split(
        "function sessionPayloadMatchesRequest",
        1,
    )[0]
    assert "updated_at?: unknown" in updated_at
    assert 'typeof value === "string"' in updated_at
    assert "value.trim() === value" in updated_at

    # A workflow or selected-lap revision invalidates both report readiness and
    # the published move in the observing render. Late responses cannot publish
    # across request identities.
    assert "intelligenceShellReportState.requestKey === intelligenceShellRequestKey" in app
    assert 'currentIntelligenceShellStatus === "ready"' in app
    effect = app.split("const requestSeq = ++intelligenceShellRequestSeqRef.current", 1)[1].split(
        "useEffect(() => {\n    let cancelled = false;",
        1,
    )[0]
    assert "const requestKey = intelligenceShellRequestKey" in effect
    assert "setIntelligenceShellReportState({" in effect
    assert 'status: intelligenceShellCanLoad ? "checking" : "idle"' in effect
    assert 'status: "ready", move, error: null' in effect
    assert 'status: "error"' in effect
    assert "move: null" in effect
    assert "requestSeq !== intelligenceShellRequestSeqRef.current" in effect
    assert "refreshKey: requestKey" in effect
    assert "workflowId: currentGuidanceWorkflow?.workflow_id ?? null" in effect
    assert "workflowUpdatedAt: currentGuidanceWorkflowUpdatedAt" in effect
    for dependency in (
        "currentGuidanceWorkflow?.workflow_id",
        "currentGuidanceWorkflowUpdatedAt",
        "currentSession?.session_id",
        "intelligenceShellRequestKey",
        "overview?.run_id",
        "sessionId",
    ):
        assert dependency in effect

    workflow_effect = app.split("const requestSeq = ++controlledWorkflowRequestSeqRef.current", 1)[1].split(
        "const requestSeq = ++intelligenceShellRequestSeqRef.current",
        1,
    )[0]
    assert "fetchControlledWorkflowCatalog(" in workflow_effect
    assert "fetchControlledWorkflow(item.workflow_id)" in workflow_effect
    assert "detailsByRevision" in workflow_effect
    assert "revision_sha256" in workflow_effect
    assert "const refreshTimer = window.setInterval" in workflow_effect
    assert 'selection.selectedWorkspace === "dial_in"' not in workflow_effect


def test_engineer_shell_review_waits_for_exact_report_readiness() -> None:
    app = _read("ui/src/App.tsx")

    assert 'type IntelligenceShellReportStatus = "idle" | "checking" | "ready" | "error"' in app
    assert "const intelligenceShellStateOwnsRequest" in app
    assert 'intelligenceShellStateOwnsRequest ? intelligenceShellReportState.status : "checking"' in app
    assert "const currentIntelligenceShellError" in app

    signal = app.split("engineer: currentControlledWorkflowAmbiguous", 1)[1].split(
        "laps: overviewBlockingWarnings.length",
        1,
    )[0]
    checking = 'currentIntelligenceShellStatus === "checking" || currentIntelligenceShellStatus === "idle"'
    failure = 'currentIntelligenceShellStatus === "error"'
    review = 'short: "Review"'
    assert checking in signal
    assert 'short: "Checking"' in signal
    assert "current run and lap scope" in signal
    assert failure in signal
    assert 'short: "Unavailable"' in signal
    assert "Open Engineer and retry the current scope" in signal
    assert review in signal
    assert signal.index(checking) < signal.index(review)
    assert signal.index(failure) < signal.index(review)

    effect = app.split("const requestSeq = ++intelligenceShellRequestSeqRef.current", 1)[1].split(
        "useEffect(() => {\n    let cancelled = false;",
        1,
    )[0]
    assert "if (!exactReportScope)" in effect
    assert "different run or session" in effect
    assert 'setIntelligenceShellReportState({ requestKey, status: "ready", move, error: null })' in effect


def test_smarter_cards_separate_observation_coaching_navigation_and_test_authority() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    for label in (
        "Next trustworthy move",
        "Repeatable opportunity",
        "Typed mechanism evidence",
        "Driver repeatability",
        "Same-setup anomaly envelope",
        "Measurement debt",
        "Controlled-test preflight",
        "Session engineering ledger",
        "Controlled hypothesis memory",
        "Cross-run telemetry health",
    ):
        assert label in cards

    assert "Observation only" in cards
    assert "Coaching only" in cards
    assert "Navigation only" in cards
    assert "Controlled-test authority" in cards
    assert "Driver coaching never authorizes a setup change." in cards
    assert "An anomaly says what was unexpected, not why it happened." in cards
    assert "They do not create a setup target." in cards
    assert "Samples are not counted as independent experiments." in cards
    assert "Only the server-owned Dial-In card can authorize or advance the test." in cards
    assert "It never starts, records, or advances a test." in cards
    assert "setupActionAuthorized" in cards
    assert "trustedSetupAuthorizedMove" in cards
    assert 'data-authority="measurement-health-only"' in cards
    assert "It never diagnoses a vehicle cause or authorizes a setup change." in cards
    assert "report.telemetry_health.current_run_id === runId" in cards
    assert "report.telemetry_health.session_id === sessionId" in cards
    assert "report.telemetry_health.setup_authorized === false" in cards


def test_attention_memory_is_exact_scope_and_presentation_only() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    assert 'racelab:intelligence-attention:v1:${sessionId ?? "run-only"}:${runId}' in cards
    assert "item.run_id === runId" in cards
    assert "previous === item.fingerprint" in cards
    assert 'data-authority="presentation-only"' in cards
    assert "Changed since last view" in cards
    assert "Mark updates seen" in cards
    effect = cards.split("useEffect(() => {", 1)[1].split("const markUpdatesSeen", 1)[0]
    mark_seen = cards.split("const markUpdatesSeen", 1)[1].split("if (snapshot.key", 1)[0]
    assert "localStorage.setItem(key, fingerprintSignature)" not in effect
    assert "localStorage.setItem(key, fingerprintSignature)" in mark_seen
    assert "onClick={markUpdatesSeen}" in cards
    assert "never changes evidence, ranking, or setup authority" in cards
    assert "createControlledWorkflow" not in cards
    assert "attachControlledWorkflowStage" not in cards


def test_race_disclosure_preference_is_separate_from_engineering_authority() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    assert 'const disclosureKey = "racelab:smart-disclosure:v1"' in cards
    assert "Supporting verified intelligence" in cards
    assert "learning ? (" in cards
    assert "Reset compact view" in cards
    assert "This display preference never changes evidence, ranking, or setup authority." in cards
    assert "window.localStorage.setItem(disclosureKey" in cards
    assert "setupActionAuthorized" in cards


def test_measurement_debt_recovery_is_typed_navigation_only() -> None:
    helper = _read("ui/src/utils/intelligenceNavigation.ts")
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    for recovery_kind in (
        "select_eligible_lap",
        "retry_resource",
        "inspect_missing_channel",
        "repeat_measurement",
        "resume_workflow",
    ):
        assert f'"{recovery_kind}"' in helper

    assert "trustedRecoveryTarget(item.recovery_kind, item.workspace)" in cards
    assert "onOpenRecovery(target.workspace, target.kind)" in cards
    assert "Recovery buttons navigate to evidence" in cards
    assert "retryRun" not in cards
    assert "createControlledWorkflow" not in cards
    assert "attachControlledWorkflowStage" not in cards


def test_grounded_question_chips_adapt_to_structured_context() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert "const contextualQuestions = useMemo" in engineer
    assert "report.opportunity_signature" in engineer
    assert "report.mechanism_observations" in engineer
    assert "report.session_ledger" in engineer
    assert "report.hypothesis_lifecycle" in engineer
    assert "report.driver_focus" in engineer
    assert "report.anomalies" in engineer
    assert "report.measurement_debt?.items.length" in engineer
    assert "How repeatable is the strongest opportunity?" in engineer
    assert "Which typed mechanism has the strongest evidence?" in engineer
    assert "Which hypotheses should I avoid repeating?" in engineer
    assert "What evidence should I recover first?" in engineer
    assert "submitQuestion(suggestion)" in engineer
    assert "questionScopeLabel" in engineer
    question_builder = engineer.split("const contextualQuestions = useMemo", 1)[1].split(
        "const submitQuestion",
        1,
    )[0]
    assert "const structuredQuestions: string[] = []" in question_builder
    assert "[...structuredQuestions, ...asArray(report.suggested_questions)]" in question_builder
    assert question_builder.index("structuredQuestions.push") < question_builder.index(
        "...asArray(report.suggested_questions)"
    )


def test_setup_authorized_next_move_requires_exact_action_and_workflow_binding() -> None:
    helper = _read("ui/src/utils/intelligenceNavigation.ts")
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    authority = _read("ui/src/utils/currentIntelligenceAuthority.ts")

    setup_gate = helper.split("export function trustedSetupAuthorizedMove", 1)[1]
    assert "trustedNavigationMove(move, runId, authorization)" in setup_gate
    assert 'move.authority === "setup_authorized"' in setup_gate
    assert "move.control_key === authorization.controlKey" in setup_gate
    assert "exactEventIdentitySet(move.source_event_ids, authorization.sourceEventIds)" in setup_gate
    assert "leftSet.size === left.length" in helper
    assert "rightSet.size === right.length" in helper

    assert "authorizedSetupAction && trustedSetupAuthorizedMove(" in cards
    assert "controlKey: authorizedSetupAction.controlKey" in cards
    assert "sourceEventIds: authorizedSetupAction.sourceEventIds" in cards
    assert "canonicalText(action.control_key)" in authority
    assert "canonicalText(action.current_value)" in authority
    assert "canonicalText(action.proposed_value)" in authority
    assert "sourceEventIds: [...action.source_event_ids]" in authority
    assert "deriveCurrentReportSetupAuthority(" in engineer


def test_stage_b_preflight_and_untrusted_query_prose_fail_closed() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    preflight = cards.split("function PreflightCard", 1)[1].split(
        "function SessionLedgerCard",
        1,
    )[0]

    assert "setupActionAuthorized" in preflight
    assert "trustedSetupAuthorizedMove(report.next_trustworthy_move" in preflight
    assert "if (!stageBSetupAuthorized)" in preflight
    withheld = preflight.split("if (!stageBSetupAuthorized)", 1)[1].split("return (", 2)[1]
    assert "preflight.title" not in withheld
    assert "check.detail" not in withheld
    assert "preflight.blocker_reasons" not in withheld
    assert "queryActionWithheld" in engineer
    assert '? queryActionTrusted ? "Controlled setup action" : "Setup action withheld"' in engineer
    assert "queryActionWithheld\n    ? []" in engineer
    assert "!queryResponse.action_authorized && asArray(queryResponse.follow_up_questions)" in engineer
    assert "!queryResponse.action_authorized && (queryResponse.interpreted_lap_number" in engineer
    assert "!queryActionWithheld && (\n                <CitationLinks" in engineer


def test_engineer_report_freshness_includes_session_membership_and_workflow_revision() -> None:
    app = _read("ui/src/App.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    client = _read("ui/src/api/client.ts")

    assert "sessionRunScopeKey={controlledWorkflowScopeKey}" in app
    assert "workflowId={currentGuidanceWorkflow?.workflow_id ?? null}" in app
    assert "workflowUpdatedAt={currentGuidanceWorkflowUpdatedAt}" in app
    assert "session_run_scope: sessionRunScopeKey" in engineer
    assert "workflow_id: workflowId" in engineer
    assert "workflow_updated_at: workflowUpdatedAt" in engineer
    assert "refreshKey: `${sessionRunScopeKey}:${workflowId" in engineer
    assert 'refreshKey?: string | number' in client
    assert 'options?.refreshKey != null' in client


def test_query_entity_interpretation_is_visible_but_cannot_weaken_action_scope() -> None:
    types = _read("ui/src/types/intelligence.ts")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert "interpreted_lap_number?: number | null" in types
    assert "interpreted_window_start_lap?: number | null" in types
    assert "interpreted_phase?:" in types
    assert "interpreted_control_key?: string | null" in types
    assert "interpreted_track_region_id?: string | null" in types
    assert "interpreted_track_region_label?: string | null" in types
    assert "clarification_required?: boolean" in types
    assert "const queryInterpretationMatchesScope = Boolean(" in engineer
    assert "!queryResponse.clarification_required" in engineer
    assert "queryResponse.interpreted_lap_number === selectedQueryLap" in engineer
    assert "queryResponse.interpreted_window_start_lap === selectedLapWindowStart" in engineer
    assert "queryResponse.interpreted_window_end_lap === selectedLapWindowEnd" in engineer
    assert "&& queryInterpretationMatchesScope" in engineer
    assert 'aria-label="Server-interpreted question context"' in engineer
    assert "queryResponse.interpreted_track_region_label" in engineer
    assert "The answer remains bound to the selected run and question scope." in engineer


def test_smarter_cards_and_shell_are_responsive_and_keyboard_visible() -> None:
    styles = _read("ui/src/styles.css")

    for selector in (
        ".engineer-smart-layer",
        ".engineer-smart-grid",
        ".engineer-smart-card",
        ".engineer-recovery-list",
        ".shell-next-trustworthy-move",
        ".shell-next-move-scope",
    ):
        assert selector in styles

    assert ".engineer-next-move button:focus-visible" in styles
    assert ".engineer-recovery-list button:focus-visible" in styles
    assert ".shell-next-trustworthy-move > button:focus-visible" in styles
    assert "@media (max-width: 920px)" in styles
    assert "@media (max-width: 860px)" in styles
