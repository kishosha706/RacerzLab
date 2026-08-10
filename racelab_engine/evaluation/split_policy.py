"""Frozen split-policy contracts for evidence evaluation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import (
    EvidenceLabModel,
    IndependenceLevel,
    canonical_hash,
)


SplitPolicyKind = Literal[
    "whole_session",
    "whole_workflow",
    "whole_stint",
    "leave_driver_out",
    "leave_track_out",
    "leave_build_out",
    "chronological",
    "prospective",
]


class DatasetSplitPolicy(EvidenceLabModel):
    policy_id: str = Field(pattern=r"^dsp-[0-9a-f]{20}$")
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1)
    kind: SplitPolicyKind
    required_independence_level: IndependenceLevel
    real_world_activation_required: bool = True
    preserve_workflows: bool = True
    preserve_source_files: bool = True
    preserve_artifact_lineage: bool = True
    protected_context_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identity_matches_content(self) -> DatasetSplitPolicy:
        if len(self.protected_context_keys) != len(set(self.protected_context_keys)):
            raise ValueError("protected context keys must be unique")
        payload = self.model_dump(
            mode="json",
            exclude={"policy_id", "policy_hash"},
        )
        expected = canonical_hash(payload)
        if self.policy_hash != expected or self.policy_id != f"dsp-{expected[:20]}":
            raise ValueError("split-policy identity does not match its content")
        return self


def build_split_policy(payload: dict[str, Any]) -> DatasetSplitPolicy:
    if {"policy_id", "policy_hash"} & payload.keys():
        raise ValueError("split-policy identity is derived")
    normalized = {
        "real_world_activation_required": True,
        "preserve_workflows": True,
        "preserve_source_files": True,
        "preserve_artifact_lineage": True,
        "protected_context_keys": (),
        **payload,
    }
    policy_hash = canonical_hash(normalized)
    return DatasetSplitPolicy(
        policy_id=f"dsp-{policy_hash[:20]}",
        policy_hash=policy_hash,
        **normalized,
    )


__all__ = ["DatasetSplitPolicy", "SplitPolicyKind", "build_split_policy"]
