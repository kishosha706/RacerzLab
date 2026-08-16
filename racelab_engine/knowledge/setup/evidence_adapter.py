from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

from racelab_engine.analysis.constants import FORCE_PROXY_WARNING
from racelab_engine.analysis.track_matching import infer_layout_key, normalize_track_key
from racelab_engine.knowledge.setup.evidence_schema import (
    CandidateEvidenceReadiness,
    EvidenceStatus,
    RunEvidenceContext,
    RunEvidenceGroup,
)
from racelab_engine.knowledge.setup.dial_in_controls import (
    control_keys_for_effect,
    expanded_related_setup_keys,
)
from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.matcher import (
    SetupQueryResult,
    parse_symptom,
    query_result_to_dict,
    query_setup_knowledge,
)
from racelab_engine.models.session import RunOverview
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.services.import_service import (
    build_channel_summary,
    read_telemetry_manifest,
    read_telemetry_rows,
)
from racelab_engine.services.setup_learning_service import (
    build_setup_response_context,
    get_setup_area_biases,
)
from racelab_engine.services.track_map_service import find_best_map_for_run
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.analysis.lap_eligibility import eligible_laps


NEXT_GEN_PATTERNS = (
    "next gen",
    "stockcars chevycamarozl12022",
    "stockcars fordmustang2022",
    "stockcars toyotacamry2022",
    "chevy camaro zl1 2022",
    "ford mustang 2022",
    "toyota camry 2022",
)
LEGACY_OVAL_PATTERNS = (
    "xfinity",
    "truck",
    "late model",
    "gen 6",
    "gen6",
    "chevy ss",
    "arca",
    "modified",
    "nationwide",
)
TRACK_FAMILY_HINTS = {
    "superspeedway": {"daytona", "talladega"},
    "intermediate_oval": {"charlotte", "atlanta", "texas", "kansas", "lasvegas", "homestead", "michigan", "autoclub", "chicagoland"},
    "short_track": {"bristol", "martinsville", "richmond", "phoenix", "wilkesboro", "irp", "newhampshire"},
}

PLATFORM_TRACE_CHANNELS = {
    "cfs_ride_height_in",
    "cfs_ride_height_mm",
    "cfsr_height_mm",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    "lf_ride_height_mm",
    "rf_ride_height_mm",
    "lr_ride_height_mm",
    "rr_ride_height_mm",
    "front_center_rh_in",
    "rear_center_rh_in",
    "center_rake_in",
    "center_rake_fs_in",
    "smooth_center_rake_in",
    "side_rake_in",
}
FRONT_PLATFORM_CHANNELS = {
    "cfs_ride_height_in",
    "cfs_ride_height_mm",
    "cfsr_height_mm",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lf_ride_height_mm",
    "rf_ride_height_mm",
    "front_center_rh_in",
    "front_split_in",
    "front_platform_risk_score",
    "cfs_risk_score",
}
REAR_PLATFORM_CHANNELS = {
    "lr_ride_height_in",
    "rr_ride_height_in",
    "lr_ride_height_mm",
    "rr_ride_height_mm",
    "rear_center_rh_in",
    "rear_min_ride_height_in",
    "rear_min_ride_height_mm",
    "rear_platform_risk_score",
    "rear_platform_contact_risk",
}
DIFFUSER_PROXY_CHANNELS = {
    "front_center_rh_in",
    "rear_center_rh_in",
    "center_rake_in",
    "smooth_center_rake_in",
    "diffuser_base_volume_ft3",
    "diffuser_wedge_volume_ft3",
    "diffuser_volume_ft3",
    "smooth_diffuser_volume_ft3",
    "diffuser_track_width_in",
    "diffuser_wheelbase_in",
}
REAR_SCRAPE_CHANNELS = {
    "rear_min_ride_height_in",
    "rear_min_ride_height_mm",
    "rear_scrape_margin_mm",
    "rear_scrape_risk_score",
    "rear_platform_contact_risk",
    "rear_scrape_side",
    "rear_scrape_side_label",
    "rear_scrub_proxy",
    "front_scrub_proxy",
    "drag_scrub_suspicion",
    "yaw_error_proxy",
}
SHOCK_CORE_CHANNELS = {
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
}
SHOCK_SUPPORT_CHANNELS = {
    "lf_shock_static_defl_in",
    "rf_shock_static_defl_in",
    "lr_shock_static_defl_in",
    "rr_shock_static_defl_in",
    "lf_shock_defl_delta_in",
    "rf_shock_defl_delta_in",
    "lr_shock_defl_delta_in",
    "rr_shock_defl_delta_in",
    "shock_velocity_rms",
    "shock_activity_index",
    "damper_energy_proxy",
    "lf_shock_activity_index",
    "rf_shock_activity_index",
    "lr_shock_activity_index",
    "rr_shock_activity_index",
    "lf_damper_energy_proxy",
    "rf_damper_energy_proxy",
    "lr_damper_energy_proxy",
    "rr_damper_energy_proxy",
}
TIRE_PRESSURE_CHANNELS = {
    "lf_pressure_gain",
    "rf_pressure_gain",
    "lr_pressure_gain",
    "rr_pressure_gain",
    "lf_tire_pressure",
    "rf_tire_pressure",
    "lr_tire_pressure",
    "rr_tire_pressure",
}
TIRE_TEMP_CHANNELS = {
    "lf_temp_inner",
    "lf_temp_middle",
    "lf_temp_outer",
    "rf_temp_inner",
    "rf_temp_middle",
    "rf_temp_outer",
    "lr_temp_inner",
    "lr_temp_middle",
    "lr_temp_outer",
    "rr_temp_inner",
    "rr_temp_middle",
    "rr_temp_outer",
    "lf_tire_temp_inner",
    "lf_tire_temp_middle",
    "lf_tire_temp_outer",
    "rf_tire_temp_inner",
    "rf_tire_temp_middle",
    "rf_tire_temp_outer",
    "lr_tire_temp_inner",
    "lr_tire_temp_middle",
    "lr_tire_temp_outer",
    "rr_tire_temp_inner",
    "rr_tire_temp_middle",
    "rr_tire_temp_outer",
    "rf_tire_temps",
}
TIRE_WEAR_CHANNELS = {
    "lf_wear_inner",
    "lf_wear_middle",
    "lf_wear_outer",
    "rf_wear_inner",
    "rf_wear_middle",
    "rf_wear_outer",
    "lr_wear_inner",
    "lr_wear_middle",
    "lr_wear_outer",
    "rr_wear_inner",
    "rr_wear_middle",
    "rr_wear_outer",
    "lf_wear_spread",
    "rf_wear_spread",
    "lr_wear_spread",
    "rr_wear_spread",
}
BRAKE_CHANNELS = {"brake_pct", "brake_01"}
THROTTLE_CHANNELS = {"throttle_pct", "throttle_01"}
STEERING_CHANNELS = {"steering_deg", "abs_steering_deg", "steering_rad"}
YAW_CHANNELS = {"yaw_rate", "yaw_error_proxy"}
SPEED_CHANNELS = {"speed_mph", "speed_mps", "speed_rate_mph_s", "grade_corrected_speed_loss_mph_s"}
RPM_GEAR_CHANNELS = {"rpm", "gear"}


@dataclass(frozen=True)
class RunContextSetupQueryResult:
    evidence_context: RunEvidenceContext
    setup_query: SetupQueryResult
    candidate_readiness: list[CandidateEvidenceReadiness]
    capability_flags: list[str]
    observed_evidence_flags: list[str]
    supporting_event_ids: list[str]
    supporting_event_ids_by_flag: dict[str, list[str]]
    supporting_event_ids_by_setup_key: dict[str, list[str]]
    source_channels_by_event_id: dict[str, list[str]]


def _sorted_present(available: set[str], aliases: set[str]) -> list[str]:
    return sorted(alias for alias in aliases if alias in available)


def _sorted_missing(available: set[str], aliases: set[str]) -> list[str]:
    return sorted(alias for alias in aliases if alias not in available)


def _recursive_has_keyword(value: Any, keywords: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(_recursive_has_keyword(key, keywords) or _recursive_has_keyword(item, keywords) for key, item in value.items())
    if isinstance(value, list):
        return any(_recursive_has_keyword(item, keywords) for item in value)
    if isinstance(value, str):
        lower = value.lower()
        return any(keyword in lower for keyword in keywords)
    return False


def _setup_snapshot_status(snapshot: SetupSnapshot | None) -> tuple[EvidenceStatus, list[str], list[str]]:
    if snapshot is None:
        return "missing", [], ["setup snapshot metadata"]
    present_items: list[str] = ["setup snapshot metadata"]
    missing_items: list[str] = []
    if snapshot.extracted_values:
        present_items.append("extracted setup values")
    else:
        missing_items.append("extracted setup values")
    if snapshot.setup_json:
        present_items.append("raw setup values")
    else:
        missing_items.append("raw setup values")
    status = "ready" if len(present_items) >= 2 else "partially_ready"
    return status, present_items, [] if status == "ready" else missing_items


def _build_group(
    *,
    group_id: str,
    label: str,
    status: EvidenceStatus,
    source: str,
    present_items: list[str],
    missing_items: list[str],
    channels_present: list[str],
    channels_missing: list[str],
    notes: list[str] | None = None,
    confidence_boost: float = 0.0,
    can_support_setup_knowledge: bool = False,
) -> RunEvidenceGroup:
    return RunEvidenceGroup(
        group_id=group_id,
        label=label,
        status=status,
        present_items=present_items,
        missing_items=missing_items,
        channels_present=channels_present,
        channels_missing=channels_missing,
        source=source,
        notes=notes or [],
        confidence_boost=confidence_boost,
        can_support_setup_knowledge=can_support_setup_knowledge,
    )


def _car_family_from_text(text: str) -> str:
    lower = text.lower()
    if any(pattern in lower for pattern in NEXT_GEN_PATTERNS):
        return "next_gen"
    if any(pattern in lower for pattern in LEGACY_OVAL_PATTERNS):
        return "legacy_oval_generic"
    return "unknown"


def resolve_car_family(
    overview: RunOverview,
    *,
    car_family_override: str | None = None,
) -> str:
    if car_family_override:
        return car_family_override
    snapshot = overview.setup_snapshot
    candidates = [
        overview.session.car_name,
        overview.session.car_path,
        snapshot.setup_name if snapshot else None,
        str(snapshot.setup_json) if snapshot and snapshot.setup_json else None,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = _car_family_from_text(candidate)
        if resolved != "unknown":
            return resolved
    return "unknown"


def resolve_track_family(
    overview: RunOverview,
    *,
    track_family_override: str | None = None,
) -> str:
    if track_family_override:
        return track_family_override
    raw_name = overview.session.track_display_name or overview.session.track_name or overview.session.track_id_or_path
    if not raw_name:
        return "unknown"
    layout = infer_layout_key(raw_name)
    if layout in {"road", "roval"}:
        return "road_course"
    if layout == "dirt":
        return "dirt_oval"
    track_key = normalize_track_key(raw_name)
    for family, keys in TRACK_FAMILY_HINTS.items():
        if track_key in keys:
            return family
    return "unknown"


def _driver_input_flags(groups: dict[str, RunEvidenceGroup], flags: set[str]) -> None:
    ready_inputs = {
        name
        for name in ("brake_trace", "throttle_trace", "steering_trace", "yaw_trace")
        if groups[name].status in {"ready", "partially_ready"}
    }
    if {"throttle_trace", "steering_trace"} <= ready_inputs:
        flags.add("driver_inputs")
    if ready_inputs:
        flags.add("driver_input")


QUALIFYING_EVENT_STATES = {
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
}


_EVENT_TYPE_MECHANISMS: dict[str, set[str]] = {
    "PLATFORM_LOW": {"platform", "platform_trace", "front_platform"},
    "PLATFORM_SCRAPE": {"platform", "platform_trace", "front_platform", "scrape"},
    "REAR_PLATFORM_LOW": {"platform", "platform_trace", "rear_platform"},
    "REAR_PLATFORM_SCRAPE": {"platform", "platform_trace", "rear_platform", "scrape"},
    "MIN_SPLITTER": {"platform", "platform_trace", "front_platform"},
    "MIN_REAR_RIDE_HEIGHT": {"platform", "platform_trace", "rear_platform"},
    "HIGHEST_RAKE": {"platform", "platform_trace"},
    "HIGHEST_PLATFORM_COMPRESSION": {"platform", "platform_trace"},
    "WHOLE_CAR_BOTTOMING_RISK": {"platform", "platform_trace"},
    "HIGHEST_SHOCK_ACTIVITY": {"shock_histogram"},
    "DAMPER_RESPONSE": {"shock_histogram"},
    "BRAKE_ENTRY_YAW": {"brake_trace", "yaw"},
    "BRAKE_INSTABILITY": {"brake_trace", "yaw"},
    "YAW_EXIT": {"yaw"},
    "THROTTLE_EXIT": {"throttle"},
    "TIRE_EXIT": {"tire_temps", "tire_trend"},
    "TIRE_PRESSURE": {"tire_pressure", "pressure_gain", "tire_trend"},
    "TIRE_WEAR": {"tire_wear", "wear", "tire_trend"},
    "FULL_THROTTLE_SPEED_LOSS": {"speed_loss", "speed_trace", "throttle"},
    "WORST_SPEED_LOSS": {"speed_loss", "speed_trace"},
    "WORST_DRAG_SCRUB": {"speed_loss", "speed_trace"},
    "RPM_GEAR_LIMITER": {"rpm"},
}

_MECHANISM_SOURCE_CHANNELS: dict[str, set[str]] = {
    "platform": PLATFORM_TRACE_CHANNELS,
    "platform_trace": PLATFORM_TRACE_CHANNELS,
    "front_platform": FRONT_PLATFORM_CHANNELS,
    "rear_platform": REAR_PLATFORM_CHANNELS,
    "scrape": FRONT_PLATFORM_CHANNELS | REAR_PLATFORM_CHANNELS | REAR_SCRAPE_CHANNELS,
    "shock_histogram": SHOCK_CORE_CHANNELS | SHOCK_SUPPORT_CHANNELS,
    "brake_trace": BRAKE_CHANNELS,
    "throttle": THROTTLE_CHANNELS,
    "steering": STEERING_CHANNELS,
    "yaw": YAW_CHANNELS,
    "speed_loss": SPEED_CHANNELS,
    "speed_trace": SPEED_CHANNELS,
    "rpm": RPM_GEAR_CHANNELS,
    "tire_pressure": TIRE_PRESSURE_CHANNELS,
    "pressure_gain": TIRE_PRESSURE_CHANNELS,
    "tire_temps": TIRE_TEMP_CHANNELS,
    "tire_wear": TIRE_WEAR_CHANNELS,
    "wear": TIRE_WEAR_CHANNELS,
    "tire_trend": TIRE_PRESSURE_CHANNELS | TIRE_TEMP_CHANNELS | TIRE_WEAR_CHANNELS,
}


def event_mechanism_flags(event_type: str, source_channels: set[str]) -> set[str]:
    """Translate a qualified observation into matcher evidence vocabulary.

    This deliberately runs only after the event passes canonical lap, tuning,
    provenance, and confidence gates.  Raw channel availability never reaches
    this function by itself.
    """
    claimed = _EVENT_TYPE_MECHANISMS.get(event_type.upper(), set())
    flags = {
        flag
        for flag in claimed
        if not (required := _MECHANISM_SOURCE_CHANNELS.get(flag)) or bool(source_channels & required)
    }
    if flags & {"throttle", "steering", "yaw", "brake_trace"} and len(
        flags & {"throttle", "steering", "yaw", "brake_trace"}
    ) >= 2:
        flags.update({"driver_input", "driver_inputs"})
    return flags


def event_matches_zone(event: Any, selected_zone: tuple[float, float] | None) -> bool:
    if selected_zone is None:
        return True
    start, end = event.lap_pct_start, event.lap_pct_end
    if start is not None and end is not None:
        return selected_zone[0] <= start <= end <= selected_zone[1]
    position = event.lap_pct_peak if event.lap_pct_peak is not None else start if start is not None else end
    return position is not None and selected_zone[0] <= position <= selected_zone[1]


def event_matches_phase(event: Any, requested_phase: str | None) -> bool:
    """Fail closed when an explicit phase cannot be tied to event provenance."""
    if not requested_phase:
        return True
    requested = requested_phase.strip().casefold().replace(" ", "_")
    explicit = str(
        event.evidence_json.get("phase")
        or event.evidence_json.get("target_phase")
        or event.evidence_json.get("corner_phase")
        or ""
    ).strip().casefold().replace(" ", "_")
    event_type = str(event.event_type).casefold()
    if explicit:
        requested_families = {
            "brake_application": "braking", "threshold_braking": "braking",
            "brake_release": "entry", "turn_in": "entry", "apex_region": "center",
            "initial_throttle": "exit", "full_throttle_exit": "exit",
            "following_straight_carry": "exit", "bump": "bump_curb", "curb": "bump_curb",
        }
        return requested_families.get(explicit, explicit) == requested_families.get(requested, requested)
    inferred: set[str] = set()
    type_families = {
        "braking": ("brake", "lock", "abs"),
        "entry": ("entry", "turn_in", "brake_release"),
        "center": ("center", "apex"),
        "exit": ("exit", "throttle", "drive_off"),
        "transition": ("transition",),
        "bump_curb": ("bump", "curb"),
        "straight": ("straight", "speed_loss", "resistance"),
    }
    inferred.update(
        family
        for family, markers in type_families.items()
        if any(marker in event_type for marker in markers)
    )
    requested_families = {
        "brake_application": "braking",
        "threshold_braking": "braking",
        "brake_release": "entry",
        "turn_in": "entry",
        "apex_region": "center",
        "initial_throttle": "exit",
        "full_throttle_exit": "exit",
        "following_straight_carry": "exit",
        "bump": "bump_curb",
        "curb": "bump_curb",
    }
    requested_family = requested_families.get(requested, requested)
    explicit_family = requested_families.get(explicit, explicit)
    return requested_family in inferred or explicit_family == requested_family


def _observed_mechanism_evidence(
    overview: RunOverview,
    *,
    eligible_lap_numbers: set[int],
    selected_zone: tuple[float, float] | None = None,
    selected_phase: str | None = None,
) -> tuple[list[str], list[str], dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    flags: set[str] = set()
    event_ids: list[str] = []
    event_ids_by_flag: dict[str, list[str]] = {}
    event_ids_by_setup_key: dict[str, list[str]] = {}
    source_channels_by_event_id: dict[str, list[str]] = {}
    for event in overview.events:
        if (
            not event.valid_for_tuning
            or event.lap_number not in eligible_lap_numbers
            or event.evidence_state not in QUALIFYING_EVENT_STATES
            or not math.isfinite(event.confidence_score)
            or not 0.5 <= event.confidence_score <= 1.0
            or event.blocker_reasons
            or not event.source_channels
            or not event_matches_phase(event, selected_phase)
            or not event_matches_zone(event, selected_zone)
        ):
            continue
        event_flags = event_mechanism_flags(event.event_type, set(event.source_channels))
        if not event_flags:
            continue
        flags.update(event_flags)
        event_ids.append(event.event_id)
        source_channels_by_event_id[event.event_id] = list(event.source_channels)
        for flag in event_flags:
            event_ids_by_flag.setdefault(flag, []).append(event.event_id)
        for setup_key in expanded_related_setup_keys(event.related_setup_keys):
            event_ids_by_setup_key.setdefault(setup_key, []).append(event.event_id)
    return (
        sorted(flags),
        list(dict.fromkeys(event_ids)),
        {flag: list(dict.fromkeys(ids)) for flag, ids in event_ids_by_flag.items()},
        {key: list(dict.fromkeys(ids)) for key, ids in event_ids_by_setup_key.items()},
        source_channels_by_event_id,
    )


def build_run_evidence_context(
    run_id: str,
    *,
    baseline_run_id: str | None = None,
    test_run_id: str | None = None,
    car_family_override: str | None = None,
    track_family_override: str | None = None,
    canonical_runtime_owned: bool = False,
) -> RunEvidenceContext:
    repo = RaceLabRepository()
    if not (overview := repo.get_overview(run_id)):
        raise ValueError(f"Run not found: {run_id}")

    channel_summary = build_channel_summary(run_id)
    available_channels = {item["name"] for item in channel_summary if item.get("missing_status") is None}

    warnings: list[str] = []
    unavailable_reasons: dict[str, str] = {}
    flags: set[str] = set()
    groups: dict[str, RunEvidenceGroup] = {}

    setup_status, setup_items, setup_missing = _setup_snapshot_status(overview.setup_snapshot)
    groups["setup_snapshot"] = _build_group(
        group_id="setup_snapshot",
        label="Setup Snapshot",
        status=setup_status,
        source="repository",
        present_items=setup_items,
        missing_items=setup_missing,
        channels_present=[],
        channels_missing=[],
        confidence_boost=0.35 if setup_status == "ready" else 0.15 if setup_status == "partially_ready" else 0.0,
    )
    if setup_status in {"ready", "partially_ready"}:
        flags.add("setup_snapshot")

    useful_laps = eligible_laps(overview.laps)
    if canonical_runtime_owned:
        observed_flags: list[str] = []
        observed_event_ids: list[str] = []
    else:
        observed_flags, observed_event_ids, _event_ids_by_flag, _, _ = (
            _observed_mechanism_evidence(
                overview,
                eligible_lap_numbers={lap.lap_number for lap in useful_laps},
            )
        )
    lap_status = "ready" if useful_laps else "missing"
    lap_present = ["lap/window data"] if useful_laps else []
    lap_missing = [] if useful_laps else ["lap/window data"]
    groups["lap_windows"] = _build_group(
        group_id="lap_windows",
        label="Lap Windows",
        status=lap_status,
        source="repository",
        present_items=lap_present,
        missing_items=lap_missing,
        channels_present=[],
        channels_missing=[],
        confidence_boost=0.2 if useful_laps else 0.0,
    )
    if useful_laps:
        flags.update({"lap_windows", "selected_lap_window", "phase"})
        if sum(lap.lap_time is not None for lap in useful_laps) >= 2:
            flags.add("lap_falloff")

    platform_present = _sorted_present(available_channels, PLATFORM_TRACE_CHANNELS)
    platform_status = "ready" if len(platform_present) >= 4 or {"front_center_rh_in", "rear_center_rh_in"} <= set(platform_present) else "partially_ready" if len(platform_present) >= 2 else "missing"
    groups["platform_trace"] = _build_group(
        group_id="platform_trace",
        label="Platform Trace",
        status=platform_status,
        source="channel_summary",
        present_items=["front/rear ride-height trace"] if platform_present else [],
        missing_items=[] if platform_present else ["front/rear ride-height trace"],
        channels_present=platform_present,
        channels_missing=_sorted_missing(available_channels, PLATFORM_TRACE_CHANNELS),
        confidence_boost=0.35 if platform_status == "ready" else 0.15 if platform_status == "partially_ready" else 0.0,
    )
    if platform_status in {"ready", "partially_ready"}:
        flags.update({"platform_trace", "platform"})

    front_present = _sorted_present(available_channels, FRONT_PLATFORM_CHANNELS)
    front_status = "ready" if ("front_center_rh_in" in front_present or "cfs_ride_height_in" in front_present or "cfs_ride_height_mm" in front_present) and len(front_present) >= 3 else "partially_ready" if front_present else "missing"
    groups["front_ride_height_platform"] = _build_group(
        group_id="front_ride_height_platform",
        label="Front Ride-Height Platform",
        status=front_status,
        source="channel_summary",
        present_items=["front platform geometry"] if front_present else [],
        missing_items=[] if front_present else ["front platform geometry"],
        channels_present=front_present,
        channels_missing=_sorted_missing(available_channels, FRONT_PLATFORM_CHANNELS),
        confidence_boost=0.35 if front_status == "ready" else 0.15 if front_status == "partially_ready" else 0.0,
    )
    if front_status in {"ready", "partially_ready"}:
        flags.update({"front_ride_height_platform", "front_platform", "cfs_front_feed"})

    rear_present = _sorted_present(available_channels, REAR_PLATFORM_CHANNELS)
    rear_status = "ready" if ("rear_center_rh_in" in rear_present or "rear_min_ride_height_mm" in rear_present or "rear_min_ride_height_in" in rear_present) and len(rear_present) >= 3 else "partially_ready" if rear_present else "missing"
    groups["rear_ride_height_platform"] = _build_group(
        group_id="rear_ride_height_platform",
        label="Rear Ride-Height Platform",
        status=rear_status,
        source="channel_summary",
        present_items=["rear platform geometry"] if rear_present else [],
        missing_items=[] if rear_present else ["rear platform geometry"],
        channels_present=rear_present,
        channels_missing=_sorted_missing(available_channels, REAR_PLATFORM_CHANNELS),
        confidence_boost=0.35 if rear_status == "ready" else 0.15 if rear_status == "partially_ready" else 0.0,
    )
    if rear_status in {"ready", "partially_ready"}:
        flags.update({"rear_ride_height_platform", "rear_platform"})

    diffuser_present = _sorted_present(available_channels, DIFFUSER_PROXY_CHANNELS)
    diffuser_status = "ready" if {"front_center_rh_in", "rear_center_rh_in"} <= set(diffuser_present) and len(diffuser_present) >= 4 else "partially_ready" if len(diffuser_present) >= 2 else "missing"
    diffuser_notes = [FORCE_PROXY_WARNING] if diffuser_present else []
    groups["diffuser_proxy"] = _build_group(
        group_id="diffuser_proxy",
        label="Diffuser Proxy",
        status=diffuser_status,
        source="channel_summary",
        present_items=["derived diffuser geometry proxy"] if diffuser_present else [],
        missing_items=[] if diffuser_present else ["derived diffuser geometry proxy"],
        channels_present=diffuser_present,
        channels_missing=_sorted_missing(available_channels, DIFFUSER_PROXY_CHANNELS),
        notes=diffuser_notes,
        confidence_boost=0.25 if diffuser_status == "ready" else 0.1 if diffuser_status == "partially_ready" else 0.0,
    )
    if diffuser_status in {"ready", "partially_ready"}:
        flags.add("diffuser_proxy")
        warnings.append("Derived diffuser geometry proxy is available. Treat it as geometry context, not measured downforce.")

    scrape_present = _sorted_present(available_channels, REAR_SCRAPE_CHANNELS)
    scrape_status = "ready" if any(name in scrape_present for name in ("rear_scrape_margin_mm", "rear_scrape_risk_score", "rear_platform_contact_risk")) else "partially_ready" if scrape_present else "missing"
    groups["rear_scrape_scrub"] = _build_group(
        group_id="rear_scrape_scrub",
        label="Rear Scrape / Scrub",
        status=scrape_status,
        source="channel_summary",
        present_items=["rear scrape/scrub proxy"] if scrape_present else [],
        missing_items=[] if scrape_present else ["rear scrape/scrub proxy"],
        channels_present=scrape_present,
        channels_missing=_sorted_missing(available_channels, REAR_SCRAPE_CHANNELS),
        confidence_boost=0.25 if scrape_status == "ready" else 0.1 if scrape_status == "partially_ready" else 0.0,
    )
    if scrape_status in {"ready", "partially_ready"}:
        flags.update({"rear_scrape_scrub", "scrape"})
        if any(name in scrape_present for name in ("drag_scrub_suspicion", "rear_scrub_proxy", "front_scrub_proxy", "yaw_error_proxy")):
            flags.add("yaw_scrub_steering")

    shock_present = _sorted_present(available_channels, SHOCK_CORE_CHANNELS | SHOCK_SUPPORT_CHANNELS)
    shock_core_present = _sorted_present(available_channels, SHOCK_CORE_CHANNELS)
    shock_status = "ready" if len(shock_core_present) == 4 else "partially_ready" if shock_present else "missing"
    shock_notes: list[str] = []
    if shock_status == "missing" and overview.setup_snapshot and _recursive_has_keyword(overview.setup_snapshot.setup_json, ("shock", "damper", "rebound", "compression")):
        shock_notes.append("Garage damper settings exist, but live shock movement telemetry is unavailable.")
        warnings.append("Garage damper settings exist, but live shock movement telemetry is unavailable.")
    groups["shock_histogram"] = _build_group(
        group_id="shock_histogram",
        label="Shock Histogram",
        status=shock_status,
        source="channel_summary",
        present_items=["live shock movement telemetry"] if shock_present else [],
        missing_items=[] if shock_present else ["live shock movement telemetry"],
        channels_present=shock_present,
        channels_missing=_sorted_missing(available_channels, SHOCK_CORE_CHANNELS | SHOCK_SUPPORT_CHANNELS),
        notes=shock_notes,
        confidence_boost=0.35 if shock_status == "ready" else 0.15 if shock_status == "partially_ready" else 0.0,
    )
    if shock_status in {"ready", "partially_ready"}:
        flags.add("shock_histogram")
        if any(name in shock_present for name in ("shock_velocity_rms", "shock_activity_index", "damper_energy_proxy")):
            flags.add("shock_rms_activity")

    tire_pressure_present = _sorted_present(available_channels, TIRE_PRESSURE_CHANNELS)
    tire_pressure_status = "ready" if len(tire_pressure_present) >= 4 else "partially_ready" if len(tire_pressure_present) >= 2 else "missing"
    groups["tire_pressure"] = _build_group(
        group_id="tire_pressure",
        label="Tire Pressure",
        status=tire_pressure_status,
        source="channel_summary",
        present_items=["tire pressure / gain telemetry"] if tire_pressure_present else [],
        missing_items=[] if tire_pressure_present else ["tire pressure / gain telemetry"],
        channels_present=tire_pressure_present,
        channels_missing=_sorted_missing(available_channels, TIRE_PRESSURE_CHANNELS),
        confidence_boost=0.25 if tire_pressure_status == "ready" else 0.1 if tire_pressure_status == "partially_ready" else 0.0,
    )
    if tire_pressure_status in {"ready", "partially_ready"}:
        flags.update({"tire_pressure", "pressure_gain"})

    tire_temp_present = _sorted_present(available_channels, TIRE_TEMP_CHANNELS)
    tire_temp_status = "ready" if len(tire_temp_present) >= 4 else "partially_ready" if tire_temp_present else "missing"
    groups["tire_temps"] = _build_group(
        group_id="tire_temps",
        label="Tire Temps",
        status=tire_temp_status,
        source="channel_summary",
        present_items=["tire temperature telemetry"] if tire_temp_present else [],
        missing_items=[] if tire_temp_present else ["tire temperature telemetry"],
        channels_present=tire_temp_present,
        channels_missing=_sorted_missing(available_channels, TIRE_TEMP_CHANNELS),
        confidence_boost=0.25 if tire_temp_status == "ready" else 0.1 if tire_temp_status == "partially_ready" else 0.0,
    )
    if tire_temp_status in {"ready", "partially_ready"}:
        flags.add("tire_temps")
        if "rf_tire_temps" in tire_temp_present:
            flags.add("rf_tire_temps")

    tire_wear_present = _sorted_present(available_channels, TIRE_WEAR_CHANNELS)
    tire_wear_status = "ready" if len(tire_wear_present) >= 4 else "partially_ready" if tire_wear_present else "missing"
    groups["tire_wear"] = _build_group(
        group_id="tire_wear",
        label="Tire Wear",
        status=tire_wear_status,
        source="channel_summary",
        present_items=["tire wear telemetry"] if tire_wear_present else [],
        missing_items=[] if tire_wear_present else ["tire wear telemetry"],
        channels_present=tire_wear_present,
        channels_missing=_sorted_missing(available_channels, TIRE_WEAR_CHANNELS),
        confidence_boost=0.2 if tire_wear_status == "ready" else 0.1 if tire_wear_status == "partially_ready" else 0.0,
    )
    if tire_wear_status in {"ready", "partially_ready"}:
        flags.update({"tire_wear", "wear"})

    for group_id, label, aliases, canonical in (
        ("brake_trace", "Brake Trace", BRAKE_CHANNELS, "brake_trace"),
        ("throttle_trace", "Throttle Trace", THROTTLE_CHANNELS, "throttle"),
        ("steering_trace", "Steering Trace", STEERING_CHANNELS, "steering"),
        ("yaw_trace", "Yaw Trace", YAW_CHANNELS, "yaw"),
        ("speed_trace", "Speed Trace", SPEED_CHANNELS, "speed_trace"),
    ):
        present = _sorted_present(available_channels, aliases)
        status = "ready" if present else "missing"
        groups[group_id] = _build_group(
            group_id=group_id,
            label=label,
            status=status,
            source="channel_summary",
            present_items=[label.lower()] if present else [],
            missing_items=[] if present else [label.lower()],
            channels_present=present,
            channels_missing=_sorted_missing(available_channels, aliases),
            confidence_boost=0.2 if present else 0.0,
        )
        if present:
            flags.add(canonical)
            if group_id == "speed_trace" and any(name in present for name in ("grade_corrected_speed_loss_mph_s", "speed_rate_mph_s")):
                flags.add("speed_loss")

    rpm_gear_present = _sorted_present(available_channels, RPM_GEAR_CHANNELS | SPEED_CHANNELS)
    rpm_gear_status = "ready" if {"rpm", "gear"} <= set(rpm_gear_present) else "partially_ready" if "rpm" in rpm_gear_present or "gear" in rpm_gear_present else "missing"
    groups["rpm_gear_trace"] = _build_group(
        group_id="rpm_gear_trace",
        label="RPM / Gear Trace",
        status=rpm_gear_status,
        source="channel_summary",
        present_items=["rpm / gear telemetry"] if rpm_gear_present else [],
        missing_items=[] if rpm_gear_present else ["rpm / gear telemetry"],
        channels_present=rpm_gear_present,
        channels_missing=_sorted_missing(available_channels, RPM_GEAR_CHANNELS | SPEED_CHANNELS),
        confidence_boost=0.2 if rpm_gear_present else 0.0,
    )
    if rpm_gear_status in {"ready", "partially_ready"}:
        flags.update({"rpm_gear_trace", "rpm"})

    track_name = overview.session.track_display_name or overview.session.track_name
    layout_hint = infer_layout_key(overview.session.track_id_or_path or track_name)
    match = find_best_map_for_run(run_id, track_name, layout=layout_hint) if track_name else None
    track_status = "ready" if match else "unavailable"
    track_notes = [f"Matched local track map: {match.get('display_name')}"] if match else []
    groups["track_map"] = _build_group(
        group_id="track_map",
        label="Track Map",
        status=track_status,
        source="track_map_service",
        present_items=["local track map package"] if match else [],
        missing_items=[] if match else ["local track map package"],
        channels_present=[],
        channels_missing=[],
        notes=track_notes,
        confidence_boost=0.15 if match else 0.0,
    )
    if match:
        flags.update({"track_map", "track_map_zone", "selected_zone"})
    else:
        unavailable_reasons["track_map"] = "No matching local track map package found for this run."

    baseline_exists = bool(baseline_run_id and repo.get_overview(baseline_run_id))
    test_exists = bool(test_run_id and repo.get_overview(test_run_id))
    for group_id, label, exists, run_value in (
        ("compare_baseline", "Baseline Compare Context", baseline_exists, baseline_run_id),
        ("compare_test", "Test Compare Context", test_exists, test_run_id),
    ):
        if run_value is None:
            status = "unavailable"
            unavailable_reasons[group_id] = "No compare run was supplied."
        else:
            status = "ready" if exists else "missing"
            if not exists:
                unavailable_reasons[group_id] = f"Run not found: {run_value}"
        groups[group_id] = _build_group(
            group_id=group_id,
            label=label,
            status=status,
            source="repository",
            present_items=[run_value] if exists and run_value else [],
            missing_items=[] if exists else ([run_value] if run_value else ["compare run id"]),
            channels_present=[],
            channels_missing=[],
            confidence_boost=0.1 if exists else 0.0,
        )
        if exists:
            flags.add(group_id)
    if baseline_exists and test_exists:
        flags.add("compare_baseline_test")

    if groups["tire_pressure"].status in {"ready", "partially_ready"} or groups["tire_temps"].status in {"ready", "partially_ready"}:
        flags.add("tire_trend")
    _driver_input_flags(groups, flags)

    car_family = resolve_car_family(overview, car_family_override=car_family_override)
    track_family = resolve_track_family(overview, track_family_override=track_family_override)
    if car_family == "unknown":
        warnings.append("Car family could not be resolved confidently. Use --car-family to unlock car-specific setup knowledge.")
    if track_family == "unknown":
        warnings.append("Track family could not be resolved confidently. Track-family weighting will stay neutral.")

    ordered_group_ids = [
        "setup_snapshot",
        "lap_windows",
        "platform_trace",
        "front_ride_height_platform",
        "rear_ride_height_platform",
        "diffuser_proxy",
        "rear_scrape_scrub",
        "shock_histogram",
        "tire_pressure",
        "tire_temps",
        "tire_wear",
        "brake_trace",
        "throttle_trace",
        "steering_trace",
        "yaw_trace",
        "speed_trace",
        "rpm_gear_trace",
        "track_map",
        "compare_baseline",
        "compare_test",
    ]
    observed_group_ids = {
        "platform_trace" if flag in {"platform", "platform_trace"} else
        "front_ride_height_platform" if flag == "front_platform" else
        "rear_ride_height_platform" if flag == "rear_platform" else
        "rear_scrape_scrub" if flag in {"scrape", "rear_scrape_scrub"} else
        "shock_histogram" if flag == "shock_histogram" else
        "tire_pressure" if flag in {"tire_pressure", "pressure_gain"} else
        "tire_temps" if flag in {"tire_temps", "tire_trend"} else
        "tire_wear" if flag in {"tire_wear", "wear"} else
        "brake_trace" if flag == "brake_trace" else
        "throttle_trace" if flag == "throttle" else
        "steering_trace" if flag == "steering" else
        "yaw_trace" if flag == "yaw" else
        "speed_trace" if flag in {"speed_trace", "speed_loss"} else
        "rpm_gear_trace" if flag == "rpm" else
        ""
        for flag in observed_flags
    }
    for group_id in observed_group_ids - {""}:
        group = groups[group_id]
        groups[group_id] = group.model_copy(update={
            "can_support_setup_knowledge": True,
            "notes": [
                *group.notes,
                f"Qualified telemetry event linkage: {', '.join(observed_event_ids)}.",
            ],
        })
    if not observed_event_ids:
        warnings.append(
            "Telemetry capability is available, but no eligible tuning event supplies observed mechanism evidence."
        )
    return RunEvidenceContext(
        run_id=run_id,
        car_name=overview.session.car_name,
        car_family=car_family,
        track_name=track_name,
        track_family=track_family,
        setup_snapshot_status=setup_status,
        evidence_groups=[groups[group_id] for group_id in ordered_group_ids],
        evidence_flags=sorted(flags),
        warnings=warnings,
        unavailable_reasons=unavailable_reasons,
    )


def query_setup_for_run_context(
    run_id: str,
    symptom: str,
    *,
    evidence_context: RunEvidenceContext | None = None,
    baseline_run_id: str | None = None,
    test_run_id: str | None = None,
    car_family_override: str | None = None,
    track_family_override: str | None = None,
    package_archetype: str | None = None,
    selected_lap: int | None = None,
    selected_zone: tuple[float, float] | None = None,
    phase: str | None = None,
    objective: str | None = None,
    priority: str | None = None,
    limit: int = 5,
    canonical_runtime_owned: bool = False,
) -> RunContextSetupQueryResult:
    context = evidence_context or build_run_evidence_context(
        run_id,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        car_family_override=car_family_override,
        track_family_override=track_family_override,
        canonical_runtime_owned=canonical_runtime_owned,
    )
    repo = RaceLabRepository()
    overview = repo.get_overview(run_id)
    observed_evidence_flags: list[str] = []
    supporting_event_ids: list[str] = []
    supporting_event_ids_by_flag: dict[str, list[str]] = {}
    supporting_event_ids_by_setup_key: dict[str, list[str]] = {}
    source_channels_by_event_id: dict[str, list[str]] = {}
    learning_biases: dict[tuple[str, int], dict[str, Any]] = {}
    effective_phase = phase
    if not effective_phase:
        try:
            effective_phase = parse_symptom(symptom, load_setup_knowledge()).phase
        except ValueError:
            effective_phase = None
    if overview is not None and not canonical_runtime_owned:
        eligible = eligible_laps(overview.laps)
        scoped_laps = (
            {selected_lap}
            if selected_lap is not None and selected_lap in {lap.lap_number for lap in eligible}
            else {lap.lap_number for lap in eligible}
        )
        (
            observed_evidence_flags,
            supporting_event_ids,
            supporting_event_ids_by_flag,
            supporting_event_ids_by_setup_key,
            source_channels_by_event_id,
        ) = _observed_mechanism_evidence(
            overview,
            eligible_lap_numbers=scoped_laps,
            selected_zone=selected_zone,
            selected_phase=effective_phase,
        )
        eligible_numbers = {lap.lap_number for lap in eligible}
        learning_lap = (
            selected_lap
            if selected_lap in eligible_numbers
            else min(
                eligible,
                key=lambda lap: lap.lap_time if lap.lap_time is not None else float("inf"),
            ).lap_number if eligible else None
        )
        learning_rows = read_telemetry_rows(
            run_id,
            lap=learning_lap,
            columns=[
                "air_temp",
                "track_temp",
                "wind_vel",
                "fuel_level",
                "lf_tire_distance_m",
                "rf_tire_distance_m",
                "lr_tire_distance_m",
                "rr_tire_distance_m",
                "player_tire_compound",
            ],
        ) if learning_lap is not None else []
        identity = read_telemetry_manifest(run_id).get("compatibility_identity") or {}
        session_type = str(identity.get("session_type") or "").lower()
        inferred_objective = (
            "qualifying"
            if "qual" in session_type
            else "long-run"
            if "race" in session_type
            else "setup-development"
        )
        memory_objective = (objective or inferred_objective).strip()
        if priority and priority != "overall-pace":
            memory_objective = f"{memory_objective}|priority:{priority}"
        response_context = build_setup_response_context(
            compatibility_identity=identity,
            rows=learning_rows,
            baseline_setup=(
                overview.setup_snapshot.model_dump(mode="json")
                if overview.setup_snapshot is not None
                else None
            ),
            package_archetype=package_archetype or context.track_family,
            objective=memory_objective,
        )
        if selected_zone is not None and effective_phase:
            learning_biases = get_setup_area_biases(
                response_context.car_name if response_context is not None else None,
                response_context.track_name if response_context is not None else None,
                response_context=response_context,
                target_zone=selected_zone,
                target_phase=effective_phase,
            )
    setup_result = query_setup_knowledge(
        car_family=car_family_override or context.car_family,
        symptom=symptom,
        phase=phase,
        track_family=track_family_override or context.track_family,
        package_archetype=package_archetype,
        evidence=context.evidence_flags,
        observed_evidence=observed_evidence_flags,
        limit=limit,
        learning_biases=learning_biases,
    )
    linked_candidates = []
    for item in setup_result.candidate_effects:
        control_keys = control_keys_for_effect(item.effect.effect_id)
        control_links = {
            key: set(supporting_event_ids_by_setup_key.get(key, ()))
            for key in control_keys
        }
        related_ids = {event_id for ids in control_links.values() for event_id in ids}
        mechanism_links_complete = bool(item.observed_evidence_matched) and all(
            set(supporting_event_ids_by_flag.get(flag, ())) & related_ids
            for flag in item.observed_evidence_matched
        )
        exact_control_links_complete = bool(control_links) and all(control_links.values())
        if item.readiness == "ready" and not (
            mechanism_links_complete and exact_control_links_complete
        ):
            item = replace(
                item,
                readiness="partially_ready",
                ranking_reasons=[
                    *item.ranking_reasons,
                    "observed mechanisms are not linked to every exact setup control in this action",
                ],
                warning="Observed mechanism events do not provide exact-control linkage for this action.",
            )
        linked_candidates.append(item)
    setup_result = replace(setup_result, candidate_effects=linked_candidates)
    candidate_readiness = [
        CandidateEvidenceReadiness(
            effect_id=item.effect.effect_id,
            readiness=item.readiness,
            present_evidence=item.evidence_matched,
            missing_evidence=item.missing_evidence,
            warnings=[item.warning] if item.warning else [],
            readiness_reason=next(
                (
                    reason
                    for reason in item.ranking_reasons
                    if "mechanism" in reason or "capability" in reason
                ),
                item.ranking_reasons[0],
            ),
        )
        for item in setup_result.candidate_effects
    ]
    return RunContextSetupQueryResult(
        evidence_context=context,
        setup_query=setup_result,
        candidate_readiness=candidate_readiness,
        capability_flags=context.evidence_flags,
        observed_evidence_flags=observed_evidence_flags,
        supporting_event_ids=supporting_event_ids,
        supporting_event_ids_by_flag=supporting_event_ids_by_flag,
        supporting_event_ids_by_setup_key=supporting_event_ids_by_setup_key,
        source_channels_by_event_id=source_channels_by_event_id,
    )


def run_context_result_to_dict(result: RunContextSetupQueryResult) -> dict[str, Any]:
    payload = query_result_to_dict(result.setup_query)
    payload.update(
        {
            "run_id": result.evidence_context.run_id,
            "car_name": result.evidence_context.car_name,
            "car_family": result.evidence_context.car_family,
            "track_name": result.evidence_context.track_name,
            "track_family": result.evidence_context.track_family,
            "setup_snapshot_status": result.evidence_context.setup_snapshot_status,
            "evidence_flags": result.evidence_context.evidence_flags,
            "capability_flags": result.capability_flags,
            "observed_evidence_flags": result.observed_evidence_flags,
            "supporting_event_ids": result.supporting_event_ids,
            "supporting_event_ids_by_flag": result.supporting_event_ids_by_flag,
            "supporting_event_ids_by_setup_key": result.supporting_event_ids_by_setup_key,
            "evidence_groups": [group.model_dump() for group in result.evidence_context.evidence_groups],
            "run_warnings": result.evidence_context.warnings,
            "unavailable_reasons": result.evidence_context.unavailable_reasons,
            "candidate_readiness": [item.model_dump() for item in result.candidate_readiness],
        }
    )
    return payload
