from __future__ import annotations

from racelab_engine.analysis.calculated_channels import (
    _compute_slip_ratios,
    _compute_tire_derived,
    SLIP_RATIO_SPEED_FLOOR_MPS,
    SLIP_RATIO_CLAMP_MAX,
)


def test_slip_ratio_near_zero_speed_uses_floor() -> None:
    """When speed is near zero, denominator should floor at SLIP_RATIO_SPEED_FLOOR_MPS."""
    item = {
        "speed_mps": 0.001,  # near stationary
        "LFspeed": 0.5,
        "RFspeed": 0.5,
        "LRspeed": 0.5,
        "RRspeed": 0.5,
    }
    _compute_slip_ratios(item)
    # Should not explode — denominator floored at 1.0 m/s
    lf_slip = item.get("lf_slip_ratio")
    assert lf_slip is not None
    assert abs(lf_slip) <= SLIP_RATIO_CLAMP_MAX


def test_slip_ratio_zero_speed_does_not_explode() -> None:
    """Zero speed should produce clamped slip ratio, not NaN or inf."""
    item = {
        "speed_mps": 0.0,
        "LFspeed": 0.1,
        "RFspeed": 0.1,
        "LRspeed": 0.1,
        "RRspeed": 0.1,
    }
    _compute_slip_ratios(item)
    lf_slip = item.get("lf_slip_ratio")
    assert lf_slip is not None
    from math import isfinite
    assert isfinite(lf_slip)


def test_slip_ratio_normal_speed() -> None:
    """Normal driving speed should produce reasonable slip ratios."""
    item = {
        "speed_mps": 50.0,  # m/s
        "LFspeed": 50.5,  # slightly faster = positive slip
        "RFspeed": 50.5,
        "LRspeed": 50.3,
        "RRspeed": 50.3,
    }
    _compute_slip_ratios(item)
    lf_slip = item.get("lf_slip_ratio")
    assert lf_slip is not None
    assert 0.005 < lf_slip < 0.015  # ~1% slip


def test_slip_ratio_negative_slip() -> None:
    """Wheel speed slower than vehicle = negative slip (braking)."""
    item = {
        "speed_mps": 50.0,
        "LFspeed": 49.0,
        "RFspeed": 49.0,
        "LRspeed": 49.0,
        "RRspeed": 49.0,
    }
    _compute_slip_ratios(item)
    lf_slip = item.get("lf_slip_ratio")
    assert lf_slip is not None
    assert lf_slip < 0


def test_slip_ratio_clamped() -> None:
    """Extreme slip values should be clamped to SLIP_RATIO_CLAMP_MAX."""
    item = {
        "speed_mps": 1.0,
        "LFspeed": 10.0,  # huge difference
        "RFspeed": 10.0,
        "LRspeed": 10.0,
        "RRspeed": 10.0,
    }
    _compute_slip_ratios(item)
    lf_slip = item.get("lf_slip_ratio")
    assert lf_slip is not None
    assert abs(lf_slip) <= SLIP_RATIO_CLAMP_MAX


def test_tire_derived_slip_ratio_uses_floor() -> None:
    """_compute_tire_derived should also use the floored denominator."""
    item = {
        "lf_speed": 0.3,
        "rf_speed": 0.3,
        "lr_speed": 0.3,
        "rr_speed": 0.3,
        "speed_mps": 0.01,  # near stationary
    }
    _compute_tire_derived(item)
    slip = item.get("lf_slip_ratio_proxy")
    assert slip is not None
    from math import isfinite
    assert isfinite(slip)
    assert abs(slip) <= SLIP_RATIO_CLAMP_MAX


def test_driven_wheel_slip_proxy_uses_floor() -> None:
    """driven_wheel_slip_proxy should not explode at low speed."""
    item = {
        "speed_mps": 0.001,
        "LRspeed": 0.5,
        "RRspeed": 0.5,
    }
    _compute_slip_ratios(item)
    slip = item.get("driven_wheel_slip_proxy")
    assert slip is not None
    from math import isfinite
    assert isfinite(slip)
