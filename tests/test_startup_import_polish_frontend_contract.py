from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_import_progress_is_stage_based_and_never_invents_a_percentage() -> None:
    panel = _read("ui/src/components/ImportPanel.tsx")

    assert "const IMPORT_STEPS" in panel
    assert "function importProgressIndex(" in panel
    assert 'aria-label="Import progress"' in panel
    assert 'aria-current={state === "active" ? "step" : undefined}' in panel
    assert 'data-state={state}' in panel
    assert ".ibt telemetry" in panel
    assert ".sto setup" not in panel
    assert ".mt2 track map" in panel
    assert "Local only" in panel
    assert "% complete" not in panel
    assert "Cached locally in the fast telemetry archive" in panel
    assert '{busy ? "Importing…" : "Import telemetry or track map"}' in panel


def test_import_surface_only_promises_supported_files_and_retry_is_reselectable() -> None:
    panel = _read("ui/src/components/ImportPanel.tsx")
    picker = _read("ui/src/utils/tauriImport.ts")
    app = _read("ui/src/App.tsx")

    assert 'accept=".ibt,.mt2"' in panel
    assert 'accept=".ibt,.sto,.mt2"' not in panel
    assert 'extensions: ["ibt"]' in picker
    assert 'extensions: ["ibt", "sto"]' not in picker
    assert 'input.value = "";' in panel
    assert 'input.value = "";' in app


def test_import_progress_never_marks_a_failed_or_map_only_flow_as_cockpit_complete() -> None:
    panel = _read("ui/src/components/ImportPanel.tsx")
    app = _read("ui/src/App.tsx")

    assert 'displayedError || displayedOutcome === "map"' in panel
    assert 'setNativeStatus(null);' in panel
    assert 'await completeImport(resp.run_id, resp.track_map ?? null);\n      setNativeStatus(resp.status.message);' in panel
    assert "const completed = await onImportComplete(runId, trackMap);" in panel
    assert "if (!completed)" in panel
    assert "if (!resp.run_id)" in panel
    assert "resp.status.message || \"The telemetry file could not be processed.\"" in panel
    assert "const importWasSaved = summary.some(" in panel
    assert "!importWasSaved && !details.some" in panel
    assert 'const [importOutcome, setImportOutcome] = useState<"run" | "map" | null>(null);' in app
    assert 'setImportOutcome("map");' in app
    assert 'setImportOutcome("run");' in app
    assert "): Promise<boolean> =>" in app
    assert "const opened = await loadSelectedRun(runId);" in app
    assert "Choose the same .ibt file again to retry the attachment." in app
    assert "The telemetry run was imported and saved, but the local session library could not refresh." in app
    assert "Technical detail: ${detail}" in app
    assert "You do not need to import it again." in app
    assert "onImportComplete={(runId, trackMap) => openImportedRun(" in app
    assert "if (opened) setSessionToolsOpen(false);" in app
    assert "return opened;" in app
    assert app.count("importOutcome={importOutcome}") == 2
