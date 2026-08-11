from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_notebook_ui_cannot_render_hostile_legacy_authority_payload() -> None:
    notebook = _source("ui/src/tabs/NotebookTab.tsx")
    export = _source("ui/src/utils/exportUtils.ts")
    combined = notebook + export

    for access in (
        ".verdict",
        ".next_step",
        ".setup_changes",
        ".recommended_next_test",
        ".change_to_try",
        ".do_not_change",
        ".success_metric",
    ):
        assert access not in combined

    assert "/api/notebook/test-plans" not in notebook
    assert "/api/notebook/setup-memory" not in notebook
    assert "/test-plan" not in notebook
    assert "Use a P19 controlled" in notebook
    assert "not setup guidance" in export


def test_notebook_types_have_no_policy_memory_or_test_plan_contracts() -> None:
    types = _source("ui/src/types/compare.ts")
    notebook_types = types.split("// -- Notebook types", 1)[1]

    assert "export interface NotebookFinding" in notebook_types
    assert "export interface TestPlan" not in notebook_types
    assert "export interface SetupMemorySummary" not in notebook_types
    for field in (
        "verdict:",
        "next_step:",
        "setup_changes:",
        "recommended_next_test:",
        "change_to_try:",
    ):
        assert field not in notebook_types


def test_notebook_backend_has_no_policy_memory_or_test_plan_producer() -> None:
    routes = _source("api/routes_notebook.py")
    service = _source("racelab_engine/services/notebook_service.py")
    model = _source("racelab_engine/models/notebook.py")

    assert "create_test_plan" not in routes + service
    assert "list_test_plans" not in routes + service
    assert "build_setup_memory_summary" not in routes + service
    assert "class TestPlan" not in model
    assert "class SetupMemorySummary" not in model
    assert "verdict=req." not in routes
    assert "next_step=req." not in routes
    assert "setup_changes=req." not in routes
