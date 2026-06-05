from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_laps_tab_includes_stint_intelligence_subview() -> None:
    source = (ROOT / "ui" / "src" / "tabs" / "LapsTab.tsx").read_text(encoding="utf-8")
    client = (ROOT / "ui" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    types = (ROOT / "ui" / "src" / "types" / "laps.ts").read_text(encoding="utf-8")

    assert '"stints"' in source
    assert "Stint Intelligence" in source
    assert "fetchStints" in source
    assert "compareStints" in source
    assert "bucketLabels.map" in source
    assert "L1-5" in source
    assert "L36-40" in source
    assert "stint-run-summary" in source
    assert "stint-window-card-row" in source
    assert "stint-selected-toolbar" in source
    assert "selectedStintId" in source
    assert "compactTrendLabel" in source
    assert "No eligible stint windows yet." in source
    assert "setWorkspace(\"compare\"" not in source
    stint_section = source.split('{subview === "stints" && (', 1)[1].split('{subview === "all_sessions" && (', 1)[0]
    assert "<th>Actions</th>" not in stint_section
    assert "export function fetchStints" in client
    assert "export interface StintSummary" in types
    assert "export interface StintBucket" in types
    assert "export interface StintRunSummary" in types
    assert "stint_rows" in types
    assert "best_window_cards" in types
    assert "run_summary" in types
    assert "primary_stints" in types
