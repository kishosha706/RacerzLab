from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class EngineeringMemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EngineeringEvidenceReference(EngineeringMemoryModel):
    kind: Literal["run", "workflow", "event", "channel", "setup", "lap"]
    reference_id: str = Field(min_length=1)


class PredictionContract(EngineeringMemoryModel):
    contract_id: str
    workflow_id: str
    created_at: datetime
    source_run_id: str
    target_metric: str
    target_phase: str
    support: Literal["exact_context_model", "mechanism_evidence", "unavailable"]
    expected_direction: Literal["decrease", "increase"] | None = None
    expected_range_s: tuple[FiniteFloat, FiniteFloat] | None = None
    expected_mechanism: str | None = None
    success_thresholds: tuple[str, ...]
    stop_rule: str
    rollback_rule: str
    evidence_references: tuple[EngineeringEvidenceReference, ...]
    ordinal_evidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    score_basis: str
    score_is_probability: Literal[False] = False

    @model_validator(mode="after")
    def require_supported_prediction(self) -> PredictionContract:
        if self.support == "unavailable" and (
            self.expected_direction is not None or self.expected_range_s is not None
        ):
            raise ValueError("unsupported prediction contracts cannot publish a direction or range")
        if self.expected_range_s is not None:
            if self.support != "exact_context_model":
                raise ValueError("a numeric prediction range requires qualified exact-context history")
            lower, upper = self.expected_range_s
            if lower > upper:
                raise ValueError("prediction ranges must be ordered")
        return self


class PredictionGrade(EngineeringMemoryModel):
    grade_id: str
    contract_id: str
    workflow_id: str
    created_at: datetime
    prediction_contract_sha256: str
    actual_effect_s: FiniteFloat | None = None
    actual_direction: Literal["decrease", "increase", "inconclusive", "unavailable"]
    direction_result: Literal["matched", "missed", "inconclusive", "unavailable"]
    range_result: Literal["inside", "outside", "inconclusive", "unavailable"]
    grade_label: Literal[
        "matched_direction_and_range",
        "matched_direction",
        "missed_prediction",
        "inconclusive",
        "outcome_recorded_without_quantified_prediction",
        "not_gradable_protocol_invalid",
    ]
    workflow_verdict: Literal["keep", "undo", "retest", "invalid"]
    protocol_valid: bool
    protocol_evidence_score: float = Field(ge=0.0, le=100.0)
    score_basis: str = (
        "Ordinal controlled-test protocol/evidence score; not a calibrated probability."
    )
    score_is_probability: Literal[False] = False
    evidence_references: tuple[EngineeringEvidenceReference, ...]


class PredictionCalibrationSummary(EngineeringMemoryModel):
    scope_run_ids: tuple[str, ...]
    source_run_ids: tuple[str, ...]
    workflow_ids: tuple[str, ...]
    graded_predictions: int = Field(ge=0)
    matched_predictions: int = Field(ge=0)
    basis: str = (
        "Count of protocol-valid frozen predictions with an actually gradable direction; "
        "not a calibrated probability or forward-looking success estimate."
    )
    score_is_probability: Literal[False] = False


NarrativeEntryType = Literal[
    "complaint",
    "hypothesis",
    "measurement",
    "change",
    "outcome",
    "rollback",
    "learning",
]


class EngineeringNarrativeEntry(EngineeringMemoryModel):
    entry_id: str
    created_at: datetime
    scope_id: str
    session_id: str | None = None
    entry_type: NarrativeEntryType
    text: str
    run_ids: tuple[str, ...]
    workflow_id: str
    evidence_references: tuple[EngineeringEvidenceReference, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DriverPresentationObservation(EngineeringMemoryModel):
    observation_id: str
    created_at: datetime
    source_key: str
    profile_id: str
    driver_id: str
    context_key: str
    context_scope: dict[str, str]
    kind: Literal["explicit_preference", "symptom_observed", "controlled_test_outcome"]
    preferred_mode: Literal["race", "learning"] | None = None
    terminology_level: Literal["plain", "standard", "engineering"] | None = None
    canonical_symptom: str | None = None
    symptom_phrase: str | None = None
    protocol_valid: bool | None = None
    driver_match_score: float | None = Field(default=None, ge=0.0, le=1.0)
    run_id: str | None = None
    workflow_id: str | None = None


class RecurringSymptom(EngineeringMemoryModel):
    canonical_symptom: str
    observations: int = Field(ge=1)
    phrases: tuple[str, ...] = ()


class DriverPresentationProfile(EngineeringMemoryModel):
    profile_id: str
    driver_id: str
    context_key: str
    scope: dict[str, str]
    preferred_mode: Literal["race", "learning"] = "race"
    terminology_level: Literal["plain", "standard", "engineering"] = "standard"
    recurring_symptoms: tuple[RecurringSymptom, ...] = ()
    controlled_tests_completed: int = Field(ge=0)
    consistency_label: Literal[
        "unavailable",
        "insufficient_history",
        "consistent_in_controlled_tests",
        "mixed_in_controlled_tests",
    ]
    affects_evidence_eligibility: Literal[False] = False


__all__ = [
    "DriverPresentationObservation",
    "DriverPresentationProfile",
    "EngineeringEvidenceReference",
    "EngineeringNarrativeEntry",
    "NarrativeEntryType",
    "PredictionContract",
    "PredictionCalibrationSummary",
    "PredictionGrade",
    "RecurringSymptom",
]
