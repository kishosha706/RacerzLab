from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.services.import_service import _build_summary_item

ROOT = Path(__file__).resolve().parents[1]
PROFILE_SHA = "a" * 64
RIDE_HEIGHT_ROW = {
    "SessionTime": 1.0,
    "LFrideHeight": 0.050,
    "RFrideHeight": 0.052,
    "LRrideHeight": 0.060,
    "RRrideHeight": 0.061,
}
DIFFUSER_DEPENDENT_CHANNELS = (
    "diffuser_track_width_in",
    "diffuser_wheelbase_in",
    "diffuser_rub_block_correction_in",
    "lr_height_rub_block_in",
    "rear_center_rh_in",
    "center_rake_in",
    "diffuser_base_volume_ft3",
    "diffuser_wedge_volume_ft3",
    "diffuser_volume_ft3",
    "smooth_diffuser_volume_ft3",
)


def reviewed_geometry() -> dict[str, object]:
    return {
        "geometry_source": "reviewed_vehicle_profile",
        "geometry_profile_sha256": PROFILE_SHA,
        "wheelbase_m": 2.794,
        "rear_track_width_m": 2.0066,
        "lr_rub_block_correction_in": 0.5,
    }


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {"wheelbase_m": 2.794, "rear_track_width_m": 2.0066},
        {
            "geometry_source": "reviewed_vehicle_profile",
            "geometry_profile_sha256": PROFILE_SHA,
            "wheelbase_m": 2.794,
            "rear_track_width_m": 2.0066,
        },
        {
            **reviewed_geometry(),
            "geometry_profile_sha256": "not-a-content-hash",
        },
    ],
)
def test_missing_or_unprovenanced_geometry_never_emits_diffuser_values(
    geometry: dict[str, object] | None,
) -> None:
    row = normalize_telemetry_rows([RIDE_HEIGHT_ROW], geometry=geometry)[0]

    assert row["front_center_rh_in"] is not None
    assert row["diffuser_geometry_source"] is None
    assert row["diffuser_geometry_profile_sha256"] is None
    assert all(row[channel] is None for channel in DIFFUSER_DEPENDENT_CHANNELS)


def test_reviewed_geometry_emits_only_content_bound_calculated_proxies() -> None:
    row = normalize_telemetry_rows([RIDE_HEIGHT_ROW], geometry=reviewed_geometry())[0]

    assert row["diffuser_geometry_source"] == "reviewed_vehicle_profile"
    assert row["diffuser_geometry_profile_sha256"] == PROFILE_SHA
    assert row["diffuser_wheelbase_in"] == pytest.approx(110.0, rel=5e-4)
    assert row["diffuser_track_width_in"] == pytest.approx(79.0, rel=5e-4)
    assert row["diffuser_rub_block_correction_in"] == pytest.approx(0.5)
    assert row["diffuser_volume_ft3"] is not None


def test_vector_and_row_paths_share_the_same_geometry_provenance_gate() -> None:
    pl = pytest.importorskip("polars")
    from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame

    unavailable = normalize_telemetry_frame(pl.DataFrame([RIDE_HEIGHT_ROW])).to_dicts()[0]
    admitted = normalize_telemetry_frame(
        pl.DataFrame([RIDE_HEIGHT_ROW]), geometry=reviewed_geometry()
    ).to_dicts()[0]
    row = normalize_telemetry_rows([RIDE_HEIGHT_ROW], geometry=reviewed_geometry())[0]

    assert all(unavailable[channel] is None for channel in DIFFUSER_DEPENDENT_CHANNELS)
    assert admitted["diffuser_geometry_profile_sha256"] == PROFILE_SHA
    assert admitted["diffuser_volume_ft3"] == pytest.approx(
        row["diffuser_volume_ft3"]
    )


def test_catalog_and_client_classify_every_diffuser_quantity_as_proxy() -> None:
    for channel in DIFFUSER_DEPENDENT_CHANNELS:
        item = _build_summary_item(
            channel,
            definition=None,
            is_raw=False,
            is_calculated=True,
            in_column_set=True,
        )
        assert item["is_calculated"] is True
        assert item["is_proxy"] is True

    client = (ROOT / "ui/src/utils/channelMeta.ts").read_text(encoding="utf-8")
    for channel in (
        "diffuser_track_width_in",
        "diffuser_wheelbase_in",
        "diffuser_base_volume_ft3",
        "diffuser_wedge_volume_ft3",
        "diffuser_volume_ft3",
        "smooth_diffuser_volume_ft3",
    ):
        definition = client.split(f"{channel}:", 1)[1].split("},", 1)[0]
        assert "isProxy: true" in definition
        assert "isCalculated: true" in definition


def test_platform_does_not_request_or_render_diffuser_volume_lanes() -> None:
    workbench = (ROOT / "ui/src/constants/workbenchChannels.ts").read_text(
        encoding="utf-8"
    )
    platform = (ROOT / "ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")

    assert "diffuser_volume_ft3" not in workbench
    assert "Smooth Diffuser Volume [ft3]" not in platform
    assert "Diffuser Base Volume [ft3]" not in platform
