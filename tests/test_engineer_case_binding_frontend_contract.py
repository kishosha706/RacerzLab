from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_main_engineer_report_is_keyed_and_validated_against_the_active_case() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    trust = _read("ui/src/utils/intelligenceResponseTrust.ts")
    client = _read("ui/src/api/client.ts")

    for identity in (
        "case_sha256",
        "case_revision_sha256",
        "p19_reasoning_snapshot_sha256",
        "run_id",
        "session_id",
    ):
        assert identity in engineer.split("const caseBindingKey", 1)[1].split("});", 1)[0]
    assert "case_provider_status: engineeringCaseStatus" in engineer
    assert "case_binding: caseBindingKey" in engineer
    assert "requestedScopeKey !== activeReportScopeKeyRef.current" in engineer
    assert "requestedCaseBindingKey !== activeCaseBindingKeyRef.current" in engineer
    assert "reasoningSnapshotSha256: requestedReasoningSnapshotSha256" in engineer
    assert "report.reasoning_snapshot_sha256 !== requestedReasoningSnapshotSha256" in engineer
    assert "report.setup_id !== requestedSetupId" in engineer
    assert "report.setup_snapshot_sha256 !== requestedSetupSnapshotSha256" in engineer
    assert "reasoningSnapshotSha256?: string | null" in trust
    assert "value.reasoning_snapshot_sha256 !== expectation.reasoningSnapshotSha256" in trust
    report_fetch = client.split("export function fetchRunIntelligence", 1)[1].split(
        "export function fetchVehicleSystems", 1
    )[0]
    assert 'params.set("refresh", String(options.refreshKey))' in report_fetch


def test_engineer_query_rejects_old_case_promises_and_provider_gates_controls() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")

    query = engineer.split("const submitQuestion", 1)[1].split("const handleSubmit", 1)[0]
    assert "case_revision_sha256: requestedCaseRevisionSha256" in query
    assert "p19_reasoning_snapshot_sha256: requestedReasoningSnapshotSha256" in query
    assert "requestedQueryBindingKey !== activeQueryBindingKeyRef.current" in query
    assert "isIntelligenceQueryResponseBoundToReport(response, requestedReport)" in query
    assert "response.case_id !== requestedCaseId" in query
    assert "response.case_sha256 !== requestedCaseSha256" in query
    assert "response.reasoning_snapshot_sha256 !== requestedReasoningSnapshotSha256" in query
    assert "scopeMatches(response, requestedRunId, requestedSessionId)" in query

    assert "Binding current case…" in engineer
    assert "Retry the current case before using the briefing or questions." in engineer
    assert "Retry current case" in engineer
    assert 'data-case-binding-state={status}' in engineer
    assert 'id="engineer-question-disabled"' in engineer
    assert '<button type="button" disabled>Ask</button>' in engineer
    assert 'disabled={!caseControlsEnabled || queryStatus === "loading"}' in engineer
    assert "disabled={!caseControlsEnabled || question.trim().length < 2" in engineer
