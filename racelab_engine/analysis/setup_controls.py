from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Literal


MagnitudeLabel = Literal["small", "medium", "large", "unknown"]
MagnitudeMode = Literal["absolute", "relative"]
StepStrategy = Literal["numeric_test", "legal_option", "discrete_mode"]

MM_PER_INCH = 25.4
LB_PER_INCH_PER_N_PER_MM = 5.71014716277


@dataclass(frozen=True)
class SetupControlSpec:
    key: str
    label: str
    group: str
    display_unit: str | None
    decimals: int
    conversion_factor: float = 1.0
    magnitude_mode: MagnitudeMode = "absolute"
    small_max: float = 0.0
    medium_max: float = 0.0
    nominal_test_increment: float | None = None
    step_strategy: StepStrategy = "legal_option"
    influence_label: str = "Moderate influence"
    garage_label: str | None = None
    magnitude_policy: str = "Use the smallest legal garage step, then measure the response."
    increase_effect: str = "Raises the selected setting."
    decrease_effect: str = "Lowers the selected setting."
    guardrail: str = "Change one setup area at a time and compare clean laps."
    non_numeric_change_label: MagnitudeLabel = "unknown"

    def to_display(self, value: float) -> float:
        return value * self.conversion_factor

    def format_number(self, value: float, *, signed: bool = False) -> str:
        prefix = "+" if signed and value > 0 else ""
        if self.decimals == 0:
            return f"{prefix}{value:.0f}"
        return f"{prefix}{value:.{self.decimals}f}"


@dataclass(frozen=True)
class MagnitudeAssessment:
    label: MagnitudeLabel
    display_delta: float | None
    relative_delta_percent: float | None
    basis: str


def _spec(
    key: str,
    label: str,
    group: str,
    unit: str | None,
    decimals: int,
    *,
    factor: float = 1.0,
    mode: MagnitudeMode = "absolute",
    small: float,
    medium: float,
    increment: float | None = None,
    step_strategy: StepStrategy | None = None,
    influence: str,
    garage: str | None = None,
    policy: str,
    increase: str,
    decrease: str,
    guardrail: str,
    non_numeric: MagnitudeLabel = "unknown",
) -> SetupControlSpec:
    return SetupControlSpec(
        key=key,
        label=label,
        group=group,
        display_unit=unit,
        decimals=decimals,
        conversion_factor=factor,
        magnitude_mode=mode,
        small_max=small,
        medium_max=medium,
        nominal_test_increment=increment,
        step_strategy=step_strategy or ("numeric_test" if increment is not None else "legal_option"),
        influence_label=influence,
        garage_label=garage or label,
        magnitude_policy=policy,
        increase_effect=increase,
        decrease_effect=decrease,
        guardrail=guardrail,
        non_numeric_change_label=non_numeric,
    )


# Driver-facing units mirror the Garage/Setup pages. These magnitude bands are
# RacerZLab engineering policy, not claims that every car has identical garage
# clicks. Input size remains separate from vehicle influence: a small ride-height
# or cross-weight input can still produce a strong response.
SETUP_CONTROL_SPECS: dict[str, SetupControlSpec] = {
    "lf_ride_height_mm": _spec("lf_ride_height_mm", "LF Ride Height", "front_platform", "in", 3, factor=1 / MM_PER_INCH, small=0.040, medium=0.100, increment=0.5, influence="Strong, coupled ride-height influence", policy="Up to 0.040 in (about 1 mm) is small; up to 0.100 in is medium; larger is a major ride-height change.", increase="Increasing LF ride height raises the LF static chassis height and ground clearance. If LF is changed alone, cross weight can also change.", decrease="Decreasing LF ride height lowers the LF static chassis height and ground clearance. If LF is changed alone, cross weight can also change.", guardrail="Decide whether the goal is corner balance or front ride height. To raise or lower the front as a pair, change LF and RF equally, then recheck cross weight and bottoming clearance."),
    "rf_ride_height_mm": _spec("rf_ride_height_mm", "RF Ride Height", "front_platform", "in", 3, factor=1 / MM_PER_INCH, small=0.040, medium=0.100, increment=0.5, influence="Strong, coupled ride-height influence", policy="Up to 0.040 in (about 1 mm) is small; up to 0.100 in is medium; larger is a major ride-height change.", increase="Increasing RF ride height raises the RF static chassis height and ground clearance. If RF is changed alone, cross weight can also change.", decrease="Decreasing RF ride height lowers the RF static chassis height and ground clearance. If RF is changed alone, cross weight can also change.", guardrail="Decide whether the goal is corner balance or front ride height. To raise or lower the front as a pair, change LF and RF equally, then recheck cross weight and bottoming clearance."),
    "lr_ride_height_mm": _spec("lr_ride_height_mm", "LR Ride Height", "rear_platform", "in", 3, factor=1 / MM_PER_INCH, small=0.040, medium=0.100, increment=0.5, influence="Strong, coupled ride-height influence", policy="Up to 0.040 in (about 1 mm) is small; up to 0.100 in is medium; larger is a major ride-height change.", increase="Increasing LR ride height raises the LR static chassis height and ground clearance. If LR is changed alone, cross weight can also change.", decrease="Decreasing LR ride height lowers the LR static chassis height and ground clearance. If LR is changed alone, cross weight can also change.", guardrail="Decide whether the goal is corner balance or rear ride height. To raise or lower the rear as a pair, change LR and RR equally, then recheck cross weight and bottoming clearance."),
    "rr_ride_height_mm": _spec("rr_ride_height_mm", "RR Ride Height", "rear_platform", "in", 3, factor=1 / MM_PER_INCH, small=0.040, medium=0.100, increment=0.5, influence="Strong, coupled ride-height influence", policy="Up to 0.040 in (about 1 mm) is small; up to 0.100 in is medium; larger is a major ride-height change.", increase="Increasing RR ride height raises the RR static chassis height and ground clearance. If RR is changed alone, cross weight can also change.", decrease="Decreasing RR ride height lowers the RR static chassis height and ground clearance. If RR is changed alone, cross weight can also change.", guardrail="Decide whether the goal is corner balance or rear ride height. To raise or lower the rear as a pair, change LR and RR equally, then recheck cross weight and bottoming clearance."),
    "lf_front_spring_n_per_mm": _spec("lf_front_spring_n_per_mm", "LF Spring", "springs", "lb/in", 0, factor=LB_PER_INCH_PER_N_PER_MM, mode="relative", small=5.0, medium=12.5, influence="Strong chassis-control and mechanical-grip influence", policy="Up to 5% from baseline is small; up to 12.5% is medium; larger is a major spring change.", increase="Increasing LF spring rate makes the LF spring stiffer, reducing LF suspension travel under the same load. It can control chassis movement better but absorb bumps less easily.", decrease="Decreasing LF spring rate makes the LF spring softer, increasing LF suspension travel under the same load. It can absorb bumps better but allow more chassis movement.", guardrail="Use the next available rate, then restore the intended ride height and cross weight. Judge the result from telemetry because the handling response depends on all four springs and the anti-roll bars."),
    "rf_front_spring_n_per_mm": _spec("rf_front_spring_n_per_mm", "RF Spring", "springs", "lb/in", 0, factor=LB_PER_INCH_PER_N_PER_MM, mode="relative", small=5.0, medium=12.5, influence="Strong chassis-control and mechanical-grip influence", policy="Up to 5% from baseline is small; up to 12.5% is medium; larger is a major spring change.", increase="Increasing RF spring rate makes the RF spring stiffer, reducing RF suspension travel under the same load. It can control chassis movement better but absorb bumps less easily.", decrease="Decreasing RF spring rate makes the RF spring softer, increasing RF suspension travel under the same load. It can absorb bumps better but allow more chassis movement.", guardrail="Use the next available rate, then restore the intended ride height and cross weight. Judge the result from telemetry because the handling response depends on all four springs and the anti-roll bars."),
    "lr_rear_spring_n_per_mm": _spec("lr_rear_spring_n_per_mm", "LR Spring", "springs", "lb/in", 0, factor=LB_PER_INCH_PER_N_PER_MM, mode="relative", small=5.0, medium=12.5, influence="Strong chassis-control and drive-grip influence", policy="Up to 5% from baseline is small; up to 12.5% is medium; larger is a major spring change.", increase="Increasing LR spring rate makes the LR spring stiffer, reducing LR suspension travel under the same load. It can control chassis movement better but absorb bumps less easily.", decrease="Decreasing LR spring rate makes the LR spring softer, increasing LR suspension travel under the same load. It can absorb bumps better but allow more chassis movement.", guardrail="Use the next available rate, then restore the intended ride height and cross weight. Judge the result from telemetry because the handling response depends on all four springs and the anti-roll bars."),
    "rr_rear_spring_n_per_mm": _spec("rr_rear_spring_n_per_mm", "RR Spring", "springs", "lb/in", 0, factor=LB_PER_INCH_PER_N_PER_MM, mode="relative", small=5.0, medium=12.5, influence="Strong rear-balance and bump-absorption influence", policy="Up to 5% from baseline is small; up to 12.5% is medium; larger is a major spring change.", increase="Increasing RR spring rate makes the RR spring stiffer, reducing RR suspension travel under the same load. It can control chassis movement better but absorb bumps less easily.", decrease="Decreasing RR spring rate makes the RR spring softer, increasing RR suspension travel under the same load. It can absorb bumps better but allow more chassis movement.", guardrail="Use the next available rate, then restore the intended ride height and cross weight. Judge the result from telemetry because the handling response depends on all four springs and the anti-roll bars."),
    "nose_weight_percent": _spec("nose_weight_percent", "Nose Weight", "weight_distribution", "%", 1, small=0.25, medium=0.75, influence="Strong whole-car balance influence", policy="Up to 0.25 percentage points is small; up to 0.75 is medium; larger is a major weight-distribution change.", increase="Increasing nose weight raises the percentage of static vehicle weight carried by the front axle. It normally makes the car more stable in a straight line and at high speed, but can reduce rotation and work the front tires harder.", decrease="Decreasing nose weight lowers the percentage of static vehicle weight carried by the front axle. It normally helps the car rotate, but can make it less stable in a straight line and at high speed.", guardrail="Use the smallest available ballast position or percentage step, then recheck total weight and cross weight. Do not treat nose weight as a corner-specific adjustment."),
    "cross_weight_percent": _spec("cross_weight_percent", "Cross Weight", "weight_distribution", "%", 1, small=0.50, medium=1.00, increment=0.5, influence="Very strong corner-balance influence", policy="Up to 0.50 percentage points is a small but clearly testable change; up to 1.00 is medium; larger is a major balance move.", increase="Increasing cross weight raises the share of static weight on the RF and LR diagonal. On a left-turn oval it normally stabilizes entry and supports drive-off, but too much can add center push or reduce LF braking load.", decrease="Decreasing cross weight lowers the share of static weight on the RF and LR diagonal. On a left-turn oval it normally frees rotation, but too little can make entry or throttle pickup unstable.", guardrail="Settle the car before every reading and remeasure after adjustment. Keep nose, left-side, and total weight consistent so cross weight is the variable being tested."),
    "tape_percent": _spec("tape_percent", "Tape / Cooling Configuration", "aero_cooling", "%", 0, small=5.0, medium=10.0, increment=5.0, step_strategy="discrete_mode", influence="Very strong cooling influence; car-specific aero/drag trade-off", policy="For percentage tape, 5 points is small, 10 is medium, and more is large. Switching between Race and Qual is always a large change.", increase="Increasing tape closes more of the radiator inlet. Less cooling air reaches the radiator, so coolant and oil temperatures rise; any aero or drag benefit depends on the car and must be confirmed from the run data.", decrease="Decreasing tape opens more of the radiator inlet. More cooling air reaches the radiator, increasing temperature safety margin; any aero or drag cost depends on the car and must be confirmed from the run data.", guardrail="Never keep more tape without a run long enough to prove temperatures remain safe. A short run cannot validate race cooling, and a Qual tape configuration is not a race recommendation.", non_numeric="large"),
    "rear_end_ratio": _spec("rear_end_ratio", "Rear End Ratio", "gearing", ":1", 3, mode="relative", small=1.5, medium=4.0, influence="Very strong RPM, acceleration, and speed influence", policy="Up to 1.5% from baseline is small; up to 4% is medium; larger is a major gearing change. Prefer one adjacent legal ratio.", increase="Increasing the numerical rear-end ratio shortens the gearing. Engine RPM and overall torque multiplication rise at the same road speed, which can improve acceleration when traction and shift timing allow, but reduces limiter and terminal-speed margin.", decrease="Decreasing the numerical rear-end ratio tallens the gearing. Engine RPM and overall torque multiplication fall at the same road speed, which adds limiter and terminal-speed margin but can weaken acceleration.", guardrail="Validate peak straight RPM, limiter margin, shift count and timing, wheelspin, and exit acceleration on comparable clean laps."),
    "front_brake_bias_percent": _spec("front_brake_bias_percent", "Front Brake Bias", "brakes", "%", 1, small=0.50, medium=1.00, increment=0.5, influence="Strong braking-balance influence", garage="Front Brake Bias", policy="Up to 0.50 percentage points is a normal fine adjustment; up to 1.00 is medium; larger is a major braking-balance change.", increase="Increasing front brake bias sends a larger share of braking force to the front axle. It normally calms the rear under braking, but increases the risk of front-tire lockup and push while braking.", decrease="Decreasing front brake bias sends a larger share of braking force to the rear axle. It can help the car rotate while braking, but increases the risk of rear-tire lockup and an unstable entry.", guardrail="Test with tires and brakes at normal running temperature. Immediately undo a change that causes rear-tire lockup, unstable braking, or less consistent stopping."),
    "steering_ratio": _spec("steering_ratio", "Steering Ratio / Pinion", "driver_controls", None, 1, mode="relative", small=10.0, medium=20.0, influence="Driver steering-response influence only", garage="Steering Ratio or Steering Pinion", policy="Up to 10% from baseline is small; up to 20% is medium; larger is a major steering-feel change. Prefer one adjacent available option.", increase="Increasing a true x:1 steering ratio makes steering slower: the driver must turn the steering wheel farther for the same front-wheel angle.", decrease="Decreasing a true x:1 steering ratio makes steering quicker: the driver turns the steering wheel less for the same front-wheel angle.", guardrail="Use this for driver preference and steering feel, not to fix chassis balance. Steering-pinion travel in mm/rev uses the opposite numeric direction from an x:1 ratio, and RacerZLab handles the two formats separately."),
    "steering_offset_deg": _spec("steering_offset_deg", "Steering Offset", "driver_controls", "deg", 1, small=1.0, medium=3.0, influence="Driver-comfort influence only", policy="Up to 1 degree is small; up to 3 degrees is medium; larger is a major steering-wheel recentering change.", increase="Increasing steering offset moves the steering wheel's centered position to the right in the iRacing garage convention. It does not change chassis handling.", decrease="Decreasing steering offset moves the steering wheel's centered position to the left in the iRacing garage convention. It does not change chassis handling.", guardrail="Use steering offset only to center the steering wheel for the driver. If the car pulls left or right, check alignment, asymmetric setup behavior, or damage instead."),
}


def setup_control_spec(key: str) -> SetupControlSpec:
    return SETUP_CONTROL_SPECS[key]


def numeric_setup_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        if not match:
            return None
        value = match.group(0)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def setup_value_numeric_representation(key: str, value: Any) -> tuple[str, float] | None:
    """Return a sortable number while retaining representation semantics."""
    numeric = numeric_setup_value(value)
    if numeric is None:
        return None
    if key != "steering_ratio":
        return "numeric", numeric
    if isinstance(value, str):
        normalized = value.casefold()
        if "mm/rev" in normalized:
            return "steering_pinion_mm_per_rev", numeric
        if ":" in normalized:
            return "steering_ratio_x_to_1", numeric
    # Legacy cards stored true x:1 ratios as bare floats. Treat an unlabelled
    # numeric steering value as x:1 for backward-compatible exact comparison;
    # explicitly labelled mm/rev values remain a separate representation.
    return "steering_ratio_x_to_1", numeric


def canonical_setup_value_key(key: str, value: Any) -> str:
    """Canonical identity for exact setup comparison and option provenance."""
    represented = setup_value_numeric_representation(key, value)
    if represented is not None:
        kind, numeric = represented
        return f"{kind}:{numeric:.12g}"
    if isinstance(value, str):
        return f"text:{value.strip().casefold()}"
    return f"typed:{type(value).__name__}:{value!r}"


def setup_control_values_equal(key: str, left: Any, right: Any) -> bool:
    return canonical_setup_value_key(key, left) == canonical_setup_value_key(key, right)


def display_setup_value(key: str, value: Any) -> Any:
    spec = setup_control_spec(key)
    if key == "steering_ratio" and isinstance(value, str):
        return value
    numeric = numeric_setup_value(value)
    if numeric is None:
        return value
    return round(spec.to_display(numeric), spec.decimals)


def format_setup_value(key: str, value: Any, *, include_unit: bool = True) -> str:
    spec = setup_control_spec(key)
    if key == "steering_ratio" and isinstance(value, str) and (":" in value or "mm/rev" in value.lower()):
        return value
    numeric = numeric_setup_value(value)
    if numeric is None:
        return str(value) if value is not None else "unavailable"
    rendered = spec.format_number(spec.to_display(numeric))
    if include_unit and spec.display_unit:
        separator = "" if spec.display_unit in {"%", ":1"} else " "
        rendered = f"{rendered}{separator}{spec.display_unit}"
    return rendered


def assess_setup_change(key: str, baseline_value: Any, test_value: Any) -> MagnitudeAssessment:
    spec = setup_control_spec(key)
    baseline = numeric_setup_value(baseline_value)
    test = numeric_setup_value(test_value)
    if baseline is None or test is None:
        if baseline_value is not None and test_value is not None and baseline_value != test_value and spec.non_numeric_change_label != "unknown":
            return MagnitudeAssessment(
                spec.non_numeric_change_label,
                None,
                None,
                f"Estimated {spec.non_numeric_change_label} input. This is a discrete configuration change, not a numeric adjustment. Policy: {spec.magnitude_policy}",
            )
        return MagnitudeAssessment("unknown", None, None, "Input size is unknown because comparable numeric values are unavailable.")

    raw_delta = test - baseline
    display_delta = spec.to_display(raw_delta)
    relative = abs(raw_delta) / abs(baseline) * 100.0 if abs(baseline) > 1e-12 else None
    measure = relative if spec.magnitude_mode == "relative" else abs(display_delta)
    if measure is None:
        return MagnitudeAssessment("unknown", display_delta, relative, "The relative change cannot be calculated from a zero baseline.")

    label: MagnitudeLabel = "small" if measure <= spec.small_max else "medium" if measure <= spec.medium_max else "large"
    if spec.magnitude_mode == "relative":
        measurement = f"{measure:.1f}% of the baseline"
    else:
        unit = "percentage points" if spec.display_unit == "%" else spec.display_unit or "units"
        measurement = f"{measure:.{spec.decimals}f} {unit}"
    basis = f"Estimated {label} input: {measurement}. Policy: {spec.magnitude_policy}"
    return MagnitudeAssessment(label, display_delta, relative, basis)


def format_setup_delta(key: str, assessment: MagnitudeAssessment, baseline_value: Any, test_value: Any) -> str | None:
    if assessment.display_delta is None:
        if baseline_value is None and test_value is not None:
            return "added"
        if test_value is None:
            return "removed"
        return f"{baseline_value} -> {test_value}"
    spec = setup_control_spec(key)
    delta = spec.format_number(assessment.display_delta, signed=True)
    if spec.display_unit == "%":
        return f"{delta} percentage points"
    return f"{delta} {spec.display_unit}" if spec.display_unit else delta


def nominal_test_target(key: str, current_value: Any, direction_sign: int) -> tuple[str | None, str]:
    """Return a proposed target when a conservative numeric increment is defined.

    Controls with car/track-specific discrete choices intentionally return a
    next-available instruction rather than inventing a legal garage value.
    """
    spec = setup_control_spec(key)
    current = numeric_setup_value(current_value)
    if spec.nominal_test_increment is None:
        current_text = format_setup_value(key, current_value) if current_value is not None else None
        prefix = f"{current_text} -> " if current_text else ""
        return None, f"{prefix}next available garage setting"
    delta = spec.nominal_test_increment * (1 if direction_sign >= 0 else -1)
    delta_display = spec.to_display(delta)
    delta_text = spec.format_number(delta_display, signed=True)
    delta_unit = "percentage points" if spec.display_unit == "%" else spec.display_unit or "units"
    if current is None:
        return None, f"{delta_text} {delta_unit} from the current setting"
    target = current + delta
    return format_setup_value(key, target), f"{format_setup_value(key, current)} -> {format_setup_value(key, target)} ({delta_text} {delta_unit})"


def recommended_test_size_label(key: str) -> str:
    """Describe the input size without confusing it with expected influence."""
    spec = setup_control_spec(key)
    if spec.nominal_test_increment is None:
        return "Smallest available garage step"
    display_increment = abs(spec.to_display(spec.nominal_test_increment))
    amount = spec.format_number(display_increment)
    unit = " percentage points" if spec.display_unit == "%" else f" {spec.display_unit}" if spec.display_unit else ""
    return f"Small test input · {amount}{unit}"


def expected_control_effect(key: str, direction_sign: int, representation_value: Any = None) -> str:
    spec = setup_control_spec(key)
    if key == "steering_ratio" and isinstance(representation_value, str) and "mm/rev" in representation_value.lower():
        if direction_sign >= 0:
            return "A higher steering-pinion value in mm/rev moves the rack farther per steering-wheel revolution, producing quicker steering."
        return "A lower steering-pinion value in mm/rev moves the rack less per steering-wheel revolution, producing slower steering."
    return spec.increase_effect if direction_sign >= 0 else spec.decrease_effect
