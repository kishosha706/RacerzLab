from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _dial_in() -> str:
    return (ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_dial_in_commits_only_exact_run_and_workflow_responses() -> None:
    dial_in = _dial_in()

    submit = _between(dial_in, "const submitDialIn", "const clearDialIn")
    assert "nextWorkflow.source_run_id !== requestedRunId" in submit
    assert "dialResult.value.run_id !== requestedRunId" in submit
    assert submit.index("nextWorkflow.source_run_id !== requestedRunId") < submit.index(
        "setWorkflow(nextWorkflow)"
    )
    assert submit.index("dialResult.value.run_id !== requestedRunId") < submit.index(
        "setResponse(dialResponse)"
    )
    assert "const dialResponse = dialResult.status" in submit
    assert "setWorkflowIdentityError(message)" in submit

    build = _between(dial_in, "const buildVerifiedWorkflow", "const nextWorkflowStage")
    assert "nextWorkflow.source_run_id !== requestedRunId" in build
    assert build.index("nextWorkflow.source_run_id !== requestedRunId") < build.index(
        "setWorkflow(nextWorkflow)"
    )

    record = _between(dial_in, "const recordCurrentRun", "const scoreVerifiedWorkflow")
    for exact_identity in (
        "nextWorkflow.workflow_id !== workflowId",
        "nextWorkflow.source_run_id !== expectedSourceRunId",
        "nextWorkflow.stage_run_ids[requestedStage] !== requestedRunId",
    ):
        assert exact_identity in record
        assert record.index(exact_identity) < record.index("setWorkflow(nextWorkflow)")

    score = _between(dial_in, "const scoreVerifiedWorkflow", "const chooseClarification")
    for exact_identity in (
        "nextWorkflow.workflow_id !== workflowId",
        "nextWorkflow.source_run_id !== expectedSourceRunId",
        'nextWorkflow.status !== "scored"',
    ):
        assert exact_identity in score
        assert score.index(exact_identity) < score.index("setWorkflow(nextWorkflow)")

    certificate = _between(dial_in, "const openTestCertificate", "const copyTestCertificate")
    assert "setCertificateMarkdown(null)" in certificate
    assert "certificate.workflow_id !== workflowId" in certificate
    assert certificate.index("certificate.workflow_id !== workflowId") < certificate.index(
        "setCertificateMarkdown(certificate.markdown)"
    )


def test_multiple_active_workflows_block_selection_and_exact_authority() -> None:
    dial_in = _dial_in()
    catalog = _between(
        dial_in,
        "void fetchControlledWorkflows(sessionId, overview.run_id, false).then",
        "useEffect(() => {\n    try {\n      window.sessionStorage.setItem",
    )

    assert "const activeAuthorityScope = explicitScope.has(overview.run_id) ? explicitScope : currentRun" in catalog
    assert "items.filter((item) => isActive(item) && touchesRun(item, activeAuthorityScope))" in catalog
    assert "const workflowScopeIsAmbiguous = scopedActiveWorkflows.length > 1" in catalog
    assert "setAmbiguousActiveWorkflowCount(scopedActiveWorkflows.length)" in catalog
    assert "setAmbiguousActiveWorkflows(workflowScopeIsAmbiguous ? scopedActiveWorkflows : [])" in catalog
    ambiguous_default = catalog.split("if (workflowScopeIsAmbiguous) {", 2)[2].split(
        "const related =",
        1,
    )[0]
    assert "setWorkflow(null)" in ambiguous_default
    assert "setWorkflowError(MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER)" in ambiguous_default

    assert "const workflowAuthorityBlocked = workflowScopeConflict || workflowIdentityError != null || !workflowRecordIntegrityReady" in dial_in
    assert "activeControlledTest" in dial_in
    assert "&& workflowCatalogReady" in dial_in
    assert "&& !workflowAuthorityBlocked" in dial_in
    assert "&& workflowContextMatches" in dial_in
    assert 'data-authority={controlledTestAuthorityReady ? "server-verified" : "withheld"}' in dial_in
    assert "2 active workflows" not in dial_in  # The count is live, never hard-coded.
    assert "active workflows · authority withheld" in dial_in
    assert "Choose one extra workflow to abandon" in dial_in
    assert "ambiguousActiveWorkflows.map" in dial_in
    assert "Exact setup targets remain hidden until one active workflow remains." in dial_in
    assert "Abandon selected workflow" in dial_in
    assert "remainingActiveWorkflows.length === 1" in dial_in
    assert "Open an exact workflow from the controlled-test ribbon" not in dial_in
    assert "!workflowAuthorityBlocked && workflow.packet.decision === \"test\"" in dial_in
    assert "disabled={workflowBusy || !workflowContextMatches || workflowAuthorityBlocked}" in dial_in


def test_unique_session_measurement_follows_the_driver_across_run_handoffs() -> None:
    dial_in = _dial_in()
    catalog = _between(
        dial_in,
        "void fetchControlledWorkflows(sessionId, overview.run_id, false).then",
        "useEffect(() => {\n    try {\n      window.sessionStorage.setItem",
    )

    assert "const uniqueActiveWorkflowInScope" in catalog
    assert "? scopedActiveWorkflows[0]" in catalog
    next_workflow = catalog.split("const nextWorkflow =", 1)[1].split(
        "setWorkflow(nextWorkflow ?? null)",
        1,
    )[0]
    assert "?? uniqueActiveWorkflowInScope" in next_workflow
    assert next_workflow.index("?? uniqueActiveWorkflowInScope") < next_workflow.index("?? related[0]")
    assert "if (!overview || !sessionId || !workflowCatalogReady || activeWorkflow || workflowAuthorityBlocked) return" in dial_in


def test_lap_window_handoff_keeps_window_and_representative_lap_distinct() -> None:
    dial_in = _dial_in()

    assert 'selection.selectedLapScope === "lap_window"' in dial_in
    assert "selection.selectedRepresentativeLap ?? selection.selectedLap" in dial_in
    assert "selected_lap: selectedLapForRequest" in dial_in
    assert "Window L${selection.selectedLapWindowStart}–L${selection.selectedLapWindowEnd}" in dial_in
    assert "· Rep L${selectedRepresentativeLap}" in dial_in
    assert 'lap_scope: requestedLapScope' in dial_in
    assert 'window_start_lap: requestedLapScope === "lap_window"' in dial_in
    assert 'window_end_lap: requestedLapScope === "lap_window"' in dial_in
    assert 'representative_lap: requestedLapScope === "lap_window"' in dial_in
    assert dial_in.count("...workflowLapContext") >= 3
    assert "data-lap-scope={broadcastLapScope}" in dial_in
    assert 'data-window-start={broadcastLapScope === "lap_window"' in dial_in
    assert 'data-window-end={broadcastLapScope === "lap_window"' in dial_in
    assert 'data-representative-lap={broadcastLapScope === "lap_window"' in dial_in
    assert 'data-selected-lap={broadcastLapScope !== "lap_window"' in dial_in
    assert "persistedDecisionContext.window_start_lap === workflowLapContext.window_start_lap" in dial_in
    assert "persistedDecisionContext.window_end_lap === workflowLapContext.window_end_lap" in dial_in
    assert "persistedDecisionContext.representative_lap === workflowLapContext.representative_lap" in dial_in
    assert "const selectedWindowIsComplete" in dial_in
    assert 'headline: "Evidence scope is incomplete · setup action withheld"' in dial_in
    assert "const selectionScopeIsComplete" in dial_in
    assert "&& currentRequestBinding != null" in dial_in


def test_same_run_stale_loose_exit_l7_cannot_replace_tight_center_l5_request() -> None:
    dial_in = _dial_in()
    submit = _between(dial_in, "const submitDialIn", "const clearDialIn")
    build = _between(dial_in, "const buildVerifiedWorkflow", "const nextWorkflowStage")

    # Hostile replay: both payloads claim the selected run, but the returned workflow
    # carries the old loose-exit/L7 complaint and context after a tight-center/L5 request.
    assert "const requestedBinding = currentRequestBinding" in submit
    assert "requestBindingsMatch(currentRequestBindingRef.current, requestedBinding)" in submit
    assert "workflowMatchesRequest(nextWorkflow, requestedBinding)" in submit
    assert "normalizeComplaint(dialResult.value.complaint_raw) !== requestedBinding.normalized_complaint" in submit
    assert submit.index("workflowMatchesRequest(nextWorkflow, requestedBinding)") < submit.index(
        "setWorkflow(nextWorkflow)"
    )
    assert submit.index("normalizeComplaint(dialResult.value.complaint_raw)") < submit.index(
        "setResponse(dialResponse)"
    )
    assert "setWorkflowIdentityError(message)" in submit
    assert "setResponseRequestBinding(null)" in submit

    assert "selected_lap: selectedLapForRequest ?? null" in dial_in
    assert "selected_phase: decisionContext.selected_phase ?? null" in dial_in
    assert "normalized_complaint: normalizeComplaint(complaint) ?? \"\"" in dial_in
    assert "returnedContext != null" in dial_in
    assert "decisionContextsMatch(returnedContext, request.decision_context)" in dial_in

    assert "const requestedBinding = currentRequestBinding" in build
    assert "requestBindingsMatch(currentRequestBindingRef.current, requestedBinding)" in build
    assert "workflowMatchesRequest(nextWorkflow, requestedBinding)" in build
    assert build.index("workflowMatchesRequest(nextWorkflow, requestedBinding)") < build.index(
        "setWorkflow(nextWorkflow)"
    )
    assert "setResponseRequestBinding(null)" in build


def test_active_catalog_workflow_requires_complete_persisted_decision_context() -> None:
    dial_in = _dial_in()
    context_match = _between(dial_in, "const workflowContextMatches", "const controlledTestAuthorityReady")

    assert "readCompleteDecisionContext(workflow)" in dial_in
    for required_field in (
        '"selected_lap"',
        "context.lap_scope",
        '"window_start_lap"',
        '"window_end_lap"',
        '"representative_lap"',
        '"selected_zone_start_pct"',
        '"selected_zone_end_pct"',
        '"selected_zone_label"',
        '"selected_phase"',
        '"objective"',
        '"priority"',
    ):
        assert required_field in dial_in
    assert "if (!workflow) return true" in context_match
    assert "if (!persistedDecisionContext) return false" in context_match
    assert "activeWorkflowIntegrityError(nextWorkflow ?? null)" in dial_in
    assert "setWorkflowIdentityError(integrityError)" in dial_in
    assert "exact targets are hidden" in dial_in


def test_cross_run_active_plan_keeps_source_scope_and_marks_current_run_unverified() -> None:
    dial_in = _dial_in()

    assert "workflowPlanCrossesCurrentRun" in dial_in
    assert "currentRunIsUnverifiedStageCandidate" in dial_in
    assert 'data-run-id={broadcastRunId}' in dial_in
    assert 'data-current-run-id={overview.run_id}' in dial_in
    assert 'data-plan-run-id={workflow?.source_run_id}' in dial_in
    assert 'data-current-run-authority={currentRunIsUnverifiedStageCandidate ? "unverified-stage-candidate"' in dial_in
    assert 'Source run ${workflow.source_run_id.slice(0, 8)}' in dial_in
    assert "formatDecisionLapScope(persistedDecisionContext)" in dial_in
    assert "The open run is only a candidate for" in dial_in
    assert "until Verify current run succeeds" in dial_in
    assert "selectionTargetsWorkflowSource" in dial_in
    assert "if (workflow && persistedDecisionContext)" in dial_in
    assert "selected_zone_start_pct: persistedDecisionContext.selected_zone_start_pct" in dial_in


def test_stage_and_score_responses_preserve_the_immutable_plan_and_prior_bindings() -> None:
    dial_in = _dial_in()
    record = _between(dial_in, "const recordCurrentRun", "const scoreVerifiedWorkflow")
    score = _between(dial_in, "const scoreVerifiedWorkflow", "const chooseClarification")

    for section in (record, score):
        assert "captureWorkflowPlanBinding(workflow)" in section
        assert "workflowPreservesPlan(requestedPlanBinding, nextWorkflow)" in section
        assert "stageBindingsMatch(previousStageRunIds, nextWorkflow.stage_run_ids" in section
        assert section.index("workflowPreservesPlan(requestedPlanBinding, nextWorkflow)") < section.index(
            "setWorkflow(nextWorkflow)"
        )

    assert "nextWorkflow.status !== expectedStatus" in record
    assert "requestedStage, requestedRunId" in record
    assert 'nextWorkflow.status !== "scored"' in score
    assert "packet_fingerprint: stableSerialize(workflow.packet)" in dial_in
    assert "returned.packet_fingerprint === binding.packet_fingerprint" in dial_in
