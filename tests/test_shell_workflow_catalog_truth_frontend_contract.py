from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _app() -> str:
    return (ROOT / "ui/src/App.tsx").read_text(encoding="utf-8")


def test_shell_workflow_catalog_state_is_owned_by_the_exact_current_request() -> None:
    app = _app()

    assert 'type ControlledWorkflowCatalogStatus = "idle" | "checking" | "ready" | "error"' in app
    assert "type ControlledWorkflowCatalogState" in app
    assert "controlledWorkflowCatalogState.requestKey === controlledWorkflowRequestKey" in app

    current_state = app.split(
        "const controlledWorkflowCatalogStateOwnsRequest",
        1,
    )[1].split("const currentGuidanceWorkflowUpdatedAt", 1)[0]
    assert '!controlledWorkflowCatalogCanLoad\n    ? "idle"' in current_state
    assert 'controlledWorkflowCatalogStateOwnsRequest ? controlledWorkflowCatalogState.status : "checking"' in current_state
    assert 'currentControlledWorkflowCatalogStatus === "ready"' in current_state
    assert current_state.count('currentControlledWorkflowCatalogStatus === "ready"') == 3


def test_shell_workflow_catalog_transitions_fail_closed_and_ignore_stale_results() -> None:
    app = _app()
    effect = app.split(
        "const requestSeq = ++controlledWorkflowRequestSeqRef.current",
        1,
    )[1].split(
        "useEffect(() => {\n    const requestSeq = ++intelligenceShellRequestSeqRef.current",
        1,
    )[0]

    checking = 'setControlledWorkflowCatalogState({ requestKey: requestedWorkflowKey, status: "checking", error: null })'
    ready = 'setControlledWorkflowCatalogState({ requestKey: requestedWorkflowKey, status: "ready", error: null })'
    assert checking in effect
    assert ready in effect
    assert effect.index(checking) < effect.index("fetchControlledWorkflows(false, {") < effect.index(ready)

    ready_prefix = effect[: effect.index(ready)]
    for stale_guard in (
        "cancelled",
        "requestSeq !== controlledWorkflowRequestSeqRef.current",
        "currentRefresh !== refreshSeq",
    ):
        assert stale_guard in ready_prefix.rsplit("if (", 1)[1]

    error_branch = effect.split("} catch (catalogError) {", 1)[1]
    assert "requestSeq === controlledWorkflowRequestSeqRef.current" in error_branch
    assert "currentRefresh === refreshSeq" in error_branch
    assert 'requestKey: requestedWorkflowKey' in error_branch
    assert 'status: "error"' in error_branch
    assert "error: controlledWorkflowCatalogRecovery(catalogError)" in error_branch
    assert error_branch.index("requestSeq === controlledWorkflowRequestSeqRef.current") < error_branch.index('status: "error"')
    assert error_branch.index('status: "error"') < error_branch.index("setActiveControlledWorkflow(null)")
    assert error_branch.index('status: "error"') < error_branch.index("setGuidanceControlledWorkflow(null)")


def test_dial_in_shell_broadcast_never_infers_availability_during_catalog_check_or_failure() -> None:
    app = _app()
    signal = app.split("dial_in: currentControlledWorkflowCatalogStatus", 1)[1].split(
        "};\n  }, [currentControlledWorkflow",
        1,
    )[0]

    checking = '=== "checking"'
    unavailable = '=== "error"'
    ambiguous = "currentControlledWorkflowAmbiguous"
    active = 'currentControlledWorkflow?.packet.decision === "test"'
    advisory = 'short: "Advisory"'
    assert signal.index(checking) < signal.index(unavailable) < signal.index(ambiguous) < signal.index(active) < signal.index(advisory)
    assert 'tone: "loading", short: "Checking"' in signal
    assert 'tone: "blocked"' in signal
    assert 'short: "Unavailable"' in signal
    assert "Open Dial-In and retry before starting or resuming a workflow" in signal

    ribbon = app.split("<RunContextBar", 1)[1].split("{currentIntelligenceShellMove", 1)[0]
    assert 'currentControlledWorkflow?.packet.decision === "test"' in ribbon
    assert "activeControlledWorkflow?.packet.decision" not in ribbon

