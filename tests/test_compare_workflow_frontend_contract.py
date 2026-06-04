from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compare_workspace_is_hidden_from_app_navigation() -> None:
    app = _read("ui/src/App.tsx")

    assert '"compare", "Compare"' not in app
    assert "CompareTab" not in app
    assert "GitCompare" not in app
    assert "Open Compare" not in app
    assert '"laps", "Laps"' in app


def test_stale_compare_workspace_redirects_to_laps() -> None:
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")

    assert 'workspace === "compare" ? "laps"' in selection
    assert "normalizeWorkspace(saved as Workspace)" in selection
    assert "normalizeWorkspace(action.workspace)" in selection


def test_test_basket_routes_to_laps_not_compare() -> None:
    basket = _read("ui/src/components/CompareBasket.tsx")

    assert 'setWorkspace("laps", "manual")' in basket
    assert "Test Basket" in basket
    assert "Review in Laps" in basket
    assert "Open Compare" not in basket
    assert "Ready to Compare" not in basket


def test_laps_owns_baseline_test_workflow_copy() -> None:
    laps = _read("ui/src/tabs/LapsTab.tsx")

    assert "Stint Intelligence" in laps
    assert "Baseline/Test Staging" in laps
    assert "Review Stint Compare" in laps
    assert "Open Stint Intelligence" in laps
    assert "Open Compare" not in laps
    assert "Compare Basket Staging" not in laps
