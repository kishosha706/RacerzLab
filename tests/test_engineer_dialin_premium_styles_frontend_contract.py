from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_engineer_and_dial_in_mission_styles_are_stateful_compact_and_accessible() -> None:
    styles = (ROOT / "ui/src/styles.css").read_text(encoding="utf-8")
    mission_styles = styles.split("/* Engineer + Dial-In mission surfaces */", 1)[1]

    for selector in (
        ".engineer-mission-command",
        ".engineer-smart-command",
        ".engineer-smart-why",
        ".engineer-smart-primary",
        ".engineer-smart-section-label",
        ".engineer-smart-recovery",
        ".engineer-mission-progress",
        ".engineer-quality-recovery",
        ".engineer-measurement-checklist",
        ".engineer-measurement-guardrails",
        ".engineer-briefing-why",
        ".engineer-evidence-trail",
        ".dialin-workflow-progress",
        ".dialin-workflow-mission",
        ".dialin-stage-mark",
        ".dialin-workflow-coaching",
        ".dialin-measurement-mission",
        ".dialin-mission-checklist",
        ".dialin-mission-guardrails",
        ".dialin-exact-change",
        ".dialin-test-guardrails",
    ):
        assert selector in mission_styles

    for state_selector in (
        '[data-mission-stage="qualify"]',
        '[data-move-kind="controlled_test"]',
        '[data-priority="1"]',
        '[data-status="planned"]',
        '[data-stage="A2"]',
        '[data-state="current"]',
        '[data-authority="measurement-only"]',
        '[data-current-stage="B"]',
        '[data-completed-stages]',
    ):
        assert state_selector in mission_styles

    assert '.smart-engineer-workspace[data-mode="race"]' in mission_styles
    assert "@media (max-width: 1080px)" in mission_styles
    assert "@media (max-width: 900px)" in mission_styles
    assert "@media (max-width: 720px)" in mission_styles
    assert "@media (prefers-reduced-motion: reduce)" in mission_styles
    reduced_motion = mission_styles.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "transition: none !important" in reduced_motion
    assert "animation: none !important" in reduced_motion
