from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_smart_engineer_is_a_lazy_first_class_workspace() -> None:
    app = _read("ui/src/App.tsx")
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")
    store_types = _read("ui/src/store/types.ts")
    shortcuts = _read("ui/src/hooks/useKeyboardShortcuts.ts")

    assert 'const loadEngineerTab = () => import("./tabs/EngineerTab")' in app
    assert "const EngineerTab = lazy" in app
    assert 'workspace === "engineer"' in app
    assert '["engineer", "Engineer", BrainCircuit]' in app
    assert '<EngineerTab' in app
    assert '"engineer"' in store_types
    assert '"engineer"' in selection.split("const VALID_WORKSPACES", 1)[1].split("];", 1)[0]
    assert 'openWorkspace("engineer")' in shortcuts
    assert "<span>E</span><p>Open Smart Engineer</p>" in app


def test_intelligence_api_is_run_and_session_scoped_with_presentation_only_mode() -> None:
    client = _read("ui/src/api/client.ts")
    types = _read("ui/src/types/intelligence.ts")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert "export function fetchRunIntelligence" in client
    assert "session_id" in client
    assert "/intelligence${suffix}" in client
    assert "export function queryRunIntelligence" in client
    assert "/intelligence/query" in client
    assert "IntelligenceQueryRequest" in client

    assert 'presentation_mode: "race" | "learning"' in types
    assert "Presentation preference only" in types
    assert 'presentation_mode: learning ? "learning" : "race"' in engineer
    assert "affects_evidence_eligibility: false" in types
    assert "track_region_label" in types
    assert "citation.track_region_label" in engineer


def test_intelligence_discards_stale_report_and_question_responses() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert "const reportSequence = useRef(0)" in engineer
    assert "const querySequence = useRef(0)" in engineer
    assert "const sequence = ++reportSequence.current" in engineer
    assert "sequence !== reportSequence.current" in engineer
    assert "scopeMatches(report, runId, sessionId)" in engineer
    assert "Nothing from that response was shown." in engineer
    assert 'setReportState({ requestKey: scopeKey, status: "loading", report: null' in engineer
    assert "const sequence = ++querySequence.current" in engineer
    assert "sequence !== querySequence.current" in engineer
    assert "scopeMatches(response, runId, sessionId)" in engineer
    assert "response.question.trim() !== nextQuestion" in engineer
    assert "It was discarded." in engineer
    assert 'setQueryState({ requestKey: null, status: "idle", response: null' in engineer
    assert "}, [learning, questionScopeKey, scopeKey]);" in engineer
    assert "cancelled || sequence !== reportSequence.current" in engineer


def test_intelligence_citation_handoff_clears_stale_zone_channel_and_setup_scope() -> None:
    app = _read("ui/src/App.tsx")
    handoff = app.split("const openIntelligenceCitation", 1)[1].split(
        "const refreshSessionRuns", 1
    )[0]

    assert "buildZoneEvidence(selection, { lapPct: citationLapPct })" in handoff
    assert "citation.run_id === selection.selectedRunId" in handoff
    assert "zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null" in handoff
    assert 'dispatch({ type: "SELECT_SETUP_KEY", setupKey: null })' in handoff
    assert "channelId: null" in handoff


def test_smart_engineer_setup_action_fails_closed_and_stays_one_change_only() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    authority = _read("ui/src/utils/currentIntelligenceAuthority.ts")

    assert "function driverFacingIssue" in engineer
    assert 'replace(/_/g, " ")' in engineer
    authorization = authority.split("export function deriveCurrentReportSetupAuthority", 1)[1].split(
        "export function deriveCurrentIntelligenceAuthority", 1
    )[0]
    assert 'action?.kind !== "controlled_test"' in authorization
    assert "action.setup_authorized !== true" in authorization
    assert "action.source_event_ids" in authorization
    assert "action.blocker_reasons" in authorization
    assert "canonicalText(action.current_value)" in authorization
    assert "canonicalText(action.proposed_value)" in authorization
    assert "canonicalText(action.instruction)" in authorization
    assert "exactEventIdentitySet(action.source_event_ids, qualifiedActionCitationIds)" in authorization
    assert 'report.status !== "ready"' in authorization
    assert 'report.data_quality?.status !== "ready"' in authorization
    assert "AUTHORIZED_ACTION_STATES.has(action.evidence_state)" in authorization
    action_state_gate = engineer.split("function controlledTestStateSupportsAction", 1)[1].split("}", 1)[0]
    assert 'state === "needs_confirmation"' in action_state_gate
    assert "evidenceStateSupportsAction(state)" in action_state_gate
    assert "citation.run_id === runId" in engineer
    assert "citation.source_channels.length > 0" in engineer
    assert 'citation.citation_id === eventId' not in authorization
    assert "citation.lap_number === selectedQueryLap" in engineer
    assert "queryActionCitations.length === asArray(queryResponse.citations).length" in engineer
    assert 'queryResponse.status === "ready"' in engineer
    assert "!queryResponse.clarification_required" in engineer
    assert "&& actionAuthorized" in engineer
    assert "queryResponse.answer === currentReportSetupAuthority?.instruction" in engineer
    assert "asArray(queryResponse.action_source_event_ids),\n      actionSourceEventIds" in engineer

    assert "actionAuthorized ? (" in engineer
    assert "Open controlled test" in engineer
    assert 'setWorkspace("dial_in", "engineer")' in engineer
    assert "No setup-change control is available from this evidence." in engineer
    assert 'actionAuthorized ? action.title : "Evidence task only"' in engineer
    assert "No setup change, Keep/Undo, or stop-testing policy is authorized." in engineer
    assert "Keep the current setup and collect the requested evidence." not in engineer
    assert 'label="Controlled-test evidence"' in engineer
    assert "best_measurement" in engineer
    assert "Best next measurement" in engineer


def test_learning_mode_exposes_explanations_without_weakening_evidence() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    types = _read("ui/src/types/intelligence.ts")

    assert 'selection.selectedMode === "learning"' in engineer
    assert "Why this call?" in engineer
    assert "Evidence graph" in engineer
    assert "Full graph · {graphNodes.length} nodes · {graphEdges.length} relationships" in engineer
    assert ".slice(0, 10)" in engineer
    assert "Cause board" in engineer
    assert "Supports" in engineer
    assert "Contradicts" in engineer
    assert "Best next measurement" in engineer
    assert "Worked here before" not in engineer
    assert "CrewChiefCommandDeck" in engineer
    assert "Calibration record" in engineer
    assert "protocol-valid gradable direction outcomes" in engineer
    assert "Session narrative" in engineer
    assert "Adapted presentation" in engineer
    assert "Personalization never changes lap eligibility, evidence gates, or confidence." in engineer

    for contract in (
        "IntelligenceEvidenceGraph",
        "IntelligenceCause",
        "IntelligenceMeasurement",
        "IntelligenceContextMatch",
        "IntelligenceCalibration",
        "IntelligenceNarrativeEntry",
        "IntelligenceDriverProfile",
    ):
        assert f"export type {contract}" in types


def test_data_quality_has_compact_status_and_learning_recovery() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    types = _read("ui/src/types/intelligence.ts")

    assert 'status: "ready" | "limited" | "blocked"' in types
    assert "eligible_laps" in types
    assert "trusted_events" in types
    assert "recovery_steps" in types
    assert "Evidence qualification counts" in engineer
    assert "eligible laps" in engineer
    assert "trusted events" in engineer
    assert "learning &&" in engineer
    assert "Recover the evidence" in engineer
    assert 'data-status={quality.status}' in engineer


def test_race_mode_keeps_secondary_engineering_surfaces_behind_one_disclosure() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "const [raceSupportOpen, setRaceSupportOpen] = useState(false)" in engineer
    assert "setRaceSupportOpen(false)" in engineer
    assert "{!learning && (" in engineer
    assert 'className="engineer-race-support-toggle"' in engineer
    assert 'aria-expanded={raceSupportOpen}' in engineer
    assert 'aria-controls="engineer-supporting-evidence"' in engineer
    assert "Supporting evidence and tools" in engineer
    assert "{(learning || raceSupportOpen) && (" in engineer
    assert 'id="engineer-supporting-evidence"' in engineer
    assert ".engineer-race-support-toggle" in styles
    assert '.engineer-race-support-toggle[aria-expanded="true"] svg' in styles


def test_grounded_questions_are_not_a_generic_chat_surface() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    assert "Grounded run questions" in engineer
    assert "Ask this evidence" in engineer
    assert "Question about the selected run" in engineer
    assert "selected_lap: selectedQueryLap" in engineer
    assert "selected_window_start_lap: completeWindowQuestionScope ? selectedLapWindowStart : null" in engineer
    assert "selected_window_end_lap: completeWindowQuestionScope ? selectedLapWindowEnd : null" in engineer
    assert "selected_window_representative_lap: completeWindowQuestionScope ? selectedQueryLap : null" in engineer
    assert "selected_lap: number | null" in _read("ui/src/types/intelligence.ts")
    assert "(response.selected_lap ?? null) !== selectedQueryLap" in engineer
    assert "response.interpreted_window_representative_lap === selectedQueryLap" in engineer
    assert "response.scope_run_ids" in engineer
    assert "responseRunScope.length === queryNavigationRunIds.size" in engineer
    assert "current run, session, question scope, and question" in engineer
    assert "Tracing the answer to this run" in engineer
    assert "Grounded answer" in engineer
    assert "Evidence limit" in engineer
    assert "queryActionTrusted" in engineer
    assert "citation.valid_for_tuning" in engineer
    assert "const visibleQueryAnswer" in engineer
    assert "The exact setup target was withheld because its evidence links were incomplete." in engineer
    assert "<p>{visibleQueryAnswer}</p>" in engineer
    assert "Action withheld because its exact tuning citation was incomplete." in engineer
    assert 'aria-live="polite"' in engineer
    assert 'minLength={2}' in engineer
    assert 'maxLength={280}' in engineer
    assert "chatbot" not in engineer.lower()


def test_query_actions_require_exact_public_event_identity_and_window_scope() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    helper = _read("ui/src/utils/intelligenceNavigation.ts")
    types = _read("ui/src/types/intelligence.ts")

    assert "action_source_event_ids: string[]" in types
    assert "suggested_navigation: IntelligenceQueryNavigationTarget[]" in types
    assert "exactEventIdentitySet(" in engineer
    assert "queryActionCitationEventIds" in engineer
    assert "asArray(queryResponse.action_source_event_ids)" in engineer
    assert "queryActionCitations.length === asArray(queryResponse.citations).length" in engineer
    assert "citation.lap_number >= interpretedQueryWindow.start" in engineer
    assert "citation.lap_number <= interpretedQueryWindow.end" in engineer
    assert "leftSet.size === left.length" in helper
    assert "rightSet.size === right.length" in helper


def test_query_navigation_is_membership_guarded_and_evidence_only() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    helper = _read("ui/src/utils/intelligenceNavigation.ts")

    assert "JSON.parse(sessionRunScopeKey)" in engineer
    assert "parsed.includes(runId)" in engineer
    assert "trustedQueryNavigationCitation(target, queryNavigationRunIds)" in engineer
    assert 'label="Suggested evidence handoffs"' in engineer
    assert "allowedRunIds.has(target.run_id)" in helper
    assert "QUERY_NAVIGATION_WORKSPACES.has(target.workspace)" in helper
    assert 'evidence_state: "needs_confirmation"' in helper
    assert "valid_for_tuning: false" in helper
    assert "It never grants setup authority." in helper


def test_public_decision_status_gates_setup_authority_and_is_broadcast() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    types = _read("ui/src/types/intelligence.ts")
    authority = _read("ui/src/utils/currentIntelligenceAuthority.ts")

    assert 'IntelligenceDecisionStatus = "ready" | "measure" | "blocked"' in types
    assert "decision_status: IntelligenceDecisionStatus" in types
    assert 'report.decision_status !== "ready"' in authority
    assert 'report?.decision_status === "blocked"' in engineer
    assert "data-decision-status={decisionStatus}" in engineer
    assert "Decision status <strong>{driverFacingLabel(decisionStatus)}</strong>" in engineer


def test_typed_mind_change_criteria_reach_report_and_query_contracts() -> None:
    types = _read("ui/src/types/intelligence.ts")

    assert "export type IntelligenceMindChangeCriterion" in types
    assert 'evidence_kind: "controlled_test" | "measurement_mission" | "discriminator"' in types
    assert "acceptance_conditions: string[]" in types
    assert "falsification_conditions: string[]" in types
    assert "minimum_independent_evidence_units: number" in types
    assert 'next_state_if_inconclusive: "unresolved"' in types
    assert types.count("mind_change_criteria: IntelligenceMindChangeCriterion[]") == 2


def test_engineer_keeps_briefing_authority_run_scoped_and_preserves_window_question_context() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    for prop in (
        "selectedLapScope: LapScope",
        "selectedLapWindowStart: number | null",
        "selectedLapWindowEnd: number | null",
        "selectedRepresentativeLap: number | null",
    ):
        assert prop in engineer

    assert 'data-briefing-scope="run"' in engineer
    assert "data-session-id={sessionId ?? undefined}" in engineer
    assert "data-selected-lap" not in engineer
    assert "Briefing scope <strong>Run</strong>" in engineer
    assert "Question scope <strong>{questionScopeLabel}</strong>" in engineer
    assert 'selectedLapScope === "lap_window"' in engineer
    assert "const completeWindowQuestionScope" in engineer
    assert "lap_window_representative" in engineer
    assert "Representative Lap ${selectedQueryLap} from Window L${selectedLapWindowStart}" in engineer
    assert "data-question-lap={selectedQueryLap ?? undefined}" in engineer
    assert "data-window-start={completeWindowQuestionScope" in engineer
    assert "data-window-end={completeWindowQuestionScope" in engineer
    assert "data-representative-lap={completeWindowQuestionScope" in engineer
    assert "Answers anchor to representative Lap {selectedQueryLap}; full-window pace remains in Laps." in engineer
    assert 'selectedLapScope === "lap_window" || selectedLapScope === "run"' in engineer


def test_intelligence_citations_navigate_exact_run_lap_position_and_workspace() -> None:
    app = _read("ui/src/App.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    types = _read("ui/src/types/intelligence.ts")

    assert "run_id: string" in types
    assert "lap_number?: number | null" in types
    assert "lap_pct?: number | null" in types
    assert "event_id?: string | null" in types
    assert "workspace: IntelligenceCitationWorkspace" in types
    assert "source_channels: string[]" in types

    handler = app.split("const openIntelligenceCitation", 1)[1].split(
        "const refreshSessionRuns", 1
    )[0]
    assert "INTELLIGENCE_CITATION_WORKSPACES.has(citation.workspace)" in handler
    assert "!attachedSessionRunIds.has(citation.run_id)" in handler
    assert "await loadSelectedRun(citation.run_id)" in handler
    assert "lapNumber: citationLap" in handler
    assert "lapPct: citationLapPct" in handler
    assert "eventId: citation.event_id" in handler
    assert 'selectionSource: "engineer"' in handler
    assert "citation.workspace" in handler
    assert "onNavigateCitation={openIntelligenceCitation}" in app
    assert 'aria-label={label}' in engineer
    assert "Open exact evidence" in engineer


def test_smart_engineer_has_explicit_recovery_accessibility_and_responsive_contracts() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    styles = _read("ui/src/styles.css")

    assert "LoadingState" in engineer
    assert 'role="status" aria-live="polite"' in engineer
    assert 'role="alert"' in engineer
    assert "No stale briefing was kept" in engineer
    assert "Current evidence needs recovery" in engineer
    assert "Re-import the original telemetry or review run health" in engineer
    assert engineer.count("<RefreshCcw") >= 2
    assert "A grounded briefing is not available yet" in engineer
    assert "No setup conclusion will be created from incomplete or ineligible evidence." in engineer
    assert 'aria-labelledby="engineer-briefing-heading"' in engineer
    assert 'htmlFor="engineer-question"' in engineer

    assert "/* Smart Engineer" in styles
    assert ".smart-engineer-workspace" in styles
    assert ".engineer-decision-grid" in styles
    assert ".engineer-learning-grid" in styles
    assert "@media (max-width: 1180px)" in styles
    assert "@media (max-width: 920px)" in styles
    assert ".engineer-authorized-action:focus-visible" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
