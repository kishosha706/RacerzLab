"""Fail-closed pseudoreplication and split-leakage firewall."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field

from racelab_engine.evaluation.dataset_registry import (
    EvidenceDataset,
    EvidenceLabModel,
    IndependenceLevel,
)
from racelab_engine.evaluation.split_policy import DatasetSplitPolicy


_LEVEL_ORDER = {
    IndependenceLevel.WINDOW: 0,
    IndependenceLevel.LAP: 1,
    IndependenceLevel.STINT: 2,
    IndependenceLevel.RUN: 3,
    IndependenceLevel.CONTROLLED_WORKFLOW: 4,
    IndependenceLevel.SESSION: 5,
    IndependenceLevel.DRIVER: 6,
    IndependenceLevel.TRACK: 6,
    IndependenceLevel.BUILD: 6,
}


class LeakageFinding(EvidenceLabModel):
    code: str = Field(min_length=1)
    severity: Literal["warning", "invalid"]
    message: str = Field(min_length=1)
    unit_ids: tuple[str, ...] = ()
    partitions: tuple[str, ...] = ()


class LeakageReport(EvidenceLabModel):
    dataset_id: str
    dataset_hash: str
    split_policy_id: str
    valid: bool
    findings: tuple[LeakageFinding, ...]
    reported_independence_units: int = Field(ge=0)
    effective_independence_units: int = Field(ge=0)


def evaluate_dataset_leakage(
    dataset: EvidenceDataset,
    policy: DatasetSplitPolicy,
) -> LeakageReport:
    findings: list[LeakageFinding] = []
    unit_by_id = {unit.unit_id: unit for unit in dataset.units}
    partitions_by_unit: dict[str, set[str]] = defaultdict(set)
    for split in dataset.splits:
        for unit_id in split.unit_ids:
            partitions_by_unit[unit_id].add(split.partition)

    for unit_id, partitions in partitions_by_unit.items():
        if len(partitions) > 1:
            findings.append(
                _invalid(
                    "unit_crosses_partitions",
                    "The same independence unit appears in multiple partitions.",
                    (unit_id,),
                    tuple(sorted(partitions)),
                )
            )
    if dataset.splits:
        missing = tuple(sorted(set(unit_by_id) - set(partitions_by_unit)))
        if missing:
            findings.append(
                _invalid(
                    "units_missing_from_split",
                    "Registered units are absent from the frozen split.",
                    missing,
                )
            )

    for unit in dataset.units:
        if _level_rank(unit.independence_level) < _level_rank(
            policy.required_independence_level
        ):
            findings.append(
                _invalid(
                    "independence_level_too_fine",
                    f"{unit.independence_level.value} cannot satisfy a "
                    f"{policy.required_independence_level.value}-level evaluation.",
                    (unit.unit_id,),
                )
            )

    _detect_shared_identity(
        findings,
        dataset,
        partitions_by_unit,
        "source_file_fingerprints",
        "duplicate_source_file",
        "A source file fingerprint is represented by multiple independence units.",
        always_invalid=policy.preserve_source_files,
    )
    _detect_shared_identity(
        findings,
        dataset,
        partitions_by_unit,
        "source_workflow_ids",
        "workflow_split_or_duplicated",
        "A/B/A2 workflow identity is split or counted more than once.",
        always_invalid=policy.preserve_workflows,
    )
    _detect_shared_identity(
        findings,
        dataset,
        partitions_by_unit,
        "source_artifact_ids",
        "artifact_split_or_duplicated",
        "The same source artifact appears in multiple independence units.",
        always_invalid=policy.preserve_artifact_lineage,
    )

    grouping_attribute = {
        "whole_session": "source_session_ids",
        "whole_workflow": "source_workflow_ids",
        "whole_stint": "source_stint_ids",
        "leave_driver_out": "driver_ids",
        "leave_track_out": "track_ids",
        "leave_build_out": "build_ids",
    }.get(policy.kind)
    if grouping_attribute:
        _detect_cross_partition_group(
            findings,
            dataset,
            partitions_by_unit,
            grouping_attribute,
            policy.kind,
        )

    _detect_derived_lineage(findings, dataset, partitions_by_unit, policy)
    _detect_adjacent_pseudoreplication(findings, dataset)
    _warn_context_collisions(findings, dataset, partitions_by_unit)

    if policy.real_world_activation_required and not any(
        not unit.synthetic for unit in dataset.units
    ):
        findings.append(
            _invalid(
                "synthetic_only_activation",
                "Synthetic units cannot satisfy a real-world activation requirement.",
                tuple(unit_by_id),
            )
        )
    invalid_unit_ids = {
        unit_id
        for finding in findings
        if finding.severity == "invalid"
        for unit_id in finding.unit_ids
    }
    valid = not any(finding.severity == "invalid" for finding in findings)
    return LeakageReport(
        dataset_id=dataset.dataset_id,
        dataset_hash=dataset.dataset_hash,
        split_policy_id=policy.policy_id,
        valid=valid,
        findings=tuple(findings),
        reported_independence_units=len(dataset.units),
        effective_independence_units=len(dataset.units) - len(invalid_unit_ids),
    )


def _level_rank(level: IndependenceLevel) -> int:
    if level is IndependenceLevel.SAMPLE:
        return -1
    return _LEVEL_ORDER[level]


def _unit_partitions(
    unit_ids: tuple[str, ...],
    partitions_by_unit: dict[str, set[str]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                partition
                for unit_id in unit_ids
                for partition in partitions_by_unit.get(unit_id, set())
            }
        )
    )


def _detect_shared_identity(
    findings: list[LeakageFinding],
    dataset: EvidenceDataset,
    partitions_by_unit: dict[str, set[str]],
    attribute: str,
    code: str,
    message: str,
    *,
    always_invalid: bool,
) -> None:
    units_by_value: dict[str, list[str]] = defaultdict(list)
    for unit in dataset.units:
        for value in getattr(unit, attribute):
            units_by_value[value].append(unit.unit_id)
    for unit_ids in units_by_value.values():
        unique_ids = tuple(dict.fromkeys(unit_ids))
        if len(unique_ids) < 2:
            continue
        partitions = _unit_partitions(unique_ids, partitions_by_unit)
        if always_invalid or len(partitions) > 1:
            findings.append(_invalid(code, message, unique_ids, partitions))


def _detect_cross_partition_group(
    findings: list[LeakageFinding],
    dataset: EvidenceDataset,
    partitions_by_unit: dict[str, set[str]],
    attribute: str,
    policy_kind: str,
) -> None:
    units_by_group: dict[str, list[str]] = defaultdict(list)
    for unit in dataset.units:
        for value in getattr(unit, attribute):
            units_by_group[value].append(unit.unit_id)
    for unit_ids in units_by_group.values():
        unique_ids = tuple(dict.fromkeys(unit_ids))
        partitions = _unit_partitions(unique_ids, partitions_by_unit)
        if len(partitions) > 1:
            findings.append(
                _invalid(
                    f"{policy_kind}_group_crosses_partitions",
                    f"A {policy_kind.replace('_', ' ')} group crosses partitions.",
                    unique_ids,
                    partitions,
                )
            )


def _detect_derived_lineage(
    findings: list[LeakageFinding],
    dataset: EvidenceDataset,
    partitions_by_unit: dict[str, set[str]],
    policy: DatasetSplitPolicy,
) -> None:
    if not policy.preserve_artifact_lineage:
        return
    unit_ids_by_artifact: dict[str, set[str]] = defaultdict(set)
    for unit in dataset.units:
        for artifact_id in unit.source_artifact_ids:
            unit_ids_by_artifact[artifact_id].add(unit.unit_id)
    for artifact in dataset.artifacts:
        child_units = unit_ids_by_artifact.get(artifact.artifact_id, set())
        for parent_id in artifact.derived_from_artifact_ids:
            related = tuple(
                sorted(child_units | unit_ids_by_artifact.get(parent_id, set()))
            )
            partitions = _unit_partitions(related, partitions_by_unit)
            if len(partitions) > 1:
                findings.append(
                    _invalid(
                        "derived_artifact_lineage_crosses_partitions",
                        "A derived artifact and its source lineage cross partitions.",
                        related,
                        partitions,
                    )
                )


def _detect_adjacent_pseudoreplication(
    findings: list[LeakageFinding],
    dataset: EvidenceDataset,
) -> None:
    by_run_lap: dict[tuple[str, int], list[str]] = defaultdict(list)
    by_window: dict[tuple[str, str], list[str]] = defaultdict(list)
    for unit in dataset.units:
        for run_id in unit.source_run_ids:
            for lap_number in unit.lap_numbers:
                by_run_lap[(run_id, lap_number)].append(unit.unit_id)
            for window_id in unit.window_ids:
                by_window[(run_id, window_id)].append(unit.unit_id)
    for unit_ids in (*by_run_lap.values(), *by_window.values()):
        unique_ids = tuple(dict.fromkeys(unit_ids))
        if len(unique_ids) > 1:
            findings.append(
                _invalid(
                    "adjacent_window_or_lap_pseudoreplication",
                    "One lap/window source is counted as multiple independent units.",
                    unique_ids,
                )
            )


def _warn_context_collisions(
    findings: list[LeakageFinding],
    dataset: EvidenceDataset,
    partitions_by_unit: dict[str, set[str]],
) -> None:
    for attribute, code, label in (
        ("setup_fingerprints", "setup_fingerprint_cross_split", "setup"),
        ("context_fingerprints", "context_fingerprint_cross_split", "context"),
    ):
        units_by_value: dict[str, list[str]] = defaultdict(list)
        for unit in dataset.units:
            for value in getattr(unit, attribute):
                units_by_value[value].append(unit.unit_id)
        for unit_ids in units_by_value.values():
            unique_ids = tuple(dict.fromkeys(unit_ids))
            partitions = _unit_partitions(unique_ids, partitions_by_unit)
            if len(partitions) > 1:
                findings.append(
                    LeakageFinding(
                        code=code,
                        severity="warning",
                        message=f"The same {label} fingerprint appears across partitions.",
                        unit_ids=unique_ids,
                        partitions=partitions,
                    )
                )


def _invalid(
    code: str,
    message: str,
    unit_ids: tuple[str, ...] = (),
    partitions: tuple[str, ...] = (),
) -> LeakageFinding:
    return LeakageFinding(
        code=code,
        severity="invalid",
        message=message,
        unit_ids=unit_ids,
        partitions=partitions,
    )


__all__ = ["LeakageFinding", "LeakageReport", "evaluate_dataset_leakage"]
