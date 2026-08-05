"""Edge case tests for drag/scrub physics, slip ratio, and scrub proxies.

Verifies the 8 edge cases from the engineering audit:
1. Superspeedway full throttle, high speed, normal aero decel → low/medium drag_scrub
2. Lower-speed corner with same raw decel → higher drag_scrub
3. Missing dynamic_pressure_psf → unavailable, no invented fallback
4. Missing track width → corrected mismatch null, raw preserved
5. Near-zero vehicle speed with wheel speed noise → bounded slip ratio
6. High steering + correct yaw response → no over-warning
7. High steering + yaw under-response → yaw_error_proxy raises scrub
8. Old saved runs/notebook entries → backward compat via aliases
"""

from __future__ import annotations

import math
import pytest

from racelab_engine.analysis.drag_scrub import aero_normalized_resistance, compute_drag_scrub_index
from racelab_engine.analysis.calculated_channels import (
    _compute_slip_ratios,
    _compute_scrub_proxies,
    _compute_tire_derived,
    SLIP_RATIO_CLAMP_MAX,
)


# ── Edge case 1: Superspeedway aero decel ─────────────────────

def test_superspeedway_aero_decel_low_index() -> None:
    """High speed, full throttle, normal aero decel should produce low index."""
    row = {
        "speed_mph": 185.0,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -1.5,  # normal aero decel at 185 mph
        "dynamic_pressure_psf": 120.0,  # high aero load
        "abs_steering_deg": 0.5,
        "yaw_rate": 0.02,
        "cfs_risk_score": 0.1,
    }
    index = compute_drag_scrub_index(row)
    assert index == pytest.approx(0.30, abs=0.05)


# ── Edge case 2: Lower-speed corner, same raw decel ───────────

def test_lower_speed_same_decel_higher_index() -> None:
    """Same raw decel at lower speed (but still above min) = higher index."""
    superspeedway = {
        "speed_mph": 185.0,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -1.5,
        "dynamic_pressure_psf": 120.0,
        "abs_steering_deg": 0.5,
        "yaw_rate": 0.02,
        "cfs_risk_score": 0.1,
    }
    # 155 mph is above DRAG_SCRUB_MIN_SPEED_MPH (150) but has lower dynamic pressure
    medium_speed = {
        "speed_mph": 155.0,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -1.5,  # same raw decel
        "dynamic_pressure_psf": 80.0,  # lower aero load than 185 mph
        "abs_steering_deg": 3.0,
        "yaw_rate": 0.10,
        "cfs_risk_score": 0.2,
    }
    ss_index = compute_drag_scrub_index(superspeedway)
    ms_index = compute_drag_scrub_index(medium_speed)
    # resistance_coeff: 1.5/120 = 0.0125 vs 1.5/80 = 0.01875
    # resistance_index: 0.0125/0.02 = 0.625 vs 0.01875/0.02 = 0.9375
    # The medium-speed case should have higher index due to lower aero normalization
    assert ms_index > ss_index, (
        f"Expected medium-speed ({ms_index:.3f}) > superspeedway ({ss_index:.3f})"
    )


# ── Edge case 3: Missing dynamic_pressure_psf ─────────────────

def test_missing_dynamic_pressure_remains_unavailable() -> None:
    """Missing dynamic pressure must not be converted to an invented force context."""
    row = {
        "speed_mph": 180.0,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "speed_rate_mph_s": -2.0,
        # no dynamic_pressure_psf
        "abs_steering_deg": 1.0,
        "yaw_rate": 0.05,
        "cfs_risk_score": 0.1,
    }
    coeff = aero_normalized_resistance(row)
    assert coeff is None

    index = compute_drag_scrub_index(row)
    assert index is None


# ── Edge case 4: Missing track width ──────────────────────────

def test_missing_track_width_preserves_raw() -> None:
    """When track width is missing, corrected mismatch is None, raw preserved."""
    item = {
        "RFspeed": 50.5,
        "LFspeed": 50.0,
        "RRspeed": 50.3,
        "LRspeed": 50.0,
        "yaw_rate": 0.1,
        "Speed": 50.0,
        # no front_track_width_m, no rear_track_width_m
    }
    _compute_slip_ratios(item)
    # Raw mismatch should be set
    assert item.get("front_wheel_speed_mismatch_raw") is not None
    assert item.get("rear_wheel_speed_mismatch_raw") is not None
    # Corrected mismatch should be None (no track width)
    assert item.get("front_wheel_speed_mismatch_corrected") is None
    assert item.get("rear_wheel_speed_mismatch_corrected") is None


# ── Edge case 5: Near-zero speed slip ratio ───────────────────

def test_near_zero_speed_slip_bounded() -> None:
    """Near-zero vehicle speed with wheel speed noise should stay bounded."""
    item = {
        "Speed": 0.01,  # ~0.02 mph
        "LFspeed": 0.5,
        "RFspeed": 0.5,
        "LRspeed": 0.5,
        "RRspeed": 0.5,
    }
    _compute_slip_ratios(item)
    for key in ["lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio"]:
        slip = item.get(key)
        assert slip is not None, f"{key} should not be None"
        assert math.isfinite(slip), f"{key} should be finite, got {slip}"
        assert abs(slip) <= SLIP_RATIO_CLAMP_MAX, f"{key} should be clamped, got {slip}"


def test_near_zero_speed_tire_derived_bounded() -> None:
    """Tire-derived slip ratio at near-zero speed should also be bounded."""
    item = {
        "lf_speed": 0.3,
        "rf_speed": 0.3,
        "lr_speed": 0.3,
        "rr_speed": 0.3,
        "speed_mps": 0.01,
    }
    _compute_tire_derived(item)
    for key in ["lf_slip_ratio_proxy", "rf_slip_ratio_proxy", "lr_slip_ratio_proxy", "rr_slip_ratio_proxy"]:
        slip = item.get(key)
        assert slip is not None, f"{key} should not be None"
        assert math.isfinite(slip), f"{key} should be finite, got {slip}"
        assert abs(slip) <= SLIP_RATIO_CLAMP_MAX, f"{key} should be clamped, got {slip}"


# ── Edge case 6: High steering + correct yaw response ─────────

def test_high_steering_correct_yaw_no_overwarning() -> None:
    """High steering with matching yaw response should not over-warn."""
    item = {
        "lf_slip_ratio": 0.01,
        "rf_slip_ratio": 0.01,
        "lr_slip_ratio": 0.01,
        "rr_slip_ratio": 0.01,
        "abs_steering_deg": 15.0,
        "abs_lat_accel": 8.0,
        "speed_mps": 50.0,
        "yaw_rate": 0.3,  # high yaw = car is rotating = correct response
        "radius_m": 166.7,  # 50 m/s / 0.3 rad/s
    }
    _compute_scrub_proxies(item)
    # yaw_error should be near zero because yaw matches curvature
    yaw_error = item.get("yaw_error_proxy", 0)
    assert yaw_error < 0.05, f"Expected low yaw error, got {yaw_error}"
    scrub = item.get("front_scrub_proxy", 0)
    # Should be moderate, not extreme
    assert scrub < 0.5, f"Expected moderate scrub, got {scrub}"


# ── Edge case 7: High steering + yaw under-response ───────────

def test_high_steering_yaw_underresponse_raises_scrub() -> None:
    """High steering with low yaw (understeer) should raise scrub via yaw_error."""
    item = {
        "lf_slip_ratio": 0.01,
        "rf_slip_ratio": 0.01,
        "lr_slip_ratio": 0.01,
        "rr_slip_ratio": 0.01,
        "abs_steering_deg": 15.0,
        "abs_lat_accel": 5.0,
        "speed_mps": 50.0,
        "yaw_rate": 0.05,  # low yaw = car not rotating = understeer
        "radius_m": 166.7,  # theoretical yaw = 50/166.7 = 0.3 rad/s
    }
    _compute_scrub_proxies(item)
    # yaw_error should be significant
    yaw_error = item.get("yaw_error_proxy", 0)
    assert yaw_error > 0.1, f"Expected significant yaw error, got {yaw_error}"
    scrub = item.get("front_scrub_proxy", 0)
    # Should be higher than the correct-yaw case
    assert scrub > 0.3, f"Expected elevated scrub, got {scrub}"


# ── Edge case 8: Backward compat via aliases ──────────────────

def test_dynamic_pressure_index_alias() -> None:
    """dynamic_pressure_index should still be set as alias for dynamic_pressure_lap_index."""
    # This is tested implicitly by _apply_derivatives setting both.
    # We verify the channel metadata has both registered.
    from racelab_engine.analysis.calculated_channels import channel_metadata
    meta_lap = channel_metadata("dynamic_pressure_lap_index")
    meta_old = channel_metadata("dynamic_pressure_index")
    assert meta_lap["comparable_across_runs"] is False
    assert meta_old["comparable_across_runs"] is False
    assert meta_lap["label"] != meta_old["label"]  # different labels


def test_aero_load_index_comparable() -> None:
    """aero_load_index should be marked comparable across runs."""
    from racelab_engine.analysis.calculated_channels import channel_metadata
    meta = channel_metadata("aero_load_index")
    assert meta["comparable_across_runs"] is True
