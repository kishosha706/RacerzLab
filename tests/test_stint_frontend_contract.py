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
    assert "compactTrendLabel" in source
    assert "No eligible stint windows yet." in source
    assert "setWorkspace(\"compare\"" not in source
    assert "export function fetchStints" in client
    assert "export interface StintSummary" in types
    assert "export interface StintBucket" in types
    assert "primary_stints" in types
