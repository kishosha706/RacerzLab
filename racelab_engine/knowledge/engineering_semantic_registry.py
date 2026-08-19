"""Compiled relationship registry for P35.4.3.

The registry connects existing typed vocabularies.  It is not an observer,
ranker, setup catalog, or authority source.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256


_SHA = r"^[0-9a-f]{64}$"
_ID = r"^[a-z0-9][a-z0-9_.:-]*$"


class _SemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EngineeringSemanticRegistryEntry(_SemanticModel):
    relation_id: str = Field(pattern=_ID)
    label: str = Field(min_length=1)
    problem_phases: tuple[str, ...] = Field(min_length=1)
    driver_demand_requirement: Literal[
        "matched", "measured_transition", "continuous_stint"
    ]
    p20_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    p35_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    p26_quantity_ids: tuple[str, ...] = Field(min_length=1)
    p26_component_family_ids: tuple[str, ...] = Field(min_length=1)
    crew_inspection_tool_ids: tuple[str, ...] = Field(min_length=1)
    discriminator_contract_ids: tuple[str, ...] = Field(min_length=1)
    required_channel_ids: tuple[str, ...] = Field(min_length=1)
    protected_countereffects: tuple[str, ...] = Field(min_length=1)
    applicability: Literal["reviewed_next_gen_oval"] = "reviewed_next_gen_oval"
    authority: Literal["relationship_only"] = "relationship_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def relationships_are_unique(self) -> Self:
        sequences = (
            self.problem_phases,
            self.p20_mechanism_ids,
            self.p35_mechanism_ids,
            self.p26_quantity_ids,
            self.p26_component_family_ids,
            self.crew_inspection_tool_ids,
            self.discriminator_contract_ids,
            self.required_channel_ids,
            self.protected_countereffects,
        )
        if any(len(values) != len(set(values)) for values in sequences):
            raise ValueError("semantic registry relationships must be unique")
        return self


class EngineeringSemanticRegistry(_SemanticModel):
    schema_version: Literal["p3543.engineering-semantic-registry.v1"] = (
        "p3543.engineering-semantic-registry.v1"
    )
    registry_sha256: str = Field(pattern=_SHA)
    entries: tuple[EngineeringSemanticRegistryEntry, ...] = Field(min_length=1)
    authority: Literal["relationship_only"] = "relationship_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def registry_is_content_addressed(self) -> Self:
        ids = tuple(item.relation_id for item in self.entries)
        if len(ids) != len(set(ids)):
            raise ValueError("semantic response relations must be unique")
        body = self.model_dump(mode="json", exclude={"registry_sha256"})
        if canonical_json_sha256(body) != self.registry_sha256:
            raise ValueError("semantic registry identity is corrupt")
        return self


def _entry(
    relation_id: str,
    label: str,
    phases: tuple[str, ...],
    driver_requirement: Literal["matched", "measured_transition", "continuous_stint"],
    p20: tuple[str, ...],
    mechanisms: tuple[str, ...],
    quantities: tuple[str, ...],
    components: tuple[str, ...],
    tools: tuple[str, ...],
    discriminators: tuple[str, ...],
    channels: tuple[str, ...],
    countereffects: tuple[str, ...],
) -> EngineeringSemanticRegistryEntry:
    return EngineeringSemanticRegistryEntry(
        relation_id=relation_id,
        label=label,
        problem_phases=phases,
        driver_demand_requirement=driver_requirement,
        p20_mechanism_ids=p20,
        p35_mechanism_ids=mechanisms,
        p26_quantity_ids=quantities,
        p26_component_family_ids=components,
        crew_inspection_tool_ids=tools,
        discriminator_contract_ids=discriminators,
        required_channel_ids=channels,
        protected_countereffects=countereffects,
    )


_ENTRIES = (
    _entry(
        "brake_to_pressure", "Brake to four-line pressure", ("brake", "entry"),
        "measured_transition", ("braking_response",),
        ("mechanism:brake_entry_instability",),
        ("quantity:brake_input", "quantity:four_corner_brake_pressure"),
        ("brakes", "weight_distribution"),
        ("inspect_brake_vehicle_response",),
        ("observation:braking_response:separate_driver_from_vehicle",),
        ("brake_pct", "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar", "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar"),
        ("entry stability", "downstream corner time"),
    ),
    _entry(
        "brake_to_deceleration", "Brake to deceleration", ("brake",),
        "measured_transition", ("braking_response",),
        ("mechanism:brake_entry_instability",),
        ("quantity:brake_input", "quantity:longitudinal_acceleration"),
        ("brakes", "tires"), ("inspect_brake_vehicle_response",),
        ("observation:braking_response:separate_driver_from_vehicle",),
        ("brake_pct", "long_accel"), ("entry stability", "braking distance"),
    ),
    _entry(
        "brake_to_yaw", "Brake to yaw", ("brake", "entry"),
        "matched", ("braking_response", "corner_rotation"),
        ("mechanism:brake_entry_instability",),
        ("quantity:brake_input", "quantity:yaw_rate"),
        ("brakes", "weight_distribution", "tires"),
        ("inspect_brake_vehicle_response",),
        ("observation:braking_response:separate_driver_from_vehicle",),
        ("brake_pct", "yaw_rate"), ("entry stability", "driver correction workload"),
    ),
    _entry(
        "brake_release_to_yaw", "Brake release to yaw", ("transition", "entry"),
        "matched", ("braking_response", "corner_rotation", "damper_response"),
        ("mechanism:brake_release_rotation_deficit",),
        ("quantity:brake_input", "quantity:yaw_rate", "quantity:shock_velocity"),
        ("brakes", "dampers", "tires"),
        ("inspect_transient_settling", "inspect_brake_vehicle_response"),
        ("observation:brake_release_transition:separate_pressure_decay_from_settling",),
        ("brake_pct", "yaw_rate"), ("center response", "entry stability"),
    ),
    _entry(
        "throttle_to_acceleration", "Throttle to acceleration", ("throttle_pickup", "exit"),
        "matched", ("powertrain_response",),
        ("mechanism:power_on_rotation_deficit", "mechanism:traction_limitation_like"),
        ("quantity:throttle_input", "quantity:longitudinal_acceleration"),
        ("differential", "final_drive", "tires"),
        ("inspect_power_on_response",),
        ("observation:throttle_pickup_transition:separate_power_response",),
        ("throttle_pct", "long_accel"), ("exit stability", "following straight carry"),
    ),
    _entry(
        "throttle_to_yaw", "Throttle to yaw", ("throttle_pickup", "exit"),
        "matched", ("powertrain_response", "corner_rotation"),
        ("mechanism:power_on_rotation_excess", "mechanism:power_on_rotation_deficit"),
        ("quantity:throttle_input", "quantity:yaw_rate"),
        ("differential", "tires", "springs", "anti_roll_bars"),
        ("inspect_power_on_response",),
        ("observation:throttle_pickup_transition:separate_power_response",),
        ("throttle_pct", "yaw_rate"), ("exit security", "driver correction workload"),
    ),
    _entry(
        "steering_wheel_to_yaw", "Steering-wheel demand to yaw", ("turn_in", "entry", "center"),
        "matched", ("corner_rotation", "driver_execution"),
        ("mechanism:center_rotation_deficit",),
        ("quantity:steering_wheel_demand", "quantity:yaw_rate"),
        ("steering", "tires", "springs", "anti_roll_bars"),
        ("inspect_steady_state_balance", "inspect_driver_vehicle_separation"),
        ("observation:settled_center_rotation:separate_driver_from_vehicle",),
        ("steering_deg", "yaw_rate"), ("entry response", "exit response"),
    ),
    _entry(
        "disturbance_to_chassis", "Disturbance to four-corner chassis response", ("transition", "entry", "exit"),
        "measured_transition", ("damper_response", "platform_response"),
        ("mechanism:disturbance_compliance_issue",),
        ("quantity:vertical_acceleration", "quantity:shock_velocity", "quantity:shock_deflection", "quantity:yaw_rate"),
        ("dampers", "springs", "platform", "tires"),
        ("inspect_transient_settling",),
        ("observation:disturbance_compliance:separate_platform_settling",),
        ("vert_accel", "yaw_rate", "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"),
        ("platform consistency", "driver workload", "downstream time"),
    ),
    _entry(
        "stint_migration", "Stint response migration", ("brake", "entry", "center", "throttle_pickup", "exit"),
        "continuous_stint", ("corner_rotation", "driver_execution", "platform_response"),
        ("mechanism:center_rotation_deficit", "mechanism:power_on_rotation_deficit"),
        ("quantity:steering_wheel_demand", "quantity:yaw_rate", "quantity:throttle_input"),
        ("tires", "platform", "steering"),
        ("inspect_tire_state_migration",),
        ("observation:stint_migration:separate_response_progression",),
        ("steering_deg", "yaw_rate", "throttle_pct", "session_tick"),
        ("long-run pace", "driver workload", "platform clearance"),
    ),
)


@lru_cache(maxsize=1)
def compile_engineering_semantic_registry() -> EngineeringSemanticRegistry:
    body: dict[str, Any] = {
        "schema_version": "p3543.engineering-semantic-registry.v1",
        "entries": [item.model_dump(mode="json") for item in _ENTRIES],
        "authority": "relationship_only",
        "setup_authorized": False,
    }
    return EngineeringSemanticRegistry(
        **body,
        registry_sha256=canonical_json_sha256(body),
    )


def response_relations_for_mechanism(mechanism_id: str) -> tuple[str, ...]:
    return tuple(
        item.relation_id
        for item in compile_engineering_semantic_registry().entries
        if mechanism_id in item.p35_mechanism_ids
    )


def semantic_entry(relation_id: str) -> EngineeringSemanticRegistryEntry | None:
    return next(
        (
            item
            for item in compile_engineering_semantic_registry().entries
            if item.relation_id == relation_id
        ),
        None,
    )


__all__ = [
    "EngineeringSemanticRegistry",
    "EngineeringSemanticRegistryEntry",
    "compile_engineering_semantic_registry",
    "response_relations_for_mechanism",
    "semantic_entry",
]
