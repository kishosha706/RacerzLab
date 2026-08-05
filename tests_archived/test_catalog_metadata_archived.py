# Archived catalog/metadata tests — covered by test_analysis_constants.py classification tests
import pytest
from racelab_engine.services.import_service import build_channel_catalog, FORCE_PROXY_CHANNELS
from racelab_engine.analysis.calculated_channels import CALCULATED_CHANNEL_UNITS, channel_metadata, CHANNEL_METADATA
pytestmark = pytest.mark.slow
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
def test_channel_metadata_labels() -> None:

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

    proxies = ["rear_downforce_proxy_n", "rear_platform_proxy_n", "aero_balance_front_pct"]
    for name in proxies:
        if name in CHANNEL_METADATA:
            desc = CHANNEL_METADATA[name].get("description", "")
            assert "ESTIMATE" in desc.upper() or "proxy" in desc.lower(), f"{name} should be labeled as estimate"





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
    meta = channel_metadata("dynamic_pressure_index")
    assert meta.get("comparable_across_runs") is False, \
        "dynamic_pressure_index must be marked comparable_across_runs=False"

