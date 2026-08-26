from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_engineering_case_strip_is_the_only_terminal_next_voice() -> None:
    mission = _read("ui/src/components/EngineeringMissionStrip.tsx")

    assert mission.count('<article className="mission-next"><span>Next</span>') == 1
    assert 'data-mode={isLearning ? "learning" : "race"}' in mission
    assert "{isLearning && <article><span>What</span>" in mission
    assert "{isLearning && <article><span>Why</span>" in mission
    assert "{isLearning && <article><span>Uncertain</span>" in mission

    for path in (
        "ui/src/tabs/OverviewTab.tsx",
        "ui/src/tabs/LapsTab.tsx",
        "ui/src/tabs/EngineerTab.tsx",
        "ui/src/tabs/PlatformTab.tsx",
        "ui/src/components/ControlledTestRibbon.tsx",
        "ui/src/components/SmartIntelligenceCards.tsx",
    ):
        source = _read(path)
        assert "<strong>What next:</strong>" not in source
        assert "Next trustworthy move" not in source
        assert "Open controlled test" not in source
        assert "Ask Engineer" not in source

    for path in (
        "ui/src/tabs/SetupTab.tsx",
        "ui/src/components/CrewChiefCommandDeck.tsx",
        "ui/src/components/EngineeringKnowledgeSpine.tsx",
        "ui/src/components/VehicleDynamicsBlackboard.tsx",
    ):
        source = _read(path)
        assert "<strong>What next:</strong>" not in source
        assert ">Next <strong>" not in source
        assert "NEXT · P19" not in source
        assert "BASELINE NEXT" not in source
        assert "MEMORY NEXT" not in source
        assert "NEXT INSPECTION" not in source
        assert "Work to next boundary" not in source

    setup = _read("ui/src/tabs/SetupTab.tsx")
    crew = _read("ui/src/components/CrewChiefCommandDeck.tsx")
    knowledge = _read("ui/src/components/EngineeringKnowledgeSpine.tsx")
    dynamics = _read("ui/src/components/VehicleDynamicsBlackboard.tsx")
    assert "Evidence route:" in setup and "Local handoff" in setup
    assert "Crew investigation status" in crew
    assert "P19 mission evidence · read-only mirror" in crew
    assert "P19 MISSION EVIDENCE · READ-ONLY MIRROR" in knowledge
    assert "P19 MISSION EVIDENCE" in dynamics


def test_supporting_surfaces_keep_evidence_status_and_neutral_navigation() -> None:
    overview = _read("ui/src/tabs/OverviewTab.tsx")
    laps = _read("ui/src/tabs/LapsTab.tsx")
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    platform = _read("ui/src/tabs/PlatformTab.tsx")
    ribbon = _read("ui/src/components/ControlledTestRibbon.tsx")
    cards = _read("ui/src/components/SmartIntelligenceCards.tsx")

    assert 'aria-label="Overview evidence status"' in overview
    assert "Evidence Collection Status" in overview
    assert 'aria-label="Laps pace evidence status"' in laps
    assert "Run evidence readiness" in laps
    assert "Engineering evidence status" in engineer
    assert "Authorized action evidence" in engineer
    assert "Review workflow evidence" in engineer
    assert 'aria-label="Platform evidence status and supporting views"' in platform
    assert "Open Engineer evidence" in platform
    assert "Status: {evidenceStatus.label}" in ribbon
    assert 'aria-label="Review controlled-test evidence"' in ribbon
    assert "Evidence handoff" in cards
    assert "Published evidence guidance" in cards
    assert "Review workflow evidence" in cards
