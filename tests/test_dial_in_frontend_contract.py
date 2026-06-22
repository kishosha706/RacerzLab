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


def test_dial_in_tab_requests_extra_swings_without_reducing_initial_count() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "const DIAL_IN_INITIAL_LIMIT = 9" in dial_in_tab
    assert "const SHOW_MORE_STEP = 9" in dial_in_tab
    assert "const DIAL_IN_REQUEST_LIMIT = DIAL_IN_INITIAL_LIMIT + SHOW_MORE_STEP" in dial_in_tab
    assert "limit: DIAL_IN_REQUEST_LIMIT" in dial_in_tab
    assert "useState(DIAL_IN_INITIAL_LIMIT)" in dial_in_tab
    assert "response?.top_swings.slice(0, 3)" in dial_in_tab
    assert "response?.top_swings.slice(3, shownSwingCount)" in dial_in_tab
    assert "include_debug_evidence: false" in dial_in_tab


def test_dial_in_tab_reveals_more_swings_in_nine_swing_steps() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "remainingSwingCount" in dial_in_tab
    assert "nextRevealCount = Math.min(SHOW_MORE_STEP, remainingSwingCount)" in dial_in_tab
    assert "setShownSwingCount((count) => Math.min(count + SHOW_MORE_STEP, response.top_swings.length))" in dial_in_tab
    assert "Show {nextRevealCount} more setup changes" in dial_in_tab
    assert "dialin-show-more-row" in dial_in_tab
    assert "dialin-show-more-button" in dial_in_tab
    assert ".dialin-show-more-row" in styles
    assert ".dialin-show-more-button" in styles


def test_dial_in_tab_uses_backend_target_labels() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")

    assert "const TARGET_LABELS" not in dial_in_tab
    assert "garageLeverLabel" in dial_in_tab
    assert "Garage control:" in dial_in_tab
    assert "dialin-garage-helper" in dial_in_tab
    assert "validate_with_labels" in dial_in_tab
    assert "watch_for_labels" in dial_in_tab
    assert "validate_with_labels" in telemetry_types
    assert "watch_for_labels" in telemetry_types


def test_dial_in_cards_render_exact_change_this_and_garage_lever() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    telemetry_types = (PROJECT_ROOT / "ui/src/types/telemetry.ts").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    assert "change_this: string" in telemetry_types
    assert "garage_lever: string" in telemetry_types
    assert "dialin-change-this" in dial_in_tab
    assert "Make this setup change:" in dial_in_tab
    assert "{swing.change_this}" in dial_in_tab
    assert "Garage control: {swing.garage_lever}" in dial_in_tab
    assert ".dialin-change-this" in styles
    assert ".dialin-garage-note" in styles


def test_dial_in_tab_uses_direct_setup_change_vocabulary() -> None:
    dial_in_tab = (PROJECT_ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")

    assert "rank specific setup changes to test" in dial_in_tab
    assert "Pick one change. Just one." in dial_in_tab
    assert "Best first setup changes" in dial_in_tab
    assert "Other setup changes" in dial_in_tab
    assert "Expected effect" in dial_in_tab
    assert "Trade-off" in dial_in_tab
    assert "Test exactly this" in dial_in_tab
    assert "Validate with" in dial_in_tab
    assert "Small setup change" in dial_in_tab

    for vague_phrase in [
        "Feel polish",
        "Balance shift",
        "Possible swings",
        "Best first swings",
        "Other possible swings",
        "setup swings to test",
        "What to watch for",
        "Your Next Test",
    ]:
        assert vague_phrase not in dial_in_tab
