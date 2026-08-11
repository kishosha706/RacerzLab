from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api.routes_compare import CompareRequest, InsightsRequest
from racelab_engine.analysis.comparison import TestDisciplineResult
from racelab_engine.analysis.confidence_weighted_verdict import ConfidenceWeightedObservation
from racelab_engine.analysis.target_zone_classifier import TargetZoneClassification as AnalysisClassification
from racelab_engine.models.comparison_insights import (
    ConfidenceWeightedObservation as PublicWeightedObservation,
    ComparisonInsightsResponse,
    TargetZoneClassification,
    TraceAnnotation,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "removed_field",
    ["verdict", "next_step", "recommendation", "final_recommendation"],
)
def test_compare_requests_reject_removed_authority_fields(removed_field: str) -> None:
    payload = {
        "baseline_run_id": "baseline",
        "test_run_id": "test",
        removed_field: "change the setup",
    }

    with pytest.raises(ValidationError):
        CompareRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        InsightsRequest.model_validate(payload)


def test_removed_dataclass_authority_fields_are_not_accepted() -> None:
    with pytest.raises(TypeError):
        TestDisciplineResult(  # type: ignore[call-arg]
            score=80,
            label="clean",
            recommendation="change a control",
        )
    with pytest.raises(TypeError):
        AnalysisClassification(  # type: ignore[call-arg]
            gain_class="inconclusive",
            label="Observed only",
            confidence=0.1,
            recommendation="change a control",
        )
    with pytest.raises(TypeError):
        ConfidenceWeightedObservation(  # type: ignore[call-arg]
            observation_state="inconclusive",
            base_confidence=0.1,
            adjusted_confidence=0.1,
            tier="low",
            recommendation="change a control",
        )
    with pytest.raises(TypeError):
        TraceAnnotation(  # type: ignore[call-arg]
            id="a1",
            kind="speed_gain",
            label="Measured speed",
            description="Observed telemetry only",
            lap_pct=50.0,
            distance_ft=None,
            channel="speed_mph",
            value=0.2,
            severity="info",
            confidence=0.5,
            recommendation="change a control",
        )
    with pytest.raises(TypeError):
        TargetZoneClassification(  # type: ignore[call-arg]
            classification="inconclusive",
            confidence=0.1,
            headline="Observed only",
            recommendation="change a control",
        )
    with pytest.raises(TypeError):
        PublicWeightedObservation(  # type: ignore[call-arg]
            observation_state="inconclusive",
            adjusted_confidence=0.1,
            confidence_tier="low",
            final_recommendation="change a control",
        )


def test_compare_insight_serialization_has_observation_only_contract() -> None:
    payload = ComparisonInsightsResponse(
        comparison_id="cmp",
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=1,
        test_lap=2,
        target_zone_start_pct=55.0,
        target_zone_end_pct=70.0,
        confidence_weighted_observation=PublicWeightedObservation(
            observation_state="observed_improvement",
            adjusted_confidence=0.7,
            confidence_tier="high",
        ),
    ).as_dict()

    assert payload["confidence_weighted_observation"]["observation_state"] == "observed_improvement"
    serialized = repr(payload)
    assert "confidence_weighted_verdict" not in serialized
    assert "original_verdict" not in serialized
    assert "final_recommendation" not in serialized
    assert "recommendation" not in serialized


def test_compare_ui_types_have_no_removed_authority_contract() -> None:
    types = (ROOT / "ui/src/types/compare.ts").read_text(encoding="utf-8")
    compare = (ROOT / "ui/src/tabs/CompareTab.tsx").read_text(encoding="utf-8")

    compare_types = types.split("// -- Notebook types", maxsplit=1)[0]
    assert "ComparisonObservation" in compare_types
    assert "observation_state" in compare_types
    assert "DidItWorkVerdict" not in compare_types
    assert "next_step" not in compare_types
    assert "final_recommendation" not in compare_types
    assert "recommendation:" not in compare_types
    assert "result.verdict" not in compare
    assert "result.observation" in compare
