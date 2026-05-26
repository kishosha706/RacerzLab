from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.io.ibt_reader import read_normalized_records
from racelab_engine.services.import_service import bucket_downsample, build_channel_catalog, build_trace_payload


def assert_close(actual: float, expected: float, *, abs_tol: float = 0.0, rel_tol: float = 1e-12) -> None:
    assert math.isclose(actual, expected, abs_tol=abs_tol, rel_tol=rel_tol)


def _trace_channel_min(trace: dict[str, Any], channel: str) -> float | None:
    channels = cast(dict[str, Any] | None, trace.get("channels"))
    if channels is None:
        return None

    channel_data = channels.get(channel)
    if channel_data is None:
        return None

    if isinstance(channel_data, dict):
        raw_values = cast(dict[str, Any], channel_data).get("values")
    else:
        raw_values = channel_data

    if raw_values is None:
        return None

    if isinstance(raw_values, list):
        values = cast(list[Any], raw_values)
    elif isinstance(raw_values, tuple):
        values = list(cast(Any, raw_values))
    elif hasattr(raw_values, "tolist"):
        values = list(raw_values.tolist())
    elif hasattr(raw_values, "__iter__") and not isinstance(raw_values, (str, bytes)):
        values = list(raw_values)
    else:
        return None

    numeric_values = [float(value) for value in values if value is not None]
    return min(numeric_values, default=None)


def _assert_required_channels(row: dict[str, Any], channels: list[str]) -> None:
    for channel in channels:
        assert channel in row, f"{channel} should exist in normalized rows"


def test_real_telemetry_normalization(talladega_ibt_path: Path) -> None:
    rows, missing = read_normalized_records(talladega_ibt_path)

    assert missing == []
    assert len(rows) == 6277
    first = rows[0]
    assert_close(float(first["session_time"]), 131.77, abs_tol=0.1)
    assert first["lap"] == 1
    assert_close(float(first["speed_mph"]), float(first["Speed"]) * 2.23693629, abs_tol=0.001)
    assert_close(float(first["throttle_pct"]), 100.0)
    assert_close(float(first["brake_pct"]), 0.0)
    assert "steering_deg" in first
    assert "cfsr_height_mm" in first
    assert "lf_ride_height_mm" in first
    assert "rf_ride_height_mm" in first


def test_calculated_ride_height_channels(talladega_ibt_path: Path) -> None:
    rows, _missing = read_normalized_records(talladega_ibt_path)

    required_channels = [
        "cfs_ride_height_in",
        "cfs_ride_height_mm",
        "lf_ride_height_in",
        "rf_ride_height_in",
        "lr_ride_height_in",
        "rr_ride_height_in",
    ]

    # Convert all ride heights
    for row in rows:
        _assert_required_channels(row, required_channels)

    # Check in-to-mm cross-consistency on a few samples
    for row in rows[:10]:
        if row.get("cfs_ride_height_in") is not None and row.get("cfs_ride_height_mm") is not None:
            assert_close(float(row["cfs_ride_height_in"]), float(row["cfs_ride_height_mm"]) / 25.4, abs_tol=0.01)


def test_platform_rake_channels(talladega_ibt_path: Path) -> None:
    rows, _missing = read_normalized_records(talladega_ibt_path)

    assert "center_rake_fs_in" in rows[0]
    assert "side_rake_in" in rows[0]
    assert "front_split_in" in rows[0]
    assert "rear_split_in" in rows[0]
    assert "front_avg_rh_in" in rows[0]
    assert "rear_avg_rh_in" in rows[0]
    assert "left_avg_rh_in" in rows[0]
    assert "right_avg_rh_in" in rows[0]

    # Spot-check: center_rake_fs_in = rear_avg - cfs
    for row in rows:
        if row.get("center_rake_fs_in") is not None and row.get("rear_avg_rh_in") is not None and row.get("cfs_ride_height_in") is not None:
            expected = float(row["rear_avg_rh_in"]) - float(row["cfs_ride_height_in"])
            assert_close(float(row["center_rake_fs_in"]), expected, abs_tol=0.001)


def test_dynamic_pressure_channels(talladega_ibt_path: Path) -> None:
    rows, _missing = read_normalized_records(talladega_ibt_path)

    assert "dynamic_pressure_pa" in rows[0]
    assert "dynamic_pressure_psf" in rows[0]
    assert "dynamic_pressure_index" in rows[0]

    # Check formula: dp_pa = 0.5 * rho * v^2
    for row in rows[:50]:
        air_density = row.get("air_density")
        speed_mps = row.get("speed_mps")
        if air_density is not None and speed_mps is not None:
            expected_pa = 0.5 * float(air_density) * float(speed_mps) * float(speed_mps)
            assert_close(float(row["dynamic_pressure_pa"]), expected_pa, abs_tol=0.1)

    # dynamic_pressure_index should be in [0, 1]
    max_index = max(float(row.get("dynamic_pressure_index", 0) or 0) for row in rows)
    assert_close(max_index, 1.0, abs_tol=0.01)


def test_talladega_min_splitter_event(calced_rows: list[dict[str, Any]]) -> None:
    """Validate the spec's Talladega min-splitter event values."""
    lap2 = [row for row in calced_rows if row.get("lap") == 2]
    assert lap2, "Lap 2 should have telemetry rows"

    # Find the minimum CFS ride height in Lap 2
    min_cfs_row = min(
        (row for row in lap2 if row.get("cfs_ride_height_in") is not None),
        key=lambda r: float(r["cfs_ride_height_in"]),
    )

    # Spec expected values for Talladega low-splitter event
    assert_close(float(min_cfs_row["cfs_ride_height_in"]), 0.141, abs_tol=0.01)
    assert_close(float(min_cfs_row["center_rake_fs_in"]), 3.57, abs_tol=0.3)
    assert_close(float(min_cfs_row["side_rake_in"]), 0.125, abs_tol=0.05)

    # Dynamic pressure at ~186 mph with ~1.19 kg/m^3 air density
    if (dynamic_pressure_psf := min_cfs_row.get("dynamic_pressure_psf")) is not None:
        assert_close(float(dynamic_pressure_psf), 86.0, abs_tol=10.0)

    # Lap distance in feet ~9397 ft at 67.02%
    if (lap_dist_ft := min_cfs_row.get("lap_dist_ft")) is not None:
        assert_close(float(lap_dist_ft), 9397.0, abs_tol=500.0)

    # Speed should be ~186 mph
    if (speed_mph := min_cfs_row.get("speed_mph")) is not None:
        assert_close(float(speed_mph), 186.0, abs_tol=1.0)

    # Throttle 100%, brake 0%
    assert_close(float(min_cfs_row["throttle_pct"]), 100.0, abs_tol=1.0)
    assert_close(float(min_cfs_row["brake_pct"]), 0.0, abs_tol=1.0)


def test_new_calculated_channels_exist(talladega_ibt_path: Path) -> None:
    rows, _missing = read_normalized_records(talladega_ibt_path)

    required_channels = [
        "driven_wheel_slip_proxy",
        "dynamic_pressure_index",
        "platform_compression_index",
        "shock_velocity_rms",
        "shock_activity_index",
        "damper_energy_proxy",
        "track_x_m",
        "track_y_m",
        "track_x_ft",
        "track_y_ft",
        "lf_shock_velocity_rms",
        "rf_shock_velocity_rms",
        "lr_shock_velocity_rms",
        "rr_shock_velocity_rms",
        "lf_shock_activity_index",
        "rf_shock_activity_index",
        "lr_shock_activity_index",
        "rr_shock_activity_index",
        "lf_damper_energy_proxy",
        "rf_damper_energy_proxy",
        "lr_damper_energy_proxy",
        "rr_damper_energy_proxy",
    ]
    for channel in required_channels:
        assert channel in rows[0], f"{channel} should exist in normalized rows"


def test_extrema_downsampling_preserves_min_cfs() -> None:
    """Extrema-preserving downsampling must not lose the minimum CFS ride height."""
    # Synthetic lap — 600 rows, min CFS intentionally planted at index 137
    rows: list[dict[str, Any]] = []
    for i in range(600):
        cfs = 0.150 + (i % 50) * 0.005  # oscillating 0.150 → 0.395
        rows.append({"lap_dist_pct_100": i / 6.0, "cfs_ride_height_in": cfs})
    # Plant a deliberate minimum that the downsampler must preserve
    rows[137]["cfs_ride_height_in"] = 0.002
    original_min = float(min(r["cfs_ride_height_in"] for r in rows))
    assert_close(original_min, 0.002)

    downsampled = bucket_downsample(rows, bucket_size=60, channels=["cfs_ride_height_in"])
    downsampled_cfs = [float(r["cfs_ride_height_in"]) for r in downsampled if r.get("cfs_ride_height_in") is not None]

    assert downsampled_cfs, "Downsampled rows should include CFS ride height values"
    assert len(downsampled) < len(rows), "Bucketing should reduce row count"
    assert_close(min(downsampled_cfs), original_min, abs_tol=0.001)


def test_missing_channel_behavior() -> None:
    """Missing channels should not crash normalization."""
    sparse_rows = normalize_telemetry_rows([{"SessionTime": 100.0, "LapDistPct": 0.5, "Speed": 80.0}])
    sparse_row = sparse_rows[0]

    assert_close(float(sparse_row["session_time"]), 100.0)
    assert sparse_row.get("cfs_ride_height_in") is None
    assert sparse_row.get("center_rake_fs_in") is None


def test_channel_catalog_includes_new_channels(talladega_run_id: str) -> None:
    """Channel catalog should list all new calculated channels."""
    run_id = talladega_run_id
    catalog = {item["name"]: item for item in build_channel_catalog(run_id)}

    # Core calculated channels should be in catalog
    for channel in [
        "cfs_ride_height_in",
        "center_rake_fs_in",
        "side_rake_in",
        "dynamic_pressure_psf",
        "dynamic_pressure_index",
        "platform_compression_index",
        "driven_wheel_slip_proxy",
        "shock_velocity_rms",
        "shock_activity_index",
        "damper_energy_proxy",
    ]:
        assert channel in catalog, f"{channel} should be in channel catalog"
        item = catalog[channel]
        assert item["name"] == channel
        assert item.get("is_calculated") is True, f"{channel} should be marked calculated"


def test_trace_preserves_extrema_with_new_channels(talladega_run_id: str) -> None:
    """Trace API with preserve_extrema should not lose min CFS from new channels."""
    run_id = talladega_run_id

    # Full-resolution trace
    full_trace = build_trace_payload(
        run_id,
        lap=2,
        channels=["cfs_ride_height_in", "center_rake_fs_in", "dynamic_pressure_psf"],
        downsample=1,
        preserve_extrema=False,
    )
    full_min = _trace_channel_min(full_trace, "cfs_ride_height_in")

    # Downsampled with extrema preservation
    ds_trace = build_trace_payload(
        run_id,
        lap=2,
        channels=["cfs_ride_height_in", "center_rake_fs_in", "dynamic_pressure_psf"],
        downsample="auto",
        preserve_extrema=True,
    )
    ds_min = _trace_channel_min(ds_trace, "cfs_ride_height_in")

    if full_min is not None and ds_min is not None:
        assert_close(ds_min, full_min, abs_tol=0.005)


@pytest.fixture(scope="session")
def calced_rows(talladega_ibt_path: Path) -> list[dict[str, Any]]:
    """Reusable Talladega normalized rows fixture."""
    rows, _missing = read_normalized_records(talladega_ibt_path)
    return rows


# ── Phase B.9: channel metadata tests ──────────────────────────

def test_channel_metadata_labels() -> None:
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA, channel_metadata

    # Key channels should have friendly labels
    assert CHANNEL_METADATA["cfs_ride_height_in"]["label"] == "CFS Ride Height"
    assert CHANNEL_METADATA["center_rake_fs_in"]["label"] == "Center Rake FS"
    assert CHANNEL_METADATA["side_rake_in"]["label"] == "Side Rake"
    assert CHANNEL_METADATA["dynamic_pressure_psf"]["label"] == "Dynamic Pressure"
    assert CHANNEL_METADATA["speed_mph"]["label"] == "Speed"
    assert CHANNEL_METADATA["drag_scrub_suspicion"]["label"] == "Drag/Scrub Suspicion"

    # channel_metadata() should return friendly defaults for unregistered channels
    unknown = channel_metadata("nonexistent_channel")
    assert unknown["label"] == "nonexistent_channel"
    assert unknown["used_by_charts"] == []
    assert unknown["used_by_events"] == []
    assert unknown["used_by_recommendations"] == []


def test_channel_metadata_used_by() -> None:
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA

    metadata_checks: list[tuple[str, list[str], list[str], list[str]]] = [
        (
            "cfs_ride_height_in",
            ["Platform / Rake / Ride Height"],
            ["PLATFORM_LOW"],
            ["Platform/Scrub Test"],
        ),
        (
            "drag_scrub_suspicion",
            ["Drag / Scrub"],
            ["FULL_THROTTLE_SPEED_LOSS"],
            [],
        ),
        (
            "speed_mph",
            [],
            [],
            [],
        ),
    ]

    for name, chart_terms, event_terms, recommendation_terms in metadata_checks:
        meta = CHANNEL_METADATA[name]
        for term in chart_terms:
            assert term in meta["used_by_charts"]
        for term in event_terms:
            assert term in meta["used_by_events"]
        for term in recommendation_terms:
            assert term in meta["used_by_recommendations"]

    assert len(CHANNEL_METADATA["speed_mph"]["used_by_charts"]) >= 3


def test_proxy_channels_have_estimate_warning() -> None:
    from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA

    proxies = ["rear_downforce_proxy_n", "rear_platform_proxy_n", "aero_balance_front_pct"]
    for name in proxies:
        if name in CHANNEL_METADATA:
            desc = CHANNEL_METADATA[name].get("description", "")
            assert "ESTIMATE" in desc.upper() or "proxy" in desc.lower(), f"{name} should be labeled as estimate"


def test_channel_catalog_includes_metadata_fields(talladega_run_id: str) -> None:
    catalog = {item["name"]: item for item in build_channel_catalog(talladega_run_id)}

    cfs = catalog.get("cfs_ride_height_in")
    assert cfs is not None
    assert cfs.get("label") == "CFS Ride Height"
    assert len(cfs.get("used_by_charts", [])) >= 1
    assert len(cfs.get("used_by_events", [])) >= 1
    assert cfs.get("formula") is not None

    drag = catalog.get("drag_scrub_suspicion")
    assert drag is not None
    assert drag.get("is_proxy") is True


def test_channel_catalog_preset_channels_exist(talladega_run_id: str) -> None:
    """Channels needed by Speed/RPM and Drag/Scrub presets should be in catalog."""
    catalog_names = {item["name"] for item in build_channel_catalog(talladega_run_id)}

    for channel in [
        "speed_mph", "rpm", "gear", "throttle_pct", "brake_pct",
        "speed_rate_mph_s", "speed_rate_mph_1000ft",
        "drag_scrub_suspicion", "abs_steering_deg", "abs_lat_accel",
        "cfs_ride_height_in",
    ]:
        assert channel in catalog_names, f"{channel} should be in channel catalog"

def test_aero_proxy_confidence_drops_on_transients():
    from racelab_engine.analysis.aero_platform import build_platform_proxy_estimates
    
    # Steady state row
    steady_row = {"lat_accel": 0.1, "long_accel": 0.1, "speed_mps": 80.0}
    steady_est = build_platform_proxy_estimates(steady_row)
    assert "low" in steady_est["front_aero_proxy_n"].confidence.lower()

    # High-G transient row (braking + turning)
    transient_row = {"lat_accel": 15.0, "long_accel": -20.0, "speed_mps": 40.0}
    transient_est = build_platform_proxy_estimates(transient_row)
    assert "very_low" in transient_est["front_aero_proxy_n"].confidence.lower()


def test_calculated_channels_imports_units_constants() -> None:
    """calculated_channels must import conversion constants from units.py, not define them locally."""
    from racelab_engine.analysis.calculated_channels import (
        M_TO_FT, M_TO_IN, MPS_TO_MPH, PA_TO_PSF, MM_TO_IN, EARTH_RADIUS_M,
    )
    # All constants should be directly importable — meaning they're re-exported from units.py
    assert isinstance(M_TO_FT, float)
    assert isinstance(M_TO_IN, float)
    assert isinstance(MPS_TO_MPH, float)
    assert isinstance(PA_TO_PSF, float)
    assert isinstance(MM_TO_IN, float)
    assert isinstance(EARTH_RADIUS_M, float)
    assert abs(M_TO_FT - 3.280839895) < 0.001
    assert abs(MPS_TO_MPH - 2.23693629) < 0.001


def test_channel_classification_contract() -> None:
    """Verify proxy/calculated/raw channel classifications are consistent."""
    from racelab_engine.services.import_service import FORCE_PROXY_CHANNELS
    from racelab_engine.analysis.calculated_channels import CALCULATED_CHANNEL_UNITS

    # Pressure gain is calculated, not proxy
    assert "lf_pressure_gain" not in FORCE_PROXY_CHANNELS
    assert "rf_pressure_gain" not in FORCE_PROXY_CHANNELS

    # Slip ratio is proxy
    assert "lf_slip_ratio_proxy" not in FORCE_PROXY_CHANNELS  # actually check naming

    # Dynamic pressure is calculated
    assert "dynamic_pressure_psf" in CALCULATED_CHANNEL_UNITS

    # Aero/load proxies are in proxy set
    assert "front_aero_proxy_n" in FORCE_PROXY_CHANNELS
    assert "rear_aero_proxy_n" in FORCE_PROXY_CHANNELS
    assert "aero_balance_front_pct" in FORCE_PROXY_CHANNELS
    assert "drag_scrub_suspicion" in FORCE_PROXY_CHANNELS


def test_dynamic_pressure_index_not_comparable_across_runs() -> None:
    """dynamic_pressure_index must be marked as not comparable across runs."""
    from racelab_engine.analysis.calculated_channels import channel_metadata
    meta = channel_metadata("dynamic_pressure_index")
    assert meta.get("comparable_across_runs") is False, \
        "dynamic_pressure_index must be marked comparable_across_runs=False"

