"""Field-level vehicle-profile validation and exact-build resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash
from racelab_engine.models.vehicle_engineering_profile import VersionRange
from racelab_engine.storage.db import initialize_database


ProfileField = Literal[
    "wheelbase",
    "front_track_width",
    "rear_track_width",
    "steering_conversion",
    "body_axes",
    "shock_sign_convention",
    "wheel_speed_semantics",
    "damper_bands",
    "ride_height_sensor_interpretation",
]
ProfileValidationState = Literal[
    "source_declared",
    "empirically_confirmed",
    "conflicted",
    "stale",
    "unavailable",
]


class ProfileValidationRecord(EvidenceLabModel):
    record_id: str = Field(pattern=r"^pvr-[0-9a-f]{20}$")
    record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    profile_id: str = Field(min_length=1)
    profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    car_path: str = Field(min_length=1)
    field: ProfileField
    state: ProfileValidationState
    source_id: str | None = None
    validation_method: str | None = None
    build_range: VersionRange
    last_validated_build: str | None = None
    evidence_artifact_ids: tuple[str, ...] = ()
    failure_or_revalidation_reason: str | None = None
    authority_ceiling: Literal["profile_field_only"] = "profile_field_only"

    @model_validator(mode="after")
    def record_is_fail_closed_and_content_addressed(self) -> ProfileValidationRecord:
        if len(self.evidence_artifact_ids) != len(set(self.evidence_artifact_ids)):
            raise ValueError("profile evidence artifact IDs must be unique")
        if self.state in {"source_declared", "empirically_confirmed"}:
            if not self.source_id or not self.validation_method or not self.last_validated_build:
                raise ValueError("usable profile states require source, method, and build")
            if not self.build_range.contains(self.last_validated_build):
                raise ValueError("last validated build is outside the declared range")
            if not self.evidence_artifact_ids:
                raise ValueError("usable profile states require evidence artifacts")
        if self.state in {"conflicted", "stale", "unavailable"} and not (
            self.failure_or_revalidation_reason
        ):
            raise ValueError("blocked profile states must explain the failure")
        payload = self.model_dump(
            mode="json",
            exclude={"record_id", "record_hash"},
        )
        expected = canonical_hash(payload)
        if self.record_hash != expected or self.record_id != f"pvr-{expected[:20]}":
            raise ValueError("profile-validation identity does not match its content")
        return self


class ProfileFieldResolution(EvidenceLabModel):
    profile_id: str
    profile_hash: str
    car_path: str
    build_id: str
    field: ProfileField
    status: Literal["ready", "blocked"]
    validation_state: ProfileValidationState | None = None
    source_record_id: str | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def resolution_is_fail_closed(self) -> ProfileFieldResolution:
        if self.status == "ready" and (
            self.validation_state != "empirically_confirmed"
            or not self.source_record_id
            or self.blocker_reasons
        ):
            raise ValueError("ready profile fields require empirical confirmation")
        if self.status == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked profile fields must explain their blocker")
        return self


def build_profile_validation_record(payload: dict[str, Any]) -> ProfileValidationRecord:
    if {"record_id", "record_hash"} & payload.keys():
        raise ValueError("profile-validation identity is derived")
    normalized = {
        "created_at": datetime.now(timezone.utc),
        "authority_ceiling": "profile_field_only",
        **payload,
    }
    normalized["build_range"] = VersionRange.model_validate(normalized["build_range"])
    identity_payload = ProfileValidationRecord.model_construct(
        record_id="pvr-" + "0" * 20,
        record_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"record_id", "record_hash"})
    record_hash = canonical_hash(identity_payload)
    return ProfileValidationRecord(
        record_id=f"pvr-{record_hash[:20]}",
        record_hash=record_hash,
        **normalized,
    )


def save_profile_validation_record(
    record: ProfileValidationRecord,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                "SELECT record_hash, record_json FROM profile_validation_records "
                "WHERE record_id = ?",
                (record.record_id,),
            ).fetchone()
            if row is not None:
                if (
                    row["record_hash"] != record.record_hash
                    or ProfileValidationRecord.model_validate_json(row["record_json"])
                    != record
                ):
                    raise ValueError("immutable profile-validation identity collision")
                return False
            connection.execute(
                "INSERT INTO profile_validation_records "
                "(record_id, record_hash, profile_id, profile_hash, car_path, "
                "field_key, state, created_at, record_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.record_id,
                    record.record_hash,
                    record.profile_id,
                    record.profile_hash,
                    record.car_path,
                    record.field,
                    record.state,
                    record.created_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def resolve_profile_field(
    *,
    profile_id: str,
    profile_hash: str,
    car_path: str,
    build_id: str,
    field: ProfileField,
    db_path: str | Path | None = None,
) -> ProfileFieldResolution:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT record_json FROM profile_validation_records "
            "WHERE profile_id = ? AND field_key = ? ORDER BY created_at DESC, record_id DESC",
            (profile_id, field),
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        return _blocked_resolution(
            profile_id,
            profile_hash,
            car_path,
            build_id,
            field,
            "No validation record exists for this profile field.",
        )
    records = tuple(ProfileValidationRecord.model_validate_json(row[0]) for row in rows)
    mismatched = [
        record
        for record in records
        if record.profile_hash != profile_hash or record.car_path != car_path
    ]
    if mismatched:
        return _blocked_resolution(
            profile_id,
            profile_hash,
            car_path,
            build_id,
            field,
            "Stored field history conflicts with the exact profile identity.",
        )
    applicable = [record for record in records if record.build_range.contains(build_id)]
    if not applicable:
        return _blocked_resolution(
            profile_id,
            profile_hash,
            car_path,
            build_id,
            field,
            "No field validation applies to this iRacing build.",
        )
    latest = applicable[0]
    if latest.state != "empirically_confirmed":
        return ProfileFieldResolution(
            profile_id=profile_id,
            profile_hash=profile_hash,
            car_path=car_path,
            build_id=build_id,
            field=field,
            status="blocked",
            validation_state=latest.state,
            source_record_id=latest.record_id,
            blocker_reasons=(
                latest.failure_or_revalidation_reason
                or f"Profile field is only {latest.state.replace('_', ' ')}.",
            ),
        )
    return ProfileFieldResolution(
        profile_id=profile_id,
        profile_hash=profile_hash,
        car_path=car_path,
        build_id=build_id,
        field=field,
        status="ready",
        validation_state=latest.state,
        source_record_id=latest.record_id,
    )


def _blocked_resolution(
    profile_id: str,
    profile_hash: str,
    car_path: str,
    build_id: str,
    field: ProfileField,
    reason: str,
) -> ProfileFieldResolution:
    return ProfileFieldResolution(
        profile_id=profile_id,
        profile_hash=profile_hash,
        car_path=car_path,
        build_id=build_id,
        field=field,
        status="blocked",
        blocker_reasons=(reason,),
    )


__all__ = [
    "ProfileField",
    "ProfileFieldResolution",
    "ProfileValidationRecord",
    "ProfileValidationState",
    "build_profile_validation_record",
    "resolve_profile_field",
    "save_profile_validation_record",
]
