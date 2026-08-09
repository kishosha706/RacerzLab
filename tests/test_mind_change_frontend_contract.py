from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mind_change_card_rejects_hostile_scope_and_candidate_state() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")
    exact = cards.split("export function exactMindChangeCriteria", 1)[1].split(
        "function missionStagePresentation",
        1,
    )[0]

    assert "criterion.run_id !== runId" in exact
    assert "(criterion.session_id ?? null) !== sessionId" in exact
    assert "cause.state !== criterion.current_state" in exact
    assert "seenCriterionIds.has(criterion.criterion_id)" in exact
    assert "canonicalUniqueTextList(criterion.acceptance_conditions, false)" in exact
    assert "canonicalUniqueTextList(criterion.falsification_conditions, false)" in exact
    assert "canonicalUniqueTextList(criterion.countereffects, true)" in exact
    assert "canonicalUniqueTextList(criterion.source_event_ids, true)" in exact
    assert "minimumUnits < 2" in exact
    assert "minimumUnits < 9" in exact
    assert "(minimumLaps ?? 0) < 3" in exact
    assert "left.cause.rank - right.cause.rank" in exact

    report_scope = cards.split("const mindChangeCriteria =", 1)[1].split(
        "const telemetryHealth",
        1,
    )[0]
    assert "report.run_id === runId" in report_scope
    assert "(report.session_id ?? null) === sessionId" in report_scope
    assert "report.mind_change_criteria" in report_scope
    assert "report.competing_causes" in report_scope


def test_mind_change_card_is_complete_reasoning_without_setup_authority() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")
    card = cards.split("export function MindChangeCriteriaCard", 1)[1].split(
        "function OvalCrewBoard",
        1,
    )[0]

    assert "learning ? criteria : criteria.slice(0, 1)" in card
    assert "const acceptance = criterion.acceptance_conditions" in card
    assert "const falsification = criterion.falsification_conditions" in card
    assert "const countereffects = criterion.countereffects" in card
    assert ".acceptance_conditions.slice" not in card
    assert ".falsification_conditions.slice" not in card
    assert ".countereffects.slice" not in card

    for copy in (
        "What changes the call",
        "Current candidate",
        "Phase",
        "Metric",
        "Accept this candidate if",
        "Falsify this candidate if",
        "Minimum proof",
        "A/B/A2 required",
        "independent evidence units",
        "Countereffects to protect",
        "Accepted",
        "Falsified",
        "Inconclusive",
        "Reasoning only · no setup authority",
        "cannot choose a setup value, start a test, or advance a workflow",
    ):
        assert copy in card

    assert 'data-authority="reasoning-only"' in card
    assert 'data-setup-authorized="false"' in card
    assert "setupActionAuthorized" not in card
    assert "trustedSetupAuthorizedMove" not in card
    assert "<button" not in card


def test_mind_change_card_is_semantic_and_visible_in_both_modes() -> None:
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    card = cards.split("export function MindChangeCriteriaCard", 1)[1].split(
        "function OvalCrewBoard",
        1,
    )[0]

    assert "aria-labelledby={headingId}" in card
    assert 'role="list"' in card
    assert 'role="listitem"' in card
    assert "Acceptance conditions for ${cause.label}" in card
    assert "Falsification conditions for ${cause.label}" in card
    assert "Minimum independent evidence for ${cause.label}" in card
    assert "Deterministic next states for ${cause.label}" in card
    assert "Countereffects for ${cause.label}" in card
    assert '<dl className="engineer-mind-change-states"' in card

    report_card = '<MindChangeCriteriaCard\n        criteria={mindChangeCriteria}'
    assert report_card in cards
    assert cards.rindex(report_card) < cards.rindex("<OvalCrewBoard")
    assert 'headingId="engineer-report-mind-change-heading"' in cards
    assert 'scopeLabel="Current run"' in cards

    assert "queryResponse.mind_change_criteria" in engineer
    assert "report.competing_causes" in engineer
    assert "!queryResponse.clarification_required" in engineer
    assert "!queryResponse.action_authorized" in engineer
    assert 'headingId="engineer-query-mind-change-heading"' in engineer
    assert 'scopeLabel="Run-scoped reasoning"' in engineer
    assert "What would change your mind?" in engineer
    query_gate = engineer.split("const queryActionTrusted = Boolean(", 1)[1].split(
        "const queryNavigationCitations",
        1,
    )[0]
    assert "mind_change" not in query_gate


def test_mind_change_styles_are_responsive_and_not_color_only() -> None:
    styles = _read("ui/src/styles.css")
    mission_styles = styles.split("/* Engineer + Dial-In mission surfaces */", 1)[1]

    for selector in (
        '.engineer-mind-change[data-authority="reasoning-only"]',
        ".engineer-mind-change-list",
        ".engineer-mind-change-criterion",
        ".engineer-mind-change-scope",
        ".engineer-mind-change-conditions",
        ".engineer-mind-change-minimum",
        ".engineer-mind-change-states",
        ".engineer-mind-change-countereffects",
        ".engineer-mind-change-guard",
    ):
        assert selector in mission_styles

    assert "repeat(auto-fit, minmax(min(100%, 360px), 1fr))" in mission_styles
    assert "overflow-wrap: anywhere" in mission_styles
    assert "@media (max-width: 1080px)" in mission_styles
    assert "@media (max-width: 720px)" in mission_styles
    mobile = mission_styles.split("@media (max-width: 720px)", 1)[1].split(
        "@media (forced-colors: active)",
        1,
    )[0]
    assert ".engineer-mind-change-scope" in mobile
    assert ".engineer-mind-change-conditions" in mobile
    assert ".engineer-mind-change-states" in mobile
    assert "@media (forced-colors: active)" in mission_styles
    forced_colors = mission_styles.split("@media (forced-colors: active)", 1)[1]
    assert ".engineer-mind-change" in forced_colors
    assert "border-color: CanvasText" in forced_colors
