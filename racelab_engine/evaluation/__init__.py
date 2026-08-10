"""Offline, non-authoritative evidence evaluation infrastructure.

Nothing in this package may create setup, cause-ranking, planner, or policy
authority.  P19 and P20 remain the production authorities.
"""

from racelab_engine.evaluation.dataset_registry import (
    DatasetArtifact,
    DatasetManifest,
    DatasetQualification,
    DatasetSplit,
    DatasetUnit,
    EvidenceDataset,
    IndependenceLevel,
    build_evidence_dataset,
    get_evidence_dataset,
    list_evidence_datasets,
    register_evidence_dataset,
)

__all__ = [
    "DatasetArtifact",
    "DatasetManifest",
    "DatasetQualification",
    "DatasetSplit",
    "DatasetUnit",
    "EvidenceDataset",
    "IndependenceLevel",
    "build_evidence_dataset",
    "get_evidence_dataset",
    "list_evidence_datasets",
    "register_evidence_dataset",
]
