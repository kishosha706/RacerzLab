from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_legacy_compare_renders_observations_not_policy_or_next_actions() -> None:
    compare = _read("ui/src/tabs/CompareTab.tsx")
    card = _read("ui/src/components/DidItWorkCard.tsx")

    assert 'observation: "Observation"' in compare
    assert "onStageNextTest" not in compare
    assert "nextStep={v.next_step}" not in compare
    assert "observation.next_step" not in compare
    assert "Stage Next Test" not in card
    assert "Create Next Test" not in card
    assert "Open Setup" not in card
    assert "{nextStep" not in card
    assert "observed_improvement" in card
    assert "observed_regression" in card


def test_hostile_legacy_recommendation_fields_have_no_ui_renderer() -> None:
    insights = _read("ui/src/components/ComparisonInsightPanel.tsx")
    engineering = _read("ui/src/components/EngineeringSystemsComparison.tsx")

    assert "{tz.recommendation" not in insights
    assert "{cwv.final_recommendation" not in insights
    assert "{conclusion.recommendation" not in engineering
    assert "Observational comparison only" in insights


def test_legacy_compare_api_cannot_emit_or_persist_setup_policy() -> None:
    route = _read("api/routes_compare.py")

    assert "record_setup_response" not in route
    assert "get_recommendations" not in route
    assert "EvidenceState.CONTROLLED_TEST_EFFECT" not in route
    assert '"observation_state": observation.observation_state' in route
    assert '"next_step"' not in route
    assert '"final_recommendation"' not in route
    assert '"recommendation"' not in route
