from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, get_args, get_origin

import pytest
from pydantic import BaseModel

from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    compile_next_gen_oval_runtime_trust_manifest,
)
from racelab_engine.models.vehicle_dynamics_knowledge import (
    MechanismSeparationRow,
    PhaseResponseMetric,
    PerformanceMechanismAssessment,
    PerformanceMechanismCandidate,
    VehicleDynamicsChainStage,
    VehicleDynamicsFocusArtifact,
    VehicleDynamicsInspectionToolId,
    VehicleProblemSignature,
    VehicleResponseObservation,
)
from racelab_engine.models.crew_chief import EngineeringEvidenceIndexEntry
from racelab_engine.models.engineering_projection import EngineeringAwarenessProjection


ROOT = Path(__file__).resolve().parents[1]


def _recursive_float_field_names(root: type[BaseModel]) -> set[str]:
    def unwrap(annotation: object) -> object:
        return (
            unwrap(get_args(annotation)[0])
            if get_origin(annotation) is Annotated
            else annotation
        )

    def contains_float(annotation: object) -> bool:
        normalized = unwrap(annotation)
        return normalized is float or any(
            contains_float(item) for item in get_args(normalized)
        )

    def nested_models(annotation: object) -> list[type[BaseModel]]:
        normalized = unwrap(annotation)
        values: list[type[BaseModel]] = []
        if isinstance(normalized, type) and issubclass(normalized, BaseModel):
            values.append(normalized)
        for item in get_args(normalized):
            values.extend(nested_models(item))
        return values

    pending = [root]
    seen: set[type[BaseModel]] = set()
    names: set[str] = set()
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, field in model.model_fields.items():
            if contains_float(field.annotation):
                names.add(name)
            pending.extend(nested_models(field.annotation))
    return names


def _typescript_string_set(source: str, name: str) -> set[str]:
    match = re.search(
        rf"const {name} = new Set\(\[(.*?)\]\);",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, f"missing canonical float-key set: {name}"
    return set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))


def test_p35_runtime_guard_rejects_forged_vehicle_dynamics_authority() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the P35 UI runtime contract test")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(ROOT / "ui/tests/vehicleDynamicsTrust.runtime.test.mjs"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p20_p35_and_evidence_digests_mirror_python_float_fields() -> None:
    crew_trust = (ROOT / "ui/src/utils/crewChiefResponseTrust.ts").read_text(
        encoding="utf-8"
    )
    dynamics_trust = (ROOT / "ui/src/utils/vehicleDynamicsTrust.ts").read_text(
        encoding="utf-8"
    )
    canonical = (ROOT / "ui/src/utils/canonicalJsonSha256.ts").read_text(
        encoding="utf-8"
    )

    p20_fields = _recursive_float_field_names(EngineeringAwarenessProjection)
    p20_fields.remove("build_duration_ms")
    assert _typescript_string_set(crew_trust, "p20ScientificFloatKeys") == p20_fields
    assert _typescript_string_set(
        crew_trust, "crewEvidenceIndexFloatKeys"
    ) == _recursive_float_field_names(EngineeringEvidenceIndexEntry)
    assert _typescript_string_set(
        dynamics_trust, "P35_PYTHON_FLOAT_KEYS"
    ) == _recursive_float_field_names(PerformanceMechanismAssessment)
    assert "canonicalJson(item, options, key)" in canonical


def test_p35_client_exact_key_lists_cannot_drift_from_public_models() -> None:
    trust = (ROOT / "ui/src/utils/vehicleDynamicsTrust.ts").read_text(
        encoding="utf-8"
    )
    types = (ROOT / "ui/src/types/vehicleDynamics.ts").read_text(encoding="utf-8")

    def exact_key_list(name: str) -> list[str]:
        match = re.search(
            rf"export const {name} = \[(.*?)\] as const;",
            trust,
            flags=re.DOTALL,
        )
        assert match is not None, f"missing P35 exact-key list: {name}"
        return re.findall(r'"([a-z0-9_]+)"', match.group(1))

    def type_fields(name: str) -> list[str]:
        match = re.search(
            rf"export type {name} = \{{(.*?)^\}};",
            types,
            flags=re.DOTALL | re.MULTILINE,
        )
        assert match is not None, f"missing P35 TypeScript type: {name}"
        return re.findall(r"^  ([a-z0-9_]+):", match.group(1), flags=re.MULTILINE)

    for key_list, type_name, model in (
        ("phaseResponseMetricKeys", "PhaseResponseMetric", PhaseResponseMetric),
        (
            "vehicleResponseObservationKeys",
            "VehicleResponseObservation",
            VehicleResponseObservation,
        ),
        (
            "vehicleProblemSignatureKeys",
            "VehicleProblemSignature",
            VehicleProblemSignature,
        ),
        (
            "mechanismSeparationRowKeys",
            "MechanismSeparationRow",
            MechanismSeparationRow,
        ),
        ("vehicleDynamicsStageKeys", "VehicleDynamicsChainStage", VehicleDynamicsChainStage),
        (
            "performanceMechanismCandidateKeys",
            "PerformanceMechanismCandidate",
            PerformanceMechanismCandidate,
        ),
        (
            "vehicleDynamicsFocusArtifactKeys",
            "VehicleDynamicsFocusArtifact",
            VehicleDynamicsFocusArtifact,
        ),
        (
            "performanceMechanismAssessmentKeys",
            "PerformanceMechanismAssessment",
            PerformanceMechanismAssessment,
        ),
    ):
        mirrored = exact_key_list(key_list)
        typed = type_fields(type_name)
        backend = list(model.model_fields)
        assert len(mirrored) == len(set(mirrored))
        assert len(typed) == len(set(typed))
        assert set(mirrored) == set(backend), (
            f"{key_list} drifted: missing={set(backend) - set(mirrored)}, "
            f"extra={set(mirrored) - set(backend)}"
        )
        assert set(typed) == set(backend), (
            f"{type_name} drifted: missing={set(backend) - set(typed)}, "
            f"extra={set(typed) - set(backend)}"
        )


def test_p35_focus_navigation_scope_and_authority_have_deep_client_mirrors() -> None:
    types = (ROOT / "ui/src/types/vehicleDynamics.ts").read_text(encoding="utf-8")
    trust = (ROOT / "ui/src/utils/vehicleDynamicsTrust.ts").read_text(
        encoding="utf-8"
    )
    component = (ROOT / "ui/src/components/VehicleDynamicsBlackboard.tsx").read_text(
        encoding="utf-8"
    )
    for field in (
        "lap_numbers",
        "lap_pct_start",
        "lap_pct_end",
        "phase",
        "p35_assessment_sha256",
        "component_causal_claim_count",
        "setup_authorized",
        "terminal_authority",
    ):
        assert field in types
        assert field in trust
    assert "p20_profile_hash: string | null" in types
    assert 'value.observation_authority !== "observation_only"' in trust
    assert 'value.mechanism_authority !== "candidate_only"' in trust
    assert "value.component_causal_claim_count !== 0" in trust
    assert "value.setup_authorized !== false" in trust
    assert 'value.terminal_authority !== "p19_only"' in trust
    assert "value.lap_numbers.length > 0" in trust
    assert "value.lap_pct_start <= value.lap_pct_end" in trust
    assert "onFocusEvidence(entry)" in component
    assert "Open support evidence" in component
    assert "Open contradiction evidence" in component
    assert "Open discriminator evidence" in component


def test_p35_client_pins_the_frozen_graph_and_all_inspection_tools() -> None:
    trust = (ROOT / "ui/src/utils/vehicleDynamicsTrust.ts").read_text(
        encoding="utf-8"
    )
    registry = (ROOT / "ui/src/utils/vehicleDynamicsRegistry.ts").read_text(
        encoding="utf-8"
    )
    types = (ROOT / "ui/src/types/vehicleDynamics.ts").read_text(encoding="utf-8")
    graph = {
        "id": "p35vdg_c14af7ad22a752df5710a6e6",
        "version": "2026.08.next-gen-oval.v1:c14af7ad22a7",
        "knowledge": "2026.08.p35-next-gen-oval.v1",
        "sha256": "c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030",
    }
    for value in graph.values():
        assert value in registry
    assert "p35.vehicle-dynamics-runtime-trust.v1" in registry
    assert "5bc9139f42049f391015040948147f9de37af1b2da770ea99e10d1db72f74164" in registry
    assert '"p20_mechanism_ids"' in registry
    assert '"support_required_evidence_layers"' in registry
    assert '"support_required_channel_groups"' in registry
    assert "runtimeSupportContractSatisfied" in trust
    assert "accepted_source_channel_ids.some" in trust
    assert "matchedAlternatives >= requirement.minimum_alternatives" in trust
    for comparison in (
        "value.graph_id !== P35_GRAPH_ID",
        "value.graph_version !== P35_GRAPH_VERSION",
        "value.knowledge_version !== P35_KNOWLEDGE_VERSION",
        "value.knowledge_graph_sha256 !== P35_GRAPH_SHA256",
    ):
        assert comparison in trust

    type_block = types.split("export type VehicleDynamicsInspectionToolId =", 1)[1].split(
        ";", 1
    )[0]
    runtime_block = trust.split("export const vehicleDynamicsInspectionToolIds =", 1)[
        1
    ].split("] as const", 1)[0]
    expected = {item.value for item in VehicleDynamicsInspectionToolId}
    assert set(re.findall(r'"(inspect_[a-z0-9_]+)"', type_block)) == expected
    assert set(re.findall(r'"(inspect_[a-z0-9_]+)"', runtime_block)) == expected

    registry_match = re.search(
        r"export const p35RuntimeTrustManifest = (\{.*\}) as const;",
        registry,
        flags=re.DOTALL,
    )
    assert registry_match is not None
    assert json.loads(registry_match.group(1)) == (
        compile_next_gen_oval_runtime_trust_manifest().model_dump(mode="json")
    )


def test_p35_blackboard_is_learning_only_complete_and_noncausal() -> None:
    deck = (ROOT / "ui/src/components/CrewChiefCommandDeck.tsx").read_text(
        encoding="utf-8"
    )
    component = (ROOT / "ui/src/components/VehicleDynamicsBlackboard.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui/src/App.tsx").read_text(encoding="utf-8")
    learning_index = deck.index("{learning && (")
    blackboard_index = deck.index("<VehicleDynamicsBlackboard")
    assert blackboard_index > learning_index
    assert "<VehicleDynamicsBlackboard" not in deck[:learning_index]
    assert '"vehicle_dynamics"' not in app
    for heading in (
        "Performance problem",
        "Driver demand",
        "Vehicle response",
        "Tire demand",
        "Load transfer / platform",
        "Transient or steady-state?",
        "Mechanism candidates",
        "Component families",
        "Strongest support",
        "Strongest contradiction",
        "Bounded inspection evidence",
    ):
        assert heading in component
    assert "P19 MISSION EVIDENCE" in component
    assert "NEXT · P19" not in component
    assert "zero component causal claims" in component
    assert "no setup authority" in component
    assert "onFocusEvidence(entry)" in component
