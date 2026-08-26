from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_source_run_authority_projection_fails_closed_across_every_identity() -> None:
    source = _read("ui/src/utils/currentIntelligenceAuthority.ts")
    report_gate = source.split("export function deriveCurrentReportSetupAuthority", 1)[1].split(
        "export function deriveCurrentIntelligenceAuthority",
        1,
    )[0]
    projection_gate = source.split("export function deriveCurrentIntelligenceAuthority", 1)[1].split(
        "export function currentIntelligenceAuthorityMatchesWorkflow",
        1,
    )[0]

    assert 'workflow.status !== "a_recorded"' in source
    assert "workflow.stage_run_ids.A !== workflow.source_run_id" in source
    assert "workflow.source_run_id !== sourceRunId" in projection_gate
    assert "report.run_id !== sourceRunId" in report_gate
    assert "!canonicalText(sessionId)" in report_gate
    assert "report.session_id !== sessionId" in report_gate
    assert "telemetryHealth?.session_id !== sessionId" in report_gate
    assert "telemetryHealth.current_run_id !== sourceRunId" in report_gate
    assert "telemetryHealth.ordered_session_run_ids.includes(sourceRunId)" in report_gate
    assert 'report.status !== "ready"' in report_gate
    assert 'report.decision_status !== "ready"' in report_gate
    assert 'report.data_quality?.status !== "ready"' in report_gate
    assert "report.data_quality.issues.length !== 0" in report_gate
    assert "report.blocker_reasons.length !== 0" in report_gate
    assert "briefing.blocker_reasons.length !== 0" in report_gate
    assert 'action?.kind !== "controlled_test"' in report_gate
    assert "action.setup_authorized !== true" in report_gate
    assert "reportAuthority.controlKey !== card.controlKey" in projection_gate
    assert "reportAuthority.currentValue !== card.currentValue" in projection_gate
    assert "reportAuthority.proposedValue !== card.proposedValue" in projection_gate
    assert "reportAuthority.instruction !== card.instruction" in projection_gate
    assert "exactEventIdentitySet(reportAuthority.sourceEventIds, card.sourceEventIds)" in projection_gate
    assert "measurement.mission_id !== `controlled-test:${action.control_key}`" in report_gate
    assert "exactTextList(measurement.procedure, card.stageInstructions)" in projection_gate
    assert "measurementCitations.every((citation) => citationIsQualified(citation, sourceRunId))" in report_gate
    assert "exactEventIdentitySet(action.source_event_ids, qualifiedActionCitationIds)" in report_gate
    assert "trustedSetupAuthorizedMove(move, sourceRunId" in report_gate
    assert "workflowUpdatedAt" in projection_gate
    assert 'preflight.stage !== "B"' in report_gate
    assert 'preflight.status !== "ready"' in report_gate


def test_blocked_or_semantic_do_not_repeat_report_can_never_reanimate_stored_card() -> None:
    source = _read("ui/src/utils/currentIntelligenceAuthority.ts")
    app = _read("ui/src/App.tsx")

    # A semantic do-not-repeat policy arrives as a blocked/non-ready decision and
    # blocker prose. Every such route must return null before a projection exists.
    assert 'report.decision_status !== "ready"' in source
    assert "report.blocker_reasons.length !== 0" in source
    assert "briefing.blocker_reasons.length !== 0" in source
    assert "action.blocker_reasons.length !== 0" in source
    assert "preflight.blocker_reasons.length !== 0" in source
    assert "authority ? \"authorized\" : \"withheld\"" in app
    assert "authority: null" in app
    assert "CURRENT_INTELLIGENCE_AUTHORITY_RECOVERY" in app


def test_app_fetches_authority_from_exact_workflow_source_revision_and_passes_projection() -> None:
    app = _read("ui/src/App.tsx")
    request_key = app.split("const intelligenceAuthorityRequestKey", 1)[1].split(
        "const intelligenceAuthorityCanLoad",
        1,
    )[0]
    effect = app.split("const requestSeq = ++intelligenceAuthorityRequestSeqRef.current", 1)[1].split(
        "useEffect(() => {\n    let cancelled = false;",
        1,
    )[0]

    assert "source_run_id: currentAuthorityWorkflow?.source_run_id ?? null" in request_key
    assert "workflow_id: currentAuthorityWorkflow?.workflow_id ?? null" in request_key
    assert "workflow_updated_at: currentAuthorityWorkflowUpdatedAt" in request_key
    assert "session_run_scope: controlledWorkflowScopeKey" in request_key
    assert "artifact_refresh_generation: intelligenceAuthorityRefreshGeneration" in request_key
    assert "controlledWorkflowScopeRunIds.includes(currentAuthorityWorkflow.source_run_id)" in app
    assert "fetchRunIntelligence(requestedSourceRunId" in effect
    assert "deriveCurrentIntelligenceAuthority(" in effect
    assert "requestedWorkflow" in effect
    assert "requestedSessionId" in effect
    assert "currentIntelligenceAuthorityMatchesWorkflow(" in app
    assert "currentIntelligenceAuthority={currentIntelligenceAuthority}" in app
    assert "intelligenceAuthorityStatus={currentIntelligenceAuthorityStatus}" in app
    assert "intelligenceAuthorityRecovery={currentIntelligenceAuthorityRecovery}" in app
    assert "invalidateIntelligenceAuthority();" in app


def test_shared_report_authority_keeps_fresh_action_but_binds_active_stage_b() -> None:
    source = _read("ui/src/utils/currentIntelligenceAuthority.ts")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    gate = source.split("export function deriveCurrentReportSetupAuthority", 1)[1].split(
        "export function deriveCurrentIntelligenceAuthority",
        1,
    )[0]

    assert "const workflowBound = hasWorkflowId && hasWorkflowUpdatedAt" in gate
    assert "if (!workflowBound)" in gate
    assert "preflight != null" in gate
    assert 'stage: "fresh"' in gate
    assert 'report.mission_stage !== "test"' in gate
    assert 'preflight.stage !== "B"' in gate
    assert "trustedSetupAuthorizedMove(move, sourceRunId" in gate
    assert "deriveCurrentReportSetupAuthority(" in engineer
    assert "const actionAuthorized = currentReportSetupAuthority != null" in engineer


def test_exact_three_step_protocol_rejects_appended_stage_b_prose() -> None:
    source = _read("ui/src/utils/currentIntelligenceAuthority.ts")

    assert "measurement.controlled_variables.length !== 1" in source
    assert "const controlledLabel = SETUP_CONTROL_LABELS[action.control_key]" in source
    assert "controlledVariable !== `Change only ${controlledLabel}.`" in source
    assert "`Keep ${controlledLabel} at the recorded baseline value.`" in source
    assert "`Change only ${controlledLabel}: ${action.instruction}.`" in source
    assert "action.instruction !== `${action.current_value} -> ${action.proposed_value}" in source


def test_same_run_artifact_refresh_synchronously_invalidates_authority() -> None:
    app = _read("ui/src/App.tsx")

    invalidation = app.split("const invalidateIntelligenceAuthority", 1)[1].split(
        "const selectedTraceLap",
        1,
    )[0]
    loader = app.split("const loadSelectedRun = useCallback", 1)[1].split(
        "const openAttachedSessionRun",
        1,
    )[0]
    importer = app.split("const handleFileSelected = useCallback", 1)[1].split(
        "const leaveCurrentSession",
        1,
    )[0]

    assert "intelligenceAuthorityRequestSeqRef.current += 1" in invalidation
    assert "authority: null" in invalidation
    assert "setIntelligenceAuthorityRefreshGeneration" in invalidation
    assert loader.index("invalidateIntelligenceAuthority();") < loader.index("await fetchOverview(runId)")
    assert 'if (ext === "ibt") invalidateIntelligenceAuthority();' in importer


def test_ribbon_never_uses_stored_exact_change_as_stage_b_authority() -> None:
    ribbon = _read("ui/src/components/ControlledTestRibbon.tsx")

    assert "currentIntelligenceAuthorityMatchesWorkflow(" in ribbon
    assert "workflow.packet.primary_test?.exact_change" not in ribbon
    assert "authority.instruction" not in ribbon
    assert 'label: authorityStatus === "checking" ? "Stage B authority checking" : "Stage B authority unavailable"' in ribbon
    assert "stored target stays hidden" in ribbon
    assert "Review workflow evidence" in ribbon
    assert 'data-authority={nextStage === "B" && exactSourceRunAuthority ? "source-run-card" : "non-authorizing-progress"}' in ribbon


def test_dial_in_hides_stage_b_prose_and_blocks_only_the_authorizing_stage() -> None:
    dial_in = _read("ui/src/tabs/DialInTab.tsx")
    record = dial_in.split("const recordCurrentRun = useCallback", 1)[1].split(
        "const scoreVerifiedWorkflow",
        1,
    )[0]

    assert "workflow.packet.primary_test?.exact_change" not in dial_in
    assert "workflow.packet.primary_test.exact_change" not in dial_in
    assert 'stage.stage !== "B" || authority' in dial_in
    assert "Exact Stage B instruction withheld pending current source-run intelligence" in dial_in
    assert 'nextWorkflowStage === "B" && exactSourceRunIntelligenceAuthority == null' in record
    assert "!currentStageRecordingAllowed" in dial_in
    assert 'const currentStageRecordingAllowed = nextWorkflowStage !== "B"' in dial_in
    assert "authority={exactSourceRunIntelligenceAuthority}" in dial_in
    assert "exactSourceRunIntelligenceAuthority.instruction" in dial_in
    assert "intelligenceAuthorityRecovery" in dial_in
    assert "abandon" in dial_in.lower()
    assert "rebuild" in dial_in.lower()
    assert 'selection.selectedMode === "learning" && !stageBSetupAuthorityWithheld' in dial_in
    assert "Stage B setup detail is withheld until current source-run authority is restored." in dial_in
    assert "!stageBSetupAuthorityWithheld && hints.length > 0" in dial_in
    assert "Baseline only · no setup authority" in dial_in
    assert "Restore only · no setup authority" in dial_in
    assert "The workflow response itself cannot publish a target or Keep/Undo verdict." in dial_in
    assert "workflow.quality.verdict" not in dial_in
