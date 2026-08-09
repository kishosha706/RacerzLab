from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_oval_briefings_share_a_responsive_visual_language() -> None:
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    for selector in (
        ".oval-run-brief",
        ".oval-run-brief-grid",
        ".oval-tire-readiness-row",
        ".setup-driver-snapshot",
        ".setup-driver-snapshot-grid",
        ".setup-one-change-guard",
        ".engineer-oval-crew-board",
        ".oval-crew-phase-strip",
        ".oval-crew-repeatability",
        ".platform-oval-checkpoint",
        ".platform-oval-checkpoint-grid",
        ".oval-compare-brief",
        ".oval-compare-facts",
    ):
        assert selector in styles

    assert '.context-tag-badge[data-readiness="long-run-review"]' in styles
    assert '.context-tag-badge[data-readiness="short-run"]' in styles
    assert '[data-driver-signal="long-run"]' in styles
    assert '[data-driver-signal="corner-priority"]' in styles
    assert "@media (max-width: 1280px)" in styles
    assert "@media (max-width: 1120px)" in styles
    assert "@media (max-width: 720px)" in styles


def test_visual_states_distinguish_observed_collecting_and_withheld() -> None:
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")

    for state in ("observed", "collecting", "withheld"):
        assert f'.oval-tire-readiness-row[data-state="{state}"]' in styles
    for state in ("single", "clear", "multiple", "withheld", "checking"):
        assert f'.setup-one-change-guard[data-one-change-state="{state}"]' in styles
    for state in ("observed", "repeatable", "coaching"):
        assert f'.oval-crew-phase-strip > li[data-state="{state}"]' in styles
