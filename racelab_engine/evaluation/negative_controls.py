"""Canonical negative controls shared by P21 shadow evaluations."""

from __future__ import annotations

from pydantic import Field

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


class NegativeControlContract(EvidenceLabModel):
    control_id: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    blocks_capabilities: tuple[str, ...] = Field(min_length=1)
    real_world_validation_required: bool = True


def negative_control_library() -> tuple[NegativeControlContract, ...]:
    definitions = {
        "same_setup_unchanged": "No setup effect or mechanism transition may fire.",
        "constant_carcass_temp": "No live carcass-temperature trend may be inferred.",
        "constant_tread_wear": "No live wear trend may be inferred.",
        "no_wheel_slip": "Wheel-slip evidence must remain absent.",
        "geometry_missing": "Geometry-dependent correction must remain unavailable.",
        "stable_steering_response": "No steering-response change may fire.",
        "same_ffb_config": "Matched FFB comparison remains eligible if other gates pass.",
        "ffb_config_changed": "Steering-workload comparison must be blocked.",
        "no_real_setup_change": "No setup response may be learned.",
        "pit_request_never_applied": "A request cannot become applied control state.",
        "traffic_context_mismatch": "Causal setup attribution must be blocked.",
        "vehicle_profile_missing": "Dependent shadow metrics must be unavailable.",
        "profile_build_mismatch": "Dependent shadow metrics must be unavailable.",
        "constant_ride_height": "No chassis-motion response may be inferred.",
        "stable_acceleration": "No acceleration-state transition may fire.",
        "a2_failed_restoration": "The workflow cannot become causal evidence.",
        "driver_line_changed": "Exact-context response attribution must be blocked.",
        "sim_integrity_degraded": "Scientific qualification must fail closed.",
        "pit_context_boundary": "A detector may not bridge the pit boundary.",
    }
    return tuple(
        NegativeControlContract(
            control_id=control_id,
            expected_behavior=behavior,
            blocks_capabilities=("statistical_activation",),
        )
        for control_id, behavior in definitions.items()
    )


__all__ = ["NegativeControlContract", "negative_control_library"]
