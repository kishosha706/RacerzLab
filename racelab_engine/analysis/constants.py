"""Shared tuning constants for the analysis engine.

Centralizes thresholds and confidence baselines so that the Verdict engine,
Target Zone Classifier, and any future analysis modules stay in sync.
"""

# ── Speed thresholds (mph) ────────────────────────────────────
SPEED_NOISE_THRESHOLD = 0.05  # mph — below this is considered noise/no-change
SPEED_LARGE_CHANGE = 0.5  # mph — above this is a large/significant change

# ── CFS / ride height thresholds (inches) ─────────────────────
CFS_WORSEN_THRESHOLD = -0.001  # in — CFS delta below this is "worsened"
CFS_SIGNIFICANT = -0.01  # in — CFS delta below this is a significant risk change

# ── Steering thresholds (degrees) ─────────────────────────────
STEERING_CHANGE_THRESHOLD = 0.5  # deg — meaningful steering delta

# ── Drag / scrub thresholds (index) ───────────────────────────
DRAG_CHANGE_THRESHOLD = 0.05  # index — meaningful drag/scrub delta

# ── RPM thresholds ────────────────────────────────────────────
RPM_CHANGE_THRESHOLD = 50  # rpm — meaningful RPM delta

# ── Confidence baselines ──────────────────────────────────────
CONF_HIGH = 0.75
CONF_MEDIUM = 0.60
CONF_LOW = 0.45
CONF_NOISE = 0.25
CONF_KEEP_MIXED = 0.55
CONF_RETEST_DISCIPLINE = 0.35
CONF_INVALID = 0.1

# ── Splitter / CFS thresholds (mm) ────────────────────────────
SPLITTER_SCRAPE_MM = 0.0
SPLITTER_CRITICAL_MM = 3.0
SPLITTER_HIGH_MM = 6.0
SPLITTER_WATCH_MM = 10.0

# ── Platform validity gates ───────────────────────────────────
PLATFORM_VALID_MIN_SPEED_MPH = 100.0
DRAG_SCRUB_MIN_SPEED_MPH = 150.0

# ── Throttle / brake thresholds (%) ───────────────────────────
FULL_THROTTLE_PCT = 95.0
PLATFORM_VALID_THROTTLE_PCT = 80.0
LOW_BRAKE_PCT = 5.0

# ── Segment / grid defaults ───────────────────────────────────
SEGMENT_WIDTH_PCT = 5.0
COMPARE_GRID_STEP_PCT = 0.1
DEFAULT_TARGET_ZONE_START_PCT = 55.0
DEFAULT_TARGET_ZONE_END_PCT = 70.0

# ── Slip ratio safety ─────────────────────────────────────────
SLIP_RATIO_SPEED_FLOOR_MPS = 1.0
SLIP_RATIO_CLAMP_MAX = 2.0

# ── Lap wraparound detection ──────────────────────────────────
LAP_WRAP_DROP_THRESHOLD_PCT = -10.0

# ── Aero-normalized resistance ────────────────────────────────
RESISTANCE_COEFF_CRITICAL = 0.02  # (mph/s) / psf — threshold for "high" aero-normalized resistance
SEA_LEVEL_AIR_DENSITY_KG_M3 = 1.225
REFERENCE_SPEED_MPS = 80.4672  # ~180 mph
REFERENCE_DYNAMIC_PRESSURE_PA = 0.5 * SEA_LEVEL_AIR_DENSITY_KG_M3 * REFERENCE_SPEED_MPS ** 2

# ── Discipline labels ─────────────────────────────────────────
RELIABLE_DISCIPLINES = ("clean", "mostly_clean")

# ── WCI weight profiles ───────────────────────────────────────
WCI_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "superspeedway": {
        "speed": 0.36,
        "platform": 0.30,
        "driver": 0.08,
        "powertrain": 0.16,
        "shock": 0.00,
        "discipline": 0.10,
    },
    "oval": {
        "speed": 0.34,
        "platform": 0.30,
        "driver": 0.12,
        "powertrain": 0.14,
        "shock": 0.00,
        "discipline": 0.10,
    },
    "short_track": {
        "speed": 0.18,
        "platform": 0.18,
        "driver": 0.22,
        "powertrain": 0.24,
        "shock": 0.08,
        "discipline": 0.10,
    },
    "road_course": {
        "speed": 0.16,
        "platform": 0.14,
        "driver": 0.34,
        "powertrain": 0.12,
        "shock": 0.14,
        "discipline": 0.10,
    },
}

# ── Motion ratio helper ───────────────────────────────────────
def apply_motion_ratio(wheel_delta: float, motion_ratio: float | None) -> float:
    """Apply motion ratio to convert wheel delta to spring delta.
    Defaults to 1:1 if motion_ratio is unavailable."""
    if motion_ratio is None or motion_ratio <= 0:
        return wheel_delta
    return wheel_delta * motion_ratio


def logistic_score(
    delta: float | None,
    noise: float,
    steepness: float,
    higher_is_better: bool = True,
) -> float:
    """Logistic (sigmoid) scoring function for continuous WCI sub-scores.

    Maps delta to a 0-100 score. The noise threshold defines the deadband
    where score ~50 (neutral). Steepness controls how quickly the score
    saturates toward 0 or 100.
    """
    import math
    if delta is None:
        return 50.0
    signed_delta = delta if higher_is_better else -delta
    x = signed_delta - noise
    return 100.0 / (1.0 + math.exp(-steepness * x))
