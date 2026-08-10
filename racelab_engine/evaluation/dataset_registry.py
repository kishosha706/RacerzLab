"""Immutable, repository-owned P21 evidence dataset registry."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.storage.db import initialize_database


class EvidenceLabModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class IndependenceLevel(str, Enum):
    SAMPLE = "sample"
    WINDOW = "window"
    LAP = "lap"
    STINT = "stint"
    RUN = "run"
    CONTROLLED_WORKFLOW = "controlled_workflow"
    SESSION = "session"
    DRIVER = "driver"
    TRACK = "track"
    BUILD = "build"


DatasetKind = Literal[
    "schema_capability",
    "same_setup_repeatability",
    "controlled_aba",
    "long_run_tire",
    "driver_repeatability",
    "nearby_car_context",
    "vehicle_profile_validation",
    "shadow_observer_ground_truth",
    "null_no_change",
    "synthetic_injection",
    "historical_archive",
]
DatasetPartition = Literal["train", "calibration", "evaluation", "prospective"]
QualificationState = Literal["unqualified", "partially_qualified", "qualified"]
GroundTruthType = Literal[
    "none",
    "synthetic_known_signal",
    "same_setup_null",
    "protocol_valid_intervention",
    "source_declared_reference",
    "external_reference_measurement",
    "prospective_observed_outcome",
]


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DatasetArtifact(EvidenceLabModel):
    artifact_id: str = Field(min_length=1)
    artifact_kind: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_file_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    source_run_ids: tuple[str, ...] = ()
    derived_from_artifact_ids: tuple[str, ...] = ()
    artifact_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def references_are_unique(self) -> DatasetArtifact:
        _require_unique(self.source_run_ids, "artifact source run")
        _require_unique(self.derived_from_artifact_ids, "artifact lineage")
        if self.artifact_id in self.derived_from_artifact_ids:
            raise ValueError("an artifact cannot derive from itself")
        return self


class DatasetUnit(EvidenceLabModel):
    unit_id: str = Field(min_length=1)
    independence_level: IndependenceLevel
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_file_fingerprints: tuple[str, ...] = Field(min_length=1)
    source_run_ids: tuple[str, ...] = ()
    source_session_ids: tuple[str, ...] = ()
    source_workflow_ids: tuple[str, ...] = ()
    source_stint_ids: tuple[str, ...] = ()
    lap_numbers: tuple[int, ...] = ()
    window_ids: tuple[str, ...] = ()
    setup_fingerprints: tuple[str, ...] = ()
    context_fingerprints: tuple[str, ...] = ()
    driver_ids: tuple[str, ...] = ()
    track_ids: tuple[str, ...] = ()
    build_ids: tuple[str, ...] = ()
    synthetic: bool = False

    @model_validator(mode="after")
    def unit_is_traceable_and_not_row_inflated(self) -> DatasetUnit:
        for values, label in (
            (self.source_artifact_ids, "source artifact"),
            (self.source_file_fingerprints, "source file fingerprint"),
            (self.source_run_ids, "source run"),
            (self.source_session_ids, "source session"),
            (self.source_workflow_ids, "source workflow"),
            (self.source_stint_ids, "source stint"),
            (self.lap_numbers, "lap number"),
            (self.window_ids, "window"),
            (self.setup_fingerprints, "setup fingerprint"),
            (self.context_fingerprints, "context fingerprint"),
            (self.driver_ids, "driver"),
            (self.track_ids, "track"),
            (self.build_ids, "build"),
        ):
            _require_unique(values, label)
        if any(lap < 0 for lap in self.lap_numbers):
            raise ValueError("lap numbers must be non-negative")
        if self.independence_level is IndependenceLevel.SAMPLE:
            raise ValueError(
                "telemetry samples cannot be registered as independent evaluation units"
            )
        return self


class DatasetSplit(EvidenceLabModel):
    split_id: str = Field(min_length=1)
    partition: DatasetPartition
    unit_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def split_units_are_unique(self) -> DatasetSplit:
        _require_unique(self.unit_ids, "split unit")
        return self


class DatasetQualification(EvidenceLabModel):
    state: QualificationState
    exclusion_reasons: tuple[str, ...] = ()
    qualified_real_world_units: int = Field(ge=0)
    qualified_synthetic_units: int = Field(ge=0)

    @model_validator(mode="after")
    def qualification_is_fail_closed(self) -> DatasetQualification:
        if self.state == "qualified" and self.exclusion_reasons:
            raise ValueError("qualified datasets cannot retain exclusion reasons")
        if self.state != "qualified" and not self.exclusion_reasons:
            raise ValueError("unqualified datasets must explain their exclusions")
        return self


class DatasetManifest(EvidenceLabModel):
    schema_version: str = Field(min_length=1)
    source_run_ids: tuple[str, ...] = ()
    source_session_ids: tuple[str, ...] = ()
    source_workflow_ids: tuple[str, ...] = ()
    car_identities: tuple[str, ...] = ()
    track_identities: tuple[str, ...] = ()
    iracing_build_identities: tuple[str, ...] = ()
    vehicle_profile_hashes: tuple[str, ...] = ()
    analysis_artifact_versions: tuple[str, ...] = ()
    setup_identities: tuple[str, ...] = ()
    context_distribution: dict[str, int] = Field(default_factory=dict)
    lap_count: int = Field(ge=0)
    independence_unit_count: int = Field(ge=0)
    ground_truth_type: GroundTruthType
    allowed_evaluation_uses: tuple[str, ...] = ()
    forbidden_uses: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def manifest_counts_and_identities_are_canonical(self) -> DatasetManifest:
        for values, label in (
            (self.source_run_ids, "manifest source run"),
            (self.source_session_ids, "manifest source session"),
            (self.source_workflow_ids, "manifest source workflow"),
            (self.car_identities, "car identity"),
            (self.track_identities, "track identity"),
            (self.iracing_build_identities, "build identity"),
            (self.vehicle_profile_hashes, "profile hash"),
            (self.analysis_artifact_versions, "artifact version"),
            (self.setup_identities, "setup identity"),
            (self.allowed_evaluation_uses, "allowed use"),
            (self.forbidden_uses, "forbidden use"),
        ):
            _require_unique(values, label)
        if any(count < 0 or not key for key, count in self.context_distribution.items()):
            raise ValueError("context distribution requires named non-negative counts")
        return self


class EvidenceDataset(EvidenceLabModel):
    dataset_id: str = Field(pattern=r"^eds-[0-9a-f]{20}$")
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_kind: DatasetKind
    created_at: datetime
    manifest: DatasetManifest
    artifacts: tuple[DatasetArtifact, ...] = Field(min_length=1)
    units: tuple[DatasetUnit, ...] = Field(min_length=1)
    splits: tuple[DatasetSplit, ...] = ()
    qualification: DatasetQualification

    @model_validator(mode="after")
    def identity_and_references_are_immutable(self) -> EvidenceDataset:
        artifact_ids = [item.artifact_id for item in self.artifacts]
        unit_ids = [item.unit_id for item in self.units]
        split_ids = [item.split_id for item in self.splits]
        _require_unique(artifact_ids, "dataset artifact")
        _require_unique(unit_ids, "dataset unit")
        _require_unique(split_ids, "dataset split")
        known_artifacts = set(artifact_ids)
        if any(
            artifact_id not in known_artifacts
            for unit in self.units
            for artifact_id in unit.source_artifact_ids
        ):
            raise ValueError("dataset units reference an unknown artifact")
        if any(
            artifact_id not in known_artifacts
            for artifact in self.artifacts
            for artifact_id in artifact.derived_from_artifact_ids
        ):
            raise ValueError("artifact lineage references an unknown artifact")
        known_units = set(unit_ids)
        if any(unit_id not in known_units for split in self.splits for unit_id in split.unit_ids):
            raise ValueError("dataset splits reference an unknown unit")
        if self.manifest.independence_unit_count != len(self.units):
            raise ValueError("manifest independence count must equal registered units")
        real_units = sum(not unit.synthetic for unit in self.units)
        synthetic_units = len(self.units) - real_units
        if self.qualification.qualified_real_world_units > real_units:
            raise ValueError("qualified real-world unit count exceeds registered units")
        if self.qualification.qualified_synthetic_units > synthetic_units:
            raise ValueError("qualified synthetic unit count exceeds registered units")
        payload = self.model_dump(
            mode="json",
            exclude={"dataset_id", "dataset_hash"},
        )
        expected = canonical_hash(payload)
        if self.dataset_hash != expected or self.dataset_id != f"eds-{expected[:20]}":
            raise ValueError("dataset identity does not match its immutable content")
        return self


def build_evidence_dataset(payload: dict[str, Any]) -> EvidenceDataset:
    """Build a content-addressed dataset; identity is never caller controlled."""
    if {"dataset_id", "dataset_hash"} & payload.keys():
        raise ValueError("dataset identity is derived and cannot be caller-supplied")
    normalized = dict(payload)
    normalized.setdefault("created_at", datetime.now(timezone.utc))
    parsed = {
        **normalized,
        "manifest": DatasetManifest.model_validate(normalized["manifest"]),
        "artifacts": tuple(
            DatasetArtifact.model_validate(item) for item in normalized["artifacts"]
        ),
        "units": tuple(DatasetUnit.model_validate(item) for item in normalized["units"]),
        "splits": tuple(
            DatasetSplit.model_validate(item) for item in normalized.get("splits", ())
        ),
        "qualification": DatasetQualification.model_validate(
            normalized["qualification"]
        ),
    }
    identity_payload = EvidenceDataset.model_construct(
        dataset_id="eds-" + "0" * 20,
        dataset_hash="0" * 64,
        **parsed,
    ).model_dump(mode="json", exclude={"dataset_id", "dataset_hash"})
    dataset_hash = canonical_hash(identity_payload)
    return EvidenceDataset(
        dataset_id=f"eds-{dataset_hash[:20]}",
        dataset_hash=dataset_hash,
        **parsed,
    )


def register_evidence_dataset(
    dataset: EvidenceDataset,
    *,
    db_path: str | Path | None = None,
) -> bool:
    """Persist once. Identical replay is idempotent; mutation is rejected."""
    connection = initialize_database(db_path)
    try:
        with connection:
            existing = connection.execute(
                "SELECT dataset_hash, dataset_json FROM evidence_datasets "
                "WHERE dataset_id = ?",
                (dataset.dataset_id,),
            ).fetchone()
            serialized = dataset.model_dump_json()
            if existing is not None:
                if (
                    existing["dataset_hash"] != dataset.dataset_hash
                    or EvidenceDataset.model_validate_json(existing["dataset_json"])
                    != dataset
                ):
                    raise ValueError("immutable evidence dataset identity collision")
                return False
            connection.execute(
                "INSERT INTO evidence_datasets "
                "(dataset_id, dataset_hash, dataset_kind, created_at, dataset_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    dataset.dataset_id,
                    dataset.dataset_hash,
                    dataset.dataset_kind,
                    dataset.created_at.isoformat(),
                    serialized,
                ),
            )
        return True
    finally:
        connection.close()


def get_evidence_dataset(
    dataset_id: str,
    *,
    db_path: str | Path | None = None,
) -> EvidenceDataset | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT dataset_json FROM evidence_datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        return None if row is None else EvidenceDataset.model_validate_json(row[0])
    finally:
        connection.close()


def list_evidence_datasets(
    *,
    db_path: str | Path | None = None,
) -> tuple[EvidenceDataset, ...]:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT dataset_json FROM evidence_datasets "
            "ORDER BY created_at, dataset_id"
        ).fetchall()
        return tuple(EvidenceDataset.model_validate_json(row[0]) for row in rows)
    finally:
        connection.close()


def _require_unique(values: tuple[Any, ...] | list[Any], label: str) -> None:
    if len(values) != len(set(values)) or any(
        isinstance(value, str) and not value for value in values
    ):
        raise ValueError(f"{label} values must be non-empty and unique")


__all__ = [
    "DatasetArtifact",
    "DatasetKind",
    "DatasetManifest",
    "DatasetPartition",
    "DatasetQualification",
    "DatasetSplit",
    "DatasetUnit",
    "EvidenceDataset",
    "EvidenceLabModel",
    "GroundTruthType",
    "IndependenceLevel",
    "QualificationState",
    "build_evidence_dataset",
    "canonical_hash",
    "get_evidence_dataset",
    "list_evidence_datasets",
    "register_evidence_dataset",
]
