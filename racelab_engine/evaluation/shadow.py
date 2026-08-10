"""Non-authoritative shadow model, prediction, and prospective-outcome contracts."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash
from racelab_engine.storage.db import initialize_database


_PROHIBITED_AUTHORITY_KEYS = frozenset(
    {
        "cause_rank",
        "cause_probability",
        "setup_leverage",
        "setup_target",
        "exact_setup_value",
        "planner_authority",
        "keep_undo",
        "policy_verdict",
    }
)


class ShadowModelContract(EvidenceLabModel):
    model_id: str = Field(pattern=r"^shm-[0-9a-f]{20}$")
    model_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    created_at: datetime
    implementation_state: Literal[
        "blocked_prerequisites",
        "historical_shadow",
        "prospective_shadow",
    ]
    input_keys: tuple[str, ...] = Field(min_length=1)
    required_context_keys: tuple[str, ...] = Field(min_length=1)
    required_profile_fields: tuple[str, ...] = ()
    output_keys: tuple[str, ...] = Field(min_length=1)
    allowed_claims: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = Field(min_length=1)
    negative_control_ids: tuple[str, ...] = Field(min_length=1)
    ground_truth_types: tuple[str, ...] = Field(min_length=1)
    authority: Literal["shadow_only"] = "shadow_only"

    @model_validator(mode="after")
    def contract_has_no_authority_and_stable_identity(self) -> ShadowModelContract:
        for values, label in (
            (self.input_keys, "input"),
            (self.required_context_keys, "context"),
            (self.required_profile_fields, "profile field"),
            (self.output_keys, "output"),
            (self.allowed_claims, "allowed claim"),
            (self.forbidden_claims, "forbidden claim"),
            (self.negative_control_ids, "negative control"),
            (self.ground_truth_types, "ground truth"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"shadow {label} values must be unique")
        if _PROHIBITED_AUTHORITY_KEYS & set(self.output_keys):
            raise ValueError("shadow outputs cannot carry production authority")
        payload = self.model_dump(mode="json", exclude={"model_id", "model_hash"})
        expected = canonical_hash(payload)
        if self.model_hash != expected or self.model_id != f"shm-{expected[:20]}":
            raise ValueError("shadow-model identity does not match its content")
        return self


class ShadowPrediction(EvidenceLabModel):
    prediction_id: str = Field(pattern=r"^shp-[0-9a-f]{20}$")
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_id: str
    model_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: str
    predicted_at: datetime
    source_run_ids: tuple[str, ...]
    source_session_ids: tuple[str, ...]
    inputs: dict[str, float | int | str | bool | None]
    context: dict[str, float | int | str | bool | None]
    prediction: dict[str, float | int | str | bool | None]
    uncertainty: dict[str, float | int | None] | None = None
    ground_truth_available_at_prediction: bool = False
    evaluation_state: Literal["unscored"] = "unscored"
    prospective: bool
    authority: Literal["shadow_only"] = "shadow_only"

    @model_validator(mode="after")
    def prediction_is_prospective_safe_and_content_addressed(self) -> ShadowPrediction:
        keys = set(self.inputs) | set(self.context) | set(self.prediction)
        if _PROHIBITED_AUTHORITY_KEYS & keys:
            raise ValueError("shadow prediction payload contains a prohibited authority key")
        if self.prospective and self.ground_truth_available_at_prediction:
            raise ValueError("prospective predictions must precede ground truth")
        payload = self.model_dump(
            mode="json",
            exclude={"prediction_id", "prediction_hash"},
        )
        expected = canonical_hash(payload)
        if (
            self.prediction_hash != expected
            or self.prediction_id != f"shp-{expected[:20]}"
        ):
            raise ValueError("shadow-prediction identity does not match its content")
        return self


class ShadowOutcome(EvidenceLabModel):
    outcome_id: str = Field(pattern=r"^sho-[0-9a-f]{20}$")
    outcome_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_id: str
    prediction_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    outcome: dict[str, float | int | str | bool | None]
    ground_truth_type: str = Field(min_length=1)
    evidence_artifact_ids: tuple[str, ...] = Field(min_length=1)
    gradable: bool
    ungradable_reason: str | None = None

    @model_validator(mode="after")
    def outcome_is_explained_and_content_addressed(self) -> ShadowOutcome:
        if self.gradable == (self.ungradable_reason is not None):
            raise ValueError("shadow outcome gradability and reason disagree")
        if _PROHIBITED_AUTHORITY_KEYS & set(self.outcome):
            raise ValueError("shadow outcome cannot carry production authority")
        payload = self.model_dump(mode="json", exclude={"outcome_id", "outcome_hash"})
        expected = canonical_hash(payload)
        if self.outcome_hash != expected or self.outcome_id != f"sho-{expected[:20]}":
            raise ValueError("shadow-outcome identity does not match its content")
        return self


class ShadowEvaluation(EvidenceLabModel):
    model_id: str
    model_hash: str
    evaluation_artifact_id: str
    prediction_ids: tuple[str, ...]
    historical_units: int = Field(ge=0)
    prospective_units: int = Field(ge=0)
    metrics: dict[str, float | int | None]
    subgroup_failures: tuple[str, ...]
    activation_state: Literal[
        "locked_insufficient_data",
        "locked_failed_validation",
        "historical_shadow",
        "prospective_shadow",
    ]
    authority: Literal["shadow_only"] = "shadow_only"


class GeometryCorrectedWheelShadow(EvidenceLabModel):
    raw_left_speed_mps: float = Field(allow_inf_nan=False)
    raw_right_speed_mps: float = Field(allow_inf_nan=False)
    expected_left_speed_mps: float = Field(allow_inf_nan=False)
    expected_right_speed_mps: float = Field(allow_inf_nan=False)
    raw_disagreement_mps: float = Field(allow_inf_nan=False)
    geometry_expected_disagreement_mps: float = Field(allow_inf_nan=False)
    residual_disagreement_mps: float = Field(allow_inf_nan=False)
    output_key: Literal["geometry_corrected_wheel_disagreement_shadow"] = (
        "geometry_corrected_wheel_disagreement_shadow"
    )
    authority: Literal["shadow_only"] = "shadow_only"


class GravityCompensatedAccelerationShadow(EvidenceLabModel):
    raw_long_accel_mps2: float = Field(allow_inf_nan=False)
    raw_lat_accel_mps2: float = Field(allow_inf_nan=False)
    raw_vert_accel_mps2: float = Field(allow_inf_nan=False)
    compensated_long_accel_mps2: float = Field(allow_inf_nan=False)
    compensated_lat_accel_mps2: float = Field(allow_inf_nan=False)
    compensated_vert_accel_mps2: float = Field(allow_inf_nan=False)
    output_key: Literal["gravity_compensated_accel_shadow"] = (
        "gravity_compensated_accel_shadow"
    )
    authority: Literal["shadow_only"] = "shadow_only"


def build_shadow_model_contract(payload: dict[str, Any]) -> ShadowModelContract:
    if {"model_id", "model_hash"} & payload.keys():
        raise ValueError("shadow-model identity is derived")
    normalized = {
        "created_at": datetime.now(timezone.utc),
        "authority": "shadow_only",
        **payload,
    }
    identity_payload = ShadowModelContract.model_construct(
        model_id="shm-" + "0" * 20,
        model_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"model_id", "model_hash"})
    model_hash = canonical_hash(identity_payload)
    return ShadowModelContract(
        model_id=f"shm-{model_hash[:20]}",
        model_hash=model_hash,
        **normalized,
    )


def build_shadow_prediction(
    contract: ShadowModelContract,
    payload: dict[str, Any],
) -> ShadowPrediction:
    if {"prediction_id", "prediction_hash", "model_id", "model_hash", "version"} & (
        payload.keys()
    ):
        raise ValueError("shadow prediction identity is derived")
    normalized = {
        "model_id": contract.model_id,
        "model_hash": contract.model_hash,
        "version": contract.version,
        "predicted_at": datetime.now(timezone.utc),
        "uncertainty": None,
        "ground_truth_available_at_prediction": False,
        "evaluation_state": "unscored",
        "authority": "shadow_only",
        **payload,
    }
    missing_inputs = set(contract.input_keys) - set(normalized["inputs"])
    missing_context = set(contract.required_context_keys) - set(normalized["context"])
    unexpected_outputs = set(normalized["prediction"]) - set(contract.output_keys)
    if missing_inputs or missing_context or unexpected_outputs:
        raise ValueError("shadow prediction does not satisfy its frozen model contract")
    identity_payload = ShadowPrediction.model_construct(
        prediction_id="shp-" + "0" * 20,
        prediction_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"prediction_id", "prediction_hash"})
    prediction_hash = canonical_hash(identity_payload)
    return ShadowPrediction(
        prediction_id=f"shp-{prediction_hash[:20]}",
        prediction_hash=prediction_hash,
        **normalized,
    )


def build_shadow_outcome(
    prediction: ShadowPrediction,
    payload: dict[str, Any],
) -> ShadowOutcome:
    if {"outcome_id", "outcome_hash", "prediction_id", "prediction_hash"} & (
        payload.keys()
    ):
        raise ValueError("shadow outcome identity is derived")
    normalized = {
        "prediction_id": prediction.prediction_id,
        "prediction_hash": prediction.prediction_hash,
        "observed_at": datetime.now(timezone.utc),
        **payload,
    }
    if normalized["observed_at"] <= prediction.predicted_at:
        raise ValueError("shadow outcome must be observed after its prediction")
    identity_payload = ShadowOutcome.model_construct(
        outcome_id="sho-" + "0" * 20,
        outcome_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"outcome_id", "outcome_hash"})
    outcome_hash = canonical_hash(identity_payload)
    return ShadowOutcome(
        outcome_id=f"sho-{outcome_hash[:20]}",
        outcome_hash=outcome_hash,
        **normalized,
    )


def save_shadow_model_contract(
    contract: ShadowModelContract,
    *,
    db_path: str | Path | None = None,
) -> bool:
    return _save_immutable(
        table="shadow_model_contracts",
        identity_column="model_id",
        hash_column="model_hash",
        identity=contract.model_id,
        digest=contract.model_hash,
        columns=("model_key", "version", "created_at", "contract_json"),
        values=(
            contract.model_key,
            contract.version,
            contract.created_at.isoformat(),
            contract.model_dump_json(),
        ),
        parser=ShadowModelContract,
        db_path=db_path,
    )


def save_shadow_prediction(
    prediction: ShadowPrediction,
    *,
    db_path: str | Path | None = None,
) -> bool:
    return _save_immutable(
        table="shadow_predictions",
        identity_column="prediction_id",
        hash_column="prediction_hash",
        identity=prediction.prediction_id,
        digest=prediction.prediction_hash,
        columns=("model_id", "predicted_at", "prospective", "prediction_json"),
        values=(
            prediction.model_id,
            prediction.predicted_at.isoformat(),
            int(prediction.prospective),
            prediction.model_dump_json(),
        ),
        parser=ShadowPrediction,
        db_path=db_path,
    )


def append_shadow_outcome(
    outcome: ShadowOutcome,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            prediction_row = connection.execute(
                "SELECT prediction_hash FROM shadow_predictions WHERE prediction_id = ?",
                (outcome.prediction_id,),
            ).fetchone()
            if (
                prediction_row is None
                or prediction_row["prediction_hash"] != outcome.prediction_hash
            ):
                raise ValueError("shadow outcome does not match a stored prediction")
            existing_for_prediction = connection.execute(
                "SELECT outcome_hash, outcome_json FROM shadow_prediction_outcomes "
                "WHERE prediction_id = ?",
                (outcome.prediction_id,),
            ).fetchone()
            if existing_for_prediction is not None:
                if (
                    existing_for_prediction["outcome_hash"] == outcome.outcome_hash
                    and ShadowOutcome.model_validate_json(
                        existing_for_prediction["outcome_json"]
                    )
                    == outcome
                ):
                    return False
                raise ValueError("a shadow prediction outcome is immutable once recorded")
            connection.execute(
                "INSERT INTO shadow_prediction_outcomes "
                "(outcome_id, outcome_hash, prediction_id, observed_at, outcome_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    outcome.outcome_id,
                    outcome.outcome_hash,
                    outcome.prediction_id,
                    outcome.observed_at.isoformat(),
                    outcome.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def geometry_corrected_wheel_disagreement_shadow(
    *,
    vehicle_speed_mps: float,
    yaw_rate_rad_s: float,
    wheelbase_m: float,
    track_width_m: float,
    left_speed_mps: float,
    right_speed_mps: float,
) -> GeometryCorrectedWheelShadow:
    values = (
        vehicle_speed_mps,
        yaw_rate_rad_s,
        wheelbase_m,
        track_width_m,
        left_speed_mps,
        right_speed_mps,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("wheel-disagreement shadow inputs must be finite")
    if vehicle_speed_mps < 0.0 or wheelbase_m <= 0.0 or track_width_m <= 0.0:
        raise ValueError("validated positive speed geometry is required")
    # Wheelbase is a prerequisite for the complete vehicle geometry even though
    # the same-axle first-order path-speed difference is yaw-rate x track width.
    expected_left = vehicle_speed_mps - yaw_rate_rad_s * track_width_m / 2.0
    expected_right = vehicle_speed_mps + yaw_rate_rad_s * track_width_m / 2.0
    raw_disagreement = right_speed_mps - left_speed_mps
    expected_disagreement = expected_right - expected_left
    return GeometryCorrectedWheelShadow(
        raw_left_speed_mps=left_speed_mps,
        raw_right_speed_mps=right_speed_mps,
        expected_left_speed_mps=expected_left,
        expected_right_speed_mps=expected_right,
        raw_disagreement_mps=raw_disagreement,
        geometry_expected_disagreement_mps=expected_disagreement,
        residual_disagreement_mps=raw_disagreement - expected_disagreement,
    )


def gravity_compensated_acceleration_shadow(
    *,
    raw_long_accel_mps2: float,
    raw_lat_accel_mps2: float,
    raw_vert_accel_mps2: float,
    roll_rad: float,
    pitch_rad: float,
    gravity_mps2: float = 9.80665,
) -> GravityCompensatedAccelerationShadow:
    values = (
        raw_long_accel_mps2,
        raw_lat_accel_mps2,
        raw_vert_accel_mps2,
        roll_rad,
        pitch_rad,
        gravity_mps2,
    )
    if not all(math.isfinite(value) for value in values) or gravity_mps2 <= 0.0:
        raise ValueError("gravity-compensation shadow inputs must be finite")
    # Contract assumes validated x-forward, y-left, z-up body axes. The function
    # remains shadow-only and never overwrites the archived raw channels.
    gravity_long = -gravity_mps2 * math.sin(pitch_rad)
    gravity_lat = gravity_mps2 * math.sin(roll_rad) * math.cos(pitch_rad)
    gravity_vert = gravity_mps2 * math.cos(roll_rad) * math.cos(pitch_rad)
    return GravityCompensatedAccelerationShadow(
        raw_long_accel_mps2=raw_long_accel_mps2,
        raw_lat_accel_mps2=raw_lat_accel_mps2,
        raw_vert_accel_mps2=raw_vert_accel_mps2,
        compensated_long_accel_mps2=raw_long_accel_mps2 - gravity_long,
        compensated_lat_accel_mps2=raw_lat_accel_mps2 - gravity_lat,
        compensated_vert_accel_mps2=raw_vert_accel_mps2 - gravity_vert,
    )


def research_shadow_contracts(
    *,
    created_at: datetime | None = None,
) -> tuple[ShadowModelContract, ...]:
    timestamp = created_at or datetime.now(timezone.utc)
    return (
        build_shadow_model_contract(
            {
                "model_key": "shadow_body_sideslip_proxy",
                "version": "research-v1",
                "created_at": timestamp,
                "implementation_state": "blocked_prerequisites",
                "input_keys": ("steering", "speed", "yaw_rate"),
                "required_context_keys": (
                    "sampling_integrity",
                    "bank_gravity_treatment",
                ),
                "required_profile_fields": (
                    "body_axes",
                    "steering_conversion",
                    "wheelbase",
                ),
                "output_keys": ("shadow_body_sideslip_proxy",),
                "allowed_claims": ("shadow estimated lateral-state proxy",),
                "forbidden_claims": ("measured_sideslip", "setup_authority"),
                "negative_control_ids": ("vehicle_profile_missing",),
                "ground_truth_types": (
                    "synthetic_known_signal",
                    "external_reference_measurement",
                ),
            }
        ),
        build_shadow_model_contract(
            {
                "model_key": "gravity_compensated_accel_shadow",
                "version": "research-v1",
                "created_at": timestamp,
                "implementation_state": "blocked_prerequisites",
                "input_keys": (
                    "raw_long_accel",
                    "raw_lat_accel",
                    "raw_vert_accel",
                    "roll",
                    "pitch",
                ),
                "required_context_keys": ("gravity_convention",),
                "required_profile_fields": ("body_axes",),
                "output_keys": ("gravity_compensated_accel_shadow",),
                "allowed_claims": ("shadow acceleration with modeled gravity removed",),
                "forbidden_claims": ("available_grip", "friction_coefficient"),
                "negative_control_ids": ("profile_build_mismatch",),
                "ground_truth_types": (
                    "synthetic_known_signal",
                    "external_reference_measurement",
                ),
            }
        ),
        build_shadow_model_contract(
            {
                "model_key": "geometry_corrected_wheel_disagreement_shadow",
                "version": "research-v1",
                "created_at": timestamp,
                "implementation_state": "blocked_prerequisites",
                "input_keys": (
                    "vehicle_speed",
                    "yaw_rate",
                    "left_wheel_speed",
                    "right_wheel_speed",
                ),
                "required_context_keys": ("turn_geometry", "bank_state"),
                "required_profile_fields": (
                    "wheelbase",
                    "front_track_width",
                    "rear_track_width",
                    "wheel_speed_semantics",
                ),
                "output_keys": ("geometry_corrected_wheel_disagreement_shadow",),
                "allowed_claims": ("residual wheel/path-speed disagreement proxy",),
                "forbidden_claims": ("tire_force", "friction_coefficient"),
                "negative_control_ids": ("no_wheel_slip", "geometry_missing"),
                "ground_truth_types": (
                    "synthetic_known_signal",
                    "protocol_valid_intervention",
                ),
            }
        ),
    )


def _save_immutable(
    *,
    table: str,
    identity_column: str,
    hash_column: str,
    identity: str,
    digest: str,
    columns: tuple[str, ...],
    values: tuple[Any, ...],
    parser: type[EvidenceLabModel],
    db_path: str | Path | None,
) -> bool:
    allowed = {
        "shadow_model_contracts": "contract_json",
        "shadow_predictions": "prediction_json",
    }
    json_column = allowed.get(table)
    if json_column is None:
        raise ValueError("unsupported immutable shadow table")
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                f"SELECT {hash_column}, {json_column} FROM {table} "
                f"WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if row is not None:
                parsed = parser.model_validate_json(row[json_column])
                incoming = parser.model_validate_json(values[-1])
                if row[hash_column] != digest or parsed != incoming:
                    raise ValueError("immutable shadow identity collision")
                return False
            all_columns = (identity_column, hash_column, *columns)
            placeholders = ", ".join("?" for _ in all_columns)
            connection.execute(
                f"INSERT INTO {table} ({', '.join(all_columns)}) "
                f"VALUES ({placeholders})",
                (identity, digest, *values),
            )
        return True
    finally:
        connection.close()


__all__ = [
    "GeometryCorrectedWheelShadow",
    "GravityCompensatedAccelerationShadow",
    "ShadowEvaluation",
    "ShadowModelContract",
    "ShadowOutcome",
    "ShadowPrediction",
    "append_shadow_outcome",
    "build_shadow_model_contract",
    "build_shadow_outcome",
    "build_shadow_prediction",
    "geometry_corrected_wheel_disagreement_shadow",
    "gravity_compensated_acceleration_shadow",
    "research_shadow_contracts",
    "save_shadow_model_contract",
    "save_shadow_prediction",
]
