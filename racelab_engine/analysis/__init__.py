"""Telemetry analysis contracts and MVP analyzers."""

from racelab_engine.analysis.calculated_channels import (
    CALCULATED_CHANNEL_UNITS,
    CHANNEL_METADATA,
    CORE_REQUIRED_CHANNELS,
    HIGH_VALUE_RAW_CHANNELS,
    channel_metadata,
    normalize_telemetry_rows,
)

# ── Vectorized path — lazy/eager depending on polars availability ──
# The vectorized engine requires polars, which is an optional dependency.
# If polars is not installed, these names resolve to None and callers
# should check before use.  This prevents cascading import failures
# across the entire analysis package.

_VECTORIZED_AVAILABLE = False
_normalize_telemetry_frame = None
_calculate_core_channels_frame = None
_frame_to_rows = None
_CORE_CHANNELS: set[str] = set()
_get_analysis_engine_mode = None
_compare_row_vs_vectorized = None

from contextlib import suppress  # noqa: E402

with suppress(ImportError):  # noqa: E402
    from racelab_engine.analysis.vectorized_channels import (
        CORE_CHANNELS as _cc,
    )
    from racelab_engine.analysis.vectorized_channels import (
        calculate_core_channels_frame as _ccf,
    )
    from racelab_engine.analysis.vectorized_channels import (
        compare_row_vs_vectorized as _crvv,
    )
    from racelab_engine.analysis.vectorized_channels import (
        frame_to_rows as _ftr,
    )
    from racelab_engine.analysis.vectorized_channels import (
        get_analysis_engine_mode as _gaem,
    )
    from racelab_engine.analysis.vectorized_channels import (
        normalize_telemetry_frame as _nft,
    )
    _normalize_telemetry_frame = _nft
    _calculate_core_channels_frame = _ccf
    _frame_to_rows = _ftr
    _CORE_CHANNELS = _cc
    _get_analysis_engine_mode = _gaem
    _compare_row_vs_vectorized = _crvv
    _VECTORIZED_AVAILABLE = True


def normalize_telemetry_frame(*args, **kwargs):
    """Vectorised equivalent of normalize_telemetry_rows.  Requires polars."""
    if not _VECTORIZED_AVAILABLE:
        raise ImportError(
            "The vectorized analysis engine requires polars. "
            "Install it with: pip install polars"
        )
    return _normalize_telemetry_frame(*args, **kwargs)  # type: ignore[misc]


def calculate_core_channels_frame(*args, **kwargs):
    if not _VECTORIZED_AVAILABLE:
        raise ImportError("The vectorized analysis engine requires polars.")
    return _calculate_core_channels_frame(*args, **kwargs)  # type: ignore[misc]


def frame_to_rows(*args, **kwargs):
    if not _VECTORIZED_AVAILABLE:
        raise ImportError("The vectorized analysis engine requires polars.")
    return _frame_to_rows(*args, **kwargs)  # type: ignore[misc]


def CORE_CHANNELS() -> set[str]:
    if not _VECTORIZED_AVAILABLE:
        raise ImportError("The vectorized analysis engine requires polars.")
    return _CORE_CHANNELS


def get_analysis_engine_mode(*args, **kwargs):
    """Resolve the analysis engine mode.  Always available (no polars required)."""
    if _VECTORIZED_AVAILABLE:
        return _get_analysis_engine_mode(*args, **kwargs)  # type: ignore[misc]
    # Without polars, only "row" is available
    return "row"


def compare_row_vs_vectorized(*args, **kwargs):
    if not _VECTORIZED_AVAILABLE:
        raise ImportError("The vectorized analysis engine requires polars.")
    return _compare_row_vs_vectorized(*args, **kwargs)  # type: ignore[misc]


from racelab_engine.analysis.constants import (  # noqa: E402
    CALCULATED_PROXY_CHANNELS,
    DIFFUSER_GEOMETRY_PROXY_CHANNELS,
    FORCE_PROXY_CHANNELS,
    FORCE_PROXY_WARNING,
    REFERENCE_DYNAMIC_PRESSURE_PA,
    SLIP_RATIO_CLAMP_MAX,
    SLIP_RATIO_SPEED_FLOOR_MPS,
)
from racelab_engine.analysis.drag_scrub import (  # noqa: E402
    aero_normalized_resistance,
    compute_drag_scrub_index,
    detect_drag_scrub_risk_zones,
)
from racelab_engine.analysis.platform_events import (  # noqa: E402
    PlatformEvent,
    PlatformEventType,
    detect_platform_events,
)
from racelab_engine.analysis.platform_metrics import (  # noqa: E402
    classify_splitter_height_mm,
)
from racelab_engine.analysis.qualified_clock import (  # noqa: E402
    QualifiedTelemetryClock,
    build_qualified_telemetry_clock,
)
from racelab_engine.analysis.units import (  # noqa: E402
    M_TO_FT,
    M_TO_IN,
    MPS_TO_MPH,
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
    "classify_splitter_height_mm",
    # Platform events
    "detect_platform_events",
    "PlatformEvent",
    "PlatformEventType",
    # Qualified base-record clock
    "QualifiedTelemetryClock",
    "build_qualified_telemetry_clock",
    # Constants
    "FORCE_PROXY_WARNING",
    "FORCE_PROXY_CHANNELS",
    "DIFFUSER_GEOMETRY_PROXY_CHANNELS",
    "CALCULATED_PROXY_CHANNELS",
    "SLIP_RATIO_SPEED_FLOOR_MPS",
    "SLIP_RATIO_CLAMP_MAX",
    "REFERENCE_DYNAMIC_PRESSURE_PA",
    # Units
    "MPS_TO_MPH",
    "M_TO_FT",
    "M_TO_IN",
    "PA_TO_PSF",
]
