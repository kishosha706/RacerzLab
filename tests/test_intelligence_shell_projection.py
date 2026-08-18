from __future__ import annotations

import pytest
from pydantic import ValidationError

from api import routes_intelligence
from api.intelligence_schemas import IntelligenceShellProjectionResponse
from racelab_engine.models.smart_guidance import NextTrustworthyMove


def test_shell_projection_does_not_start_cold_intelligence(monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def peek(run_id: str, *, session_id: str | None = None):
        calls.append((run_id, session_id))
        return None

    monkeypatch.setattr(routes_intelligence, "peek_cached_run_intelligence", peek)
    projection = routes_intelligence.get_run_intelligence_shell(
        "run-alpha", "session-alpha"
    )

    assert calls == [("run-alpha", "session-alpha")]
    assert projection.status == "not_built"
    assert projection.next_trustworthy_move is None
    assert projection.reasoning_snapshot_sha256 is None


def test_ready_shell_projection_accepts_navigation_only_move() -> None:
    projection = IntelligenceShellProjectionResponse(
        schema_version="p19.intelligence-shell.v1",
        run_id="run-alpha",
        session_id="session-alpha",
        status="ready",
        reasoning_snapshot_sha256="a" * 64,
        next_trustworthy_move=NextTrustworthyMove(
            move_id="inspect:overview",
            kind="diagnose",
            title="Inspect the qualified observation",
            instruction="Open Overview to inspect the exact-run evidence.",
            reason="The cached report has one current navigation handoff.",
            workspace="overview",
            authority="navigation_only",
            run_id="run-alpha",
        ),
        recovery="Open the projected supporting view.",
    )
    assert projection.next_trustworthy_move is not None
    assert projection.next_trustworthy_move.authority == "navigation_only"


def test_shell_projection_rejects_setup_authority() -> None:
    setup_move = NextTrustworthyMove(
        move_id="test:workflow",
        kind="controlled_test",
        title="Controlled test",
        instruction="Open Dial-In to review the authorized card.",
        reason="P19 authorized one test.",
        workspace="dial_in",
        authority="setup_authorized",
        run_id="run-alpha",
        workflow_id="workflow-alpha",
        workflow_updated_at="2026-08-18T12:00:00Z",
        control_key="front_arb",
        source_event_ids=("event-alpha",),
    )
    with pytest.raises(ValidationError, match="navigation-only"):
        IntelligenceShellProjectionResponse(
            schema_version="p19.intelligence-shell.v1",
            run_id="run-alpha",
            session_id="session-alpha",
            status="ready",
            reasoning_snapshot_sha256="a" * 64,
            next_trustworthy_move=setup_move,
            recovery="Use the controlled-test ribbon.",
        )
