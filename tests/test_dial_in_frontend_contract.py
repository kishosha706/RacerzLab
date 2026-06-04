from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_setup_tab_no_longer_owns_full_dial_in_panel() -> None:
    setup_tab = (PROJECT_ROOT / "ui/src/tabs/SetupTab.tsx").read_text(encoding="utf-8")
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "analyzeRunDialIn" not in setup_tab
    assert "Crew Chief Dial-In" not in setup_tab
    assert "analyzeRunDialIn" in dial_in_tab
    assert "Crew Chief Dial-In" in dial_in_tab


def test_dial_in_tab_requests_nine_swings_without_debug_evidence() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "const DIAL_IN_LIMIT = 9" in dial_in_tab
    assert "limit: DIAL_IN_LIMIT" in dial_in_tab
    assert "include_debug_evidence: false" in dial_in_tab


def test_dial_in_tab_uses_backend_target_labels() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")

    assert "const TARGET_LABELS" not in dial_in_tab
    assert "validate_with_labels" in dial_in_tab
    assert "watch_for_labels" in dial_in_tab
    assert "validate_with_labels" in telemetry_types
    assert "watch_for_labels" in telemetry_types
