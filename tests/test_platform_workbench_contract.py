from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.services.import_service import ImportService, build_channel_catalog, build_trace_payload


def test_platform_calculated_channels_from_rows() -> None:
    rows = normalize_telemetry_rows(
        [
            {
                "SessionTime": 0.0,
                "LapDist": 0.0,
                "LapDistPct": 0.10,
                "Speed": 80.0,
                "AirDensity": 1.20,
                "Throttle": 1.0,
                "Brake": 0.0,
                "CFSRrideHeight": 0.004,
                "LFrideHeight": 0.045,
                "RFrideHeight": 0.049,
                "LRrideHeight": 0.092,
                "RRrideHeight": 0.095,
            },
            {
                "SessionTime": 1.0,
                "LapDist": 80.0,
                "LapDistPct": 0.11,
                "Speed": 79.0,
                "AirDensity": 1.20,
                "Throttle": 1.0,
                "Brake": 0.0,
                "CFSRrideHeight": 0.0035,
                "LFrideHeight": 0.044,
                "RFrideHeight": 0.049,
                "LRrideHeight": 0.092,
                "RRrideHeight": 0.095,
            },
        ]
    )
    first, second = rows

    assert first["lap_dist_ft"] == pytest.approx(0.0)
    assert second["lap_dist_ft"] == pytest.approx(262.467, abs=0.01)
    assert first["lap_dist_pct_100"] == pytest.approx(10.0)
    assert first["speed_mph"] == pytest.approx(178.9549, abs=0.001)
    assert first["speed_fps"] == pytest.approx(262.467, abs=0.001)
    assert first["cfs_ride_height_in"] == pytest.approx(0.15748, abs=0.0001)
    assert first["center_rake_fs_in"] == pytest.approx(((0.092 + 0.095) / 2 * 39.37007874) - 0.15748, abs=0.001)
    assert first["side_rake_in"] == pytest.approx(((0.049 + 0.095) / 2 - (0.045 + 0.092) / 2) * 39.37007874, abs=0.001)
    assert first["dynamic_pressure_pa"] == pytest.approx(3840.0)
    assert first["dynamic_pressure_psf"] == pytest.approx(80.20, abs=0.05)
    assert second["speed_rate_mph_s"] == pytest.approx(-2.236936292)
    assert second["speed_rate_mph_1000ft"] == pytest.approx(-8.52, abs=0.05)


def test_missing_channel_and_geometry_behavior_is_safe() -> None:
    rows = normalize_telemetry_rows([{"SessionTime": 0.0, "Speed": 50.0}])
    row = rows[0]

    assert row["speed_mph"] == pytest.approx(111.8468, abs=0.001)
    assert row.get("dynamic_pressure_pa") is None
    assert row.get("center_rake_fs_in") is None
    assert row.get("platform_pitch_deg_from_rh") is None
    assert row.get("platform_roll_deg_from_rh") is None


def test_talladega_platform_anchor_and_extrema_downsample(
    tmp_path: Path, talladega_ibt_path: Path
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    result, _cache = ImportService(db_path=db_path, data_dir=data_dir).import_ibt_file(talladega_ibt_path)
    assert result.overview is not None
    run_id = result.overview.run_id

    trace = build_trace_payload(
        run_id,
        lap=2,
        x_axis="lap_dist_ft",
        channels=["cfs_ride_height_in", "center_rake_fs_in", "side_rake_in", "dynamic_pressure_psf"],
        downsample=50,
        preserve_extrema=True,
        events=result.overview.events,
        data_dir=data_dir,
    )

    cfs_values = trace["channels"]["cfs_ride_height_in"]["values"]
    min_index, min_cfs = min(
        ((index, value) for index, value in enumerate(cfs_values) if value is not None),
        key=lambda item: item[1],
    )

    assert min_cfs == pytest.approx(0.141, abs=0.01)
    assert trace["x"][min_index] == pytest.approx(9397, abs=25)
    assert trace["channels"]["center_rake_fs_in"]["values"][min_index] == pytest.approx(3.57, abs=0.05)
    assert trace["channels"]["side_rake_in"]["values"][min_index] == pytest.approx(0.125, abs=0.03)
    assert trace["channels"]["dynamic_pressure_psf"]["values"][min_index] == pytest.approx(86.0, abs=1.0)


def test_channel_catalog_and_trace_api_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, talladega_ibt_path: Path
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    client = TestClient(app)
    run_id = client.post("/api/imports/ibt", json={"path": str(talladega_ibt_path)}).json()["run_id"]

    catalog_response = client.get(f"/api/runs/{run_id}/channels")
    assert catalog_response.status_code == 200
    catalog = {item["name"]: item for item in catalog_response.json()}
    assert catalog["CFSRrideHeight"]["is_raw"] is True
    assert catalog["cfs_ride_height_in"]["is_calculated"] is True
    assert catalog["center_rake_fs_in"]["missing_status"] is None

    service_catalog = {item["name"]: item for item in build_channel_catalog(run_id, data_dir)}
    assert service_catalog["dynamic_pressure_psf"]["mean"] is not None

    trace_response = client.get(
        f"/api/runs/{run_id}/trace",
        params={
            "lap": 2,
            "x": "lap_dist_ft",
            "channels": "throttle_pct,center_rake_fs_in,side_rake_in,cfs_ride_height_in,dynamic_pressure_psf",
            "downsample": "auto",
            "preserve_extrema": "true",
        },
    )
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace["x_name"] == "lap_dist_ft"
    assert trace["x_unit"] == "ft"
    assert trace["preserve_extrema"] is True
    assert "values" in trace["channels"]["cfs_ride_height_in"]
    assert trace["events"]
