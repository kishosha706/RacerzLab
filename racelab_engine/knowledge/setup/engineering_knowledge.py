"""Compiler for the P35.1 Dial-In-to-vehicle-dynamics knowledge spine."""

from __future__ import annotations

from functools import lru_cache

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    compile_next_gen_oval_knowledge_graph,
    compile_next_gen_oval_runtime_trust_manifest,
)
from racelab_engine.models.engineering_knowledge import (
    EngineeringKnowledgeCoverageReport,
    MechanismSetupBridge,
)

from .dial_in_controls import control_keys_for_effect
from .loader import load_setup_knowledge


# Explicit by design. A new setup area cannot silently inherit a nearby physical
# mechanism. The compiler fails until its reviewed bridge is declared here.
_AREA_MECHANISMS: dict[str, tuple[str, ...]] = {
    "brake_bias": (
        "mechanism:brake_entry_instability",
        "mechanism:brake_release_rotation_deficit",
    ),
    "camber": (
        "mechanism:front_tire_saturation_like",
        "mechanism:rear_tire_saturation_like",
        "mechanism:tire_state_migration",
    ),
    "caster": ("mechanism:front_tire_saturation_like",),
    "cross_weight": (
        "mechanism:center_rotation_deficit",
        "mechanism:power_on_rotation_deficit",
        "mechanism:power_on_rotation_excess",
    ),
    "diff_preload": (
        "mechanism:power_on_rotation_deficit",
        "mechanism:power_on_rotation_excess",
        "mechanism:traction_limitation_like",
    ),
    "diffuser_platform": (
        "mechanism:platform_pitch_migration",
        "mechanism:platform_roll_migration",
        "mechanism:scrub_like_resistance",
    ),
    "final_drive": ("mechanism:gearing_headroom_limitation",),
    "front_arb_arm": (
        "mechanism:front_roll_support_limitation",
        "mechanism:center_rotation_deficit",
    ),
    "front_arb_diameter": (
        "mechanism:front_roll_support_limitation",
        "mechanism:center_rotation_deficit",
    ),
    "front_arb_preload": ("mechanism:front_roll_support_limitation",),
    "front_ride_height_platform": (
        "mechanism:platform_pitch_migration",
        "mechanism:front_roll_support_limitation",
    ),
    "front_toe_response": (
        "mechanism:front_tire_saturation_like",
        "mechanism:scrub_like_resistance",
    ),
    "hs_comp_slope": ("mechanism:disturbance_compliance_issue",),
    "hs_compression": ("mechanism:disturbance_compliance_issue",),
    "hs_rebound": ("mechanism:disturbance_compliance_issue",),
    "ls_compression": (
        "mechanism:brake_release_rotation_deficit",
        "mechanism:platform_pitch_migration",
        "mechanism:platform_roll_migration",
    ),
    "ls_rebound": (
        "mechanism:brake_release_rotation_deficit",
        "mechanism:platform_pitch_migration",
        "mechanism:power_on_rotation_deficit",
        "mechanism:power_on_rotation_excess",
    ),
    "pressure_split": (
        "mechanism:tire_state_migration",
        "mechanism:front_tire_saturation_like",
        "mechanism:rear_tire_saturation_like",
    ),
    "rear_arb_arm": (
        "mechanism:rear_roll_support_limitation",
        "mechanism:power_on_rotation_deficit",
        "mechanism:power_on_rotation_excess",
    ),
    "rear_arb_diameter": (
        "mechanism:rear_roll_support_limitation",
        "mechanism:power_on_rotation_deficit",
        "mechanism:power_on_rotation_excess",
    ),
    "rear_arb_preload": ("mechanism:rear_roll_support_limitation",),
    "rear_ride_height_platform": (
        "mechanism:platform_pitch_migration",
        "mechanism:rear_roll_support_limitation",
    ),
    "rear_toe_stability": (
        "mechanism:rear_tire_saturation_like",
        "mechanism:scrub_like_resistance",
    ),
    "ride_height": (
        "mechanism:platform_pitch_migration",
        "mechanism:platform_roll_migration",
    ),
    "shock_collar": (
        "mechanism:platform_pitch_migration",
        "mechanism:platform_roll_migration",
    ),
    "spring_rate": (
        "mechanism:front_roll_support_limitation",
        "mechanism:rear_roll_support_limitation",
        "mechanism:platform_pitch_migration",
        "mechanism:platform_roll_migration",
        "mechanism:traction_limitation_like",
    ),
    "tire_pressure": (
        "mechanism:tire_state_migration",
        "mechanism:front_tire_saturation_like",
        "mechanism:rear_tire_saturation_like",
        "mechanism:traction_limitation_like",
    ),
    "toe": (
        "mechanism:scrub_like_resistance",
        "mechanism:front_tire_saturation_like",
        "mechanism:rear_tire_saturation_like",
    ),
}

_LEGACY_FORBIDDEN_AREAS = frozenset({"track_bar", "truck_arm_mount", "bump_stop", "packer"})


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@lru_cache(maxsize=1)
def compile_mechanism_setup_bridges() -> tuple[MechanismSetupBridge, ...]:
    knowledge = load_setup_knowledge()
    graph = compile_next_gen_oval_knowledge_graph()
    trust_manifest = compile_next_gen_oval_runtime_trust_manifest()
    trust_by_id = {item.mechanism_id: item for item in trust_manifest.mechanisms}
    setup_areas = {item.setup_area: item for item in knowledge.setup_areas}
    catalog_areas = {effect.setup_area for effect in knowledge.setup_effects}
    undeclared = catalog_areas - set(_AREA_MECHANISMS) - _LEGACY_FORBIDDEN_AREAS
    if undeclared:
        raise ValueError(
            "P35.1 setup areas require an explicit reviewed bridge: "
            + ", ".join(sorted(undeclared))
        )
    bridges: list[MechanismSetupBridge] = []
    for effect in knowledge.setup_effects:
        mechanism_ids = _AREA_MECHANISMS.get(effect.setup_area, ())
        trusts = tuple(trust_by_id[item] for item in mechanism_ids)
        control_keys = control_keys_for_effect(effect.effect_id)
        if effect.setup_area in _LEGACY_FORBIDDEN_AREAS:
            classification = "unsupported_remove"
        elif control_keys:
            classification = "p19_testable_control"
        else:
            classification = "measurable_hypothesis"
        bridges.append(
            MechanismSetupBridge.build(
                effect_id=effect.effect_id,
                setup_area=effect.setup_area,
                knowledge_version=graph.knowledge_version,
                p35_knowledge_graph_sha256=graph.content_sha256,
                p35_runtime_trust_sha256=trust_manifest.runtime_trust_sha256,
                catalog_classification=classification,
                physical_role=setup_areas[effect.setup_area].what_it_changes,
                car_applicability=tuple(effect.applies_to),
                disabled_car_families=tuple(effect.disabled_for),
                p35_mechanism_ids=mechanism_ids,
                p20_mechanism_ids=_unique(
                    [value for trust in trusts for value in trust.p20_mechanism_ids]
                ),
                p26_component_family_ids=_unique(
                    [value for trust in trusts for value in trust.component_family_ids]
                ),
                p32_performance_mechanism_ids=_unique(
                    [
                        value
                        for trust in trusts
                        for value in trust.p32_performance_mechanism_ids
                    ]
                ),
                response_regimes=_unique(
                    [trust.response_regime.value for trust in trusts]
                ),
                relevant_phases=_unique(
                    [phase.value for trust in trusts for phase in trust.relevant_phases]
                ),
                inspection_tool_ids=_unique(
                    [trust.inspection_tool_id.value for trust in trusts]
                ),
                discriminator_contract_ids=_unique(
                    [
                        value
                        for trust in trusts
                        for value in trust.discriminator_observation_contract_ids
                    ]
                ),
                required_evidence_layers=_unique(
                    [
                        layer.value
                        for trust in trusts
                        for layer in trust.support_required_evidence_layers
                    ]
                ),
                evidence_requirements=tuple(effect.evidence_required),
                validation_targets=tuple(effect.validation_targets),
                countereffect_targets=tuple(effect.watch_for_targets),
                protected_outcomes=tuple(effect.watch_for_targets),
                related_control_keys=control_keys,
                source_ids=tuple(effect.source_ids),
            )
        )
    return tuple(bridges)


@lru_cache(maxsize=1)
def compile_engineering_knowledge_coverage() -> EngineeringKnowledgeCoverageReport:
    effects = tuple(load_setup_knowledge().setup_effects)
    bridges = compile_mechanism_setup_bridges()
    effect_ids = tuple(item.effect_id for item in effects)
    bridge_effect_ids = tuple(item.effect_id for item in bridges)
    duplicates = tuple(
        sorted({effect_id for effect_id in bridge_effect_ids if bridge_effect_ids.count(effect_id) > 1})
    )
    mapped = tuple(effect_id for effect_id in effect_ids if effect_id in set(bridge_effect_ids))
    unmapped = tuple(effect_id for effect_id in effect_ids if effect_id not in set(bridge_effect_ids))
    counts = {
        value: sum(item.catalog_classification == value for item in bridges)
        for value in (
            "educational_knowledge",
            "measurable_hypothesis",
            "p19_testable_control",
            "unsupported_remove",
        )
    }
    body = {
        "schema_version": "p351.knowledge-coverage.v1",
        "catalog_effect_count": len(effects),
        "bridge_count": len(bridges),
        "educational_count": counts["educational_knowledge"],
        "measurable_count": counts["measurable_hypothesis"],
        "structurally_p19_testable_count": counts["p19_testable_control"],
        "unsupported_remove_count": counts["unsupported_remove"],
        "mapped_effect_ids": mapped,
        "unmapped_effect_ids": unmapped,
        "duplicate_effect_ids": duplicates,
        "legacy_forbidden_effect_ids": tuple(
            item.effect_id for item in bridges if item.catalog_classification == "unsupported_remove"
        ),
        "bridge_ids": tuple(item.bridge_id for item in bridges),
    }
    return EngineeringKnowledgeCoverageReport(
        report_sha256=canonical_json_sha256(body), **body
    )


__all__ = [
    "compile_engineering_knowledge_coverage",
    "compile_mechanism_setup_bridges",
]
