from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_notebook_workspace_is_hidden_from_app_navigation() -> None:
    app = _read("ui/src/App.tsx")

    nav_block = app.split('<nav className="workspace-nav-rail"', 1)[1].split("</nav>", 1)[0]
    shortcut_block = app.split('<div className="shortcut-grid">', 1)[1].split("</div>", 1)[0]

    for label in [
        '["overview", "Overview", Gauge]',
        '["laps", "Laps", Clock]',
        '["platform_trace", "Platform", Layers]',
        '["setup_impact", "Setup", Wrench]',
        '["dial_in", "Dial-In", Crosshair]',
    ]:
        assert label in nav_block

    assert '["notebook", "Notebook"' not in nav_block
    assert "NotebookTab" not in app
    assert "<NotebookTab" not in app
    assert "Open Notebook" not in app
    assert "Open Notebook" not in shortcut_block
    assert "<span>N</span>" not in shortcut_block


def test_stale_notebook_workspace_normalizes_to_overview() -> None:
    selection = _read("ui/src/store/TelemetrySelectionContext.tsx")

    assert '"notebook"' in selection
    assert 'if (workspace === "notebook") return "overview";' in selection
    assert "normalizeWorkspace(saved as Workspace)" in selection
    assert "normalizeWorkspace(action.workspace)" in selection


def test_notebook_shortcut_no_longer_opens_hidden_workspace() -> None:
    shortcuts = _read("ui/src/hooks/useKeyboardShortcuts.ts")

    assert 'openWorkspace("notebook")' not in shortcuts
    assert 'case "n":' not in shortcuts
    assert 'case "N":' not in shortcuts


def test_visible_notebook_buttons_are_removed_from_primary_cockpit() -> None:
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    inspector = _read("ui/src/components/EvidenceInspector.tsx")
    priority = _read("ui/src/components/PriorityRail.tsx")
    next_best = _read("ui/src/components/NextBestClick.tsx")

    for source in [overview, platform, inspector, priority, next_best]:
        assert 'setWorkspace("notebook"' not in source
        assert 'workspace: "notebook"' not in source
        assert "Open Notebook" not in source
        assert "Add to Notebook" not in source
        assert "Create Test Note" not in source
        assert "Stage Test" not in source
