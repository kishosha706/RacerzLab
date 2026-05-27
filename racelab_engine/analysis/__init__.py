"""Telemetry analysis contracts and MVP analyzers."""

from racelab_engine.analysis.calculated_channels import (
    normalize_telemetry_rows,
    channel_metadata,
    CHANNEL_METADATA,
    CALCULATED_CHANNEL_UNITS,
    CORE_REQUIRED_CHANNELS,
    HIGH_VALUE_RAW_CHANNELS,
)
from racelab_engine.analysis.vectorized_channels import (
    normalize_telemetry_frame,
    calculate_core_channels_frame,
    frame_to_rows,
    CORE_CHANNELS,
    get_analysis_engine_mode,
    compare_row_vs_vectorized,
)
from racelab_engine.analysis.drag_scrub import (
    compute_drag_scrub_index,
    aero_normalized_resistance,
    detect_drag_scrub_risk_zones,
)
from racelab_engine.analysis.platform_events import (
    detect_platform_events,
    PlatformEvent,
)
from racelab_engine.analysis.constants import (
    FORCE_PROXY_WARNING,
    FORCE_PROXY_CHANNELS,
    SLIP_RATIO_SPEED_FLOOR_MPS,
    SLIP_RATIO_CLAMP_MAX,
    REFERENCE_DYNAMIC_PRESSURE_PA,
)
from racelab_engine.analysis.units import (
    MPS_TO_MPH,
    M_TO_FT,
    M_TO_IN,
    PA_TO_PSF,
)

__all__ = [
    # Row path
    "normalize_telemetry_rows",
    "channel_metadata",
    "CHANNEL_METADATA",
    "CALCULATED_CHANNEL_UNITS",
    "CORE_REQUIRED_CHANNELS",
    "HIGH_VALUE_RAW_CHANNELS",
    # Vector path
    "normalize_telemetry_frame",
    "calculate_core_channels_frame",
    "frame_to_rows",
    "CORE_CHANNELS",
    "get_analysis_engine_mode",
    "compare_row_vs_vectorized",
    # Drag/scrub
    "compute_drag_scrub_index",
    "aero_normalized_resistance",
    "detect_drag_scrub_risk_zones",
    # Platform events
    "detect_platform_events",
    "PlatformEvent",
    # Constants
    "FORCE_PROXY_WARNING",
    "FORCE_PROXY_CHANNELS",
    "SLIP_RATIO_SPEED_FLOOR_MPS",
    "SLIP_RATIO_CLAMP_MAX",
    "REFERENCE_DYNAMIC_PRESSURE_PA",
    # Units
    "MPS_TO_MPH",
    "M_TO_FT",
    "M_TO_IN",
    "PA_TO_PSF",
]

