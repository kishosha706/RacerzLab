from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_speed_story_is_one_race_mode_brief_and_learning_exposes_full_chain() -> None:
    deck = (ROOT / "ui/src/components/CrewChiefCommandDeck.tsx").read_text(
        encoding="utf-8"
    )
    for label in (
        "OBSERVED",
        "ATTRIBUTION",
        "WHERE IT STARTS",
        "WHAT CARRIES",
        "DRIVER",
        "CAR",
        "SYSTEMS",
        "MEMORY",
        "STRONGEST CONTRADICTION",
        "NEXT · P19",
    ):
        assert label in deck
    for learning_surface in (
        "Time-loss ribbon",
        "Corner performance chain",
        "Driver / car separation",
        "Measured track demand",
        "Comparison context",
        "P20 / P26 performance bridge",
        "Objective envelope",
        "ENGINEERING MEMORY",
    ):
        assert learning_surface in deck
    assert "onFocusEvidence(evidence)" in deck
    assert deck.index("NEXT · P19") < deck.index("OBSERVED")


def test_client_requires_atomic_p32_identity_and_rejects_authority_smuggling() -> None:
    trust = (ROOT / "ui/src/utils/performanceIntelligenceTrust.js").read_text(
        encoding="utf-8"
    )
    crew_trust = (ROOT / "ui/src/utils/crewChiefResponseTrust.ts").read_text(
        encoding="utf-8"
    )
    types = (ROOT / "ui/src/types/performanceIntelligence.ts").read_text(
        encoding="utf-8"
    )
    for contract in (
        "p32.performance-intelligence.v1",
        "theoretical_is_guaranteed",
        "setup_authorized",
        "optimization_state",
        "p19_only",
        "measured_time_consequence",
        "component_context_state",
        "observed_direction",
        "attribution_state",
        "comparison_compatibility",
    ):
        assert contract in trust
        assert contract in types
    assert "p32_projection_sha256" in crew_trust
    assert "isPerformanceIntelligenceProjection" in crew_trust
    assert "objectiveId: scope.objectiveId" in crew_trust
    assert "opportunityEvidence: p32Evidence" in crew_trust
    assert 'value.schema_version !== "p33.crew-chief-workspace.v2"' in crew_trust


def test_crew_planner_begins_with_measured_time_before_component_relevance() -> None:
    service = (
        ROOT / "racelab_engine/services/crew_chief_service.py"
    ).read_text(encoding="utf-8")
    subgoal = service.split("def _subgoal(", 1)[1].split("def _driver_question(", 1)[0]
    assert subgoal.index('priorities.append("inspect_lap_time_opportunity")') < subgoal.index(
        'priorities.append("inspect_component_performance_link")'
    )
    assert "inspect_driver_vehicle_separation" in subgoal
