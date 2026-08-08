from __future__ import annotations

import math
import struct
from pathlib import Path

import polars as pl
import pytest

from api.schemas import ChannelCatalogItem, ChannelSummaryItem
from racelab_engine.analysis.calculated_channels import CORE_REQUIRED_CHANNELS, _REMAINING_ALIAS_MAP
from racelab_engine.analysis.channel_registry import canonical_mapping_kind, canonical_name
from racelab_engine.analysis.vectorized_channels import (
    _ALIAS_MAP as VECTOR_ALIAS_MAP,
    normalize_telemetry_frame,
)
from racelab_engine.io.ibt_reader import (
    IBTParseError,
    TARGET_CHANNELS,
    _merge_raw_columns,
    _merge_raw_rows,
    _read_records_columnar,
    _raw_archive_column_mapping,
    _validate_variable_definitions,
)
from racelab_engine.io.ibt_types import IBTHeader, IBTVariableDefinition
from racelab_engine.io.telemetry_manifest import (
    build_telemetry_manifest,
    assess_cache_compatibility,
    compatibility_fingerprint,
    compatibility_identity,
    schema_fingerprint,
)
from racelab_engine.services.import_service import (
    _assert_declared_channels_archived,
    ImportService,
    build_telemetry_capability_payload,
    build_channel_catalog,
    build_channel_summary,
    read_telemetry_manifest,
    write_channel_metadata,
    write_telemetry_cache,
    write_telemetry_manifest,
)


def test_every_core_channel_reaches_the_production_normalizer() -> None:
    assert set(CORE_REQUIRED_CHANNELS).issubset(TARGET_CHANNELS)


def test_production_vector_engine_materializes_every_simple_row_alias() -> None:
    expected_aliases = {
        raw_name: canonical_name
        for raw_name, canonical_name in _REMAINING_ALIAS_MAP.items()
        if raw_name in TARGET_CHANNELS
    }
    assert expected_aliases.items() <= VECTOR_ALIAS_MAP.items()

    raw_values = {
        "WaterTemp": [93.5],
        "OilTemp": [108.25],
        "FuelUsePerHour": [2.75],
        "EngineWarnings": [4],
    }
    normalized = normalize_telemetry_frame(pl.DataFrame(raw_values))

    assert normalized["water_temp"].to_list() == [93.5]
    assert normalized["oil_temp"].to_list() == [108.25]
    assert normalized["fuel_use_per_hour"].to_list() == [2.75]
    assert normalized["engine_warnings"].to_list() == [4]


def _definitions() -> list[IBTVariableDefinition]:
    return [
        IBTVariableDefinition(name="Speed", unit="m/s", data_type="float", data_type_id=4, offset=0),
        IBTVariableDefinition(name="MysterySignal", unit="widgets", data_type="float", data_type_id=4, offset=4),
        IBTVariableDefinition(
            name="SteeringWheelTorque_ST",
            unit="N*m",
            data_type="float",
            data_type_id=4,
            offset=8,
            count=6,
            count_as_time=True,
        ),
    ]


def test_raw_columns_are_additive_to_normalized_analysis_columns() -> None:
    normalized = pl.DataFrame({"sample_index": [0, 1], "speed_mps": [10.0, 11.0]})
    raw = {
        "sample_index": [0, 1],
        "Speed": [10.0, 11.0],
        "MysterySignal": [3.0, 4.0],
        "SteeringWheelTorque_ST": [[1.0] * 6, [2.0] * 6],
    }

    merged = _merge_raw_columns(normalized, raw)

    assert merged.columns == [
        "sample_index",
        "speed_mps",
        "raw__sample_index",
        "Speed",
        "MysterySignal",
        "SteeringWheelTorque_ST",
    ]
    assert merged["SteeringWheelTorque_ST"].dtype == pl.List(pl.Float64)


def test_raw_canonical_name_collision_uses_explicit_raw_namespace_in_both_engines(
    tmp_path: Path,
) -> None:
    normalized_frame = pl.DataFrame({"sample_index": [0, 1], "speed_mps": [10.0, 11.0]})
    raw_columns = {"Speed": [10.0, 11.0], "speed_mps": [999.0, 998.0]}
    mapping = _raw_archive_column_mapping(normalized_frame.columns, raw_columns)

    merged_frame = _merge_raw_columns(normalized_frame, raw_columns)
    merged_rows = _merge_raw_rows(normalized_frame.to_dicts(), pl.DataFrame(raw_columns).to_dicts())

    assert mapping == {"Speed": "Speed", "speed_mps": "raw__speed_mps"}
    assert merged_frame["speed_mps"].to_list() == [10.0, 11.0]
    assert merged_frame["raw__speed_mps"].to_list() == [999.0, 998.0]
    assert [row["speed_mps"] for row in merged_rows] == [10.0, 11.0]
    assert [row["raw__speed_mps"] for row in merged_rows] == [999.0, 998.0]

    definitions = [
        IBTVariableDefinition(name="Speed", unit="m/s", data_type_id=4, offset=0),
        IBTVariableDefinition(name="speed_mps", unit="future", data_type_id=4, offset=4),
    ]
    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=8, record_count=2),
        definitions,
        merged_frame,
        raw_archive_columns=mapping,
    )
    channels = {channel["raw_name"]: channel for channel in manifest["channels"]}
    assert channels["speed_mps"]["archive_column"] == "raw__speed_mps"
    assert channels["speed_mps"]["observed_min"] == 998
    assert manifest["lossless_archive_complete"] is True

    run_id = "raw-canonical-collision"
    write_telemetry_cache(run_id, [], normalized_frame=merged_frame, data_dir=tmp_path)
    write_channel_metadata(run_id, definitions, data_dir=tmp_path)
    write_telemetry_manifest(
        run_id,
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=8, record_count=2),
        definitions,
        merged_frame,
        raw_archive_columns=mapping,
        data_dir=tmp_path,
    )
    catalog = {item["name"]: item for item in build_channel_catalog(run_id, tmp_path)}
    canonical_item = catalog["speed_mps"]
    future_raw_item = catalog["raw__speed_mps"]
    assert canonical_item["is_canonical_alias"] is True
    assert canonical_item["is_calculated"] is False
    assert canonical_item["raw_name"] == "Speed"
    assert canonical_item["min"] == 10.0
    assert canonical_item["max"] == 11.0
    assert future_raw_item["is_raw"] is True
    assert future_raw_item["raw_name"] == "speed_mps"
    assert future_raw_item["archive_column"] == "raw__speed_mps"
    assert future_raw_item["min"] == 998.0
    assert future_raw_item["max"] == 999.0


def test_manifest_reports_schema_health_unknown_channels_and_subtick_rate() -> None:
    header = IBTHeader(version=2, telemetry_rate_hz=60, record_length=32, record_count=2)
    definitions = _definitions()
    frame = pl.DataFrame(
        {
            "Speed": [10.0, 11.0],
            "MysterySignal": [7.0, 7.0],
            "SteeringWheelTorque_ST": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [2.0] * 6],
        }
    )

    manifest = build_telemetry_manifest(header, definitions, frame)
    channels = {channel["raw_name"]: channel for channel in manifest["channels"]}

    assert manifest["declared_channel_count"] == 3
    assert manifest["cached_channel_count"] == 3
    assert manifest["lossless_archive_complete"] is True
    assert len(manifest["schema_fingerprint"]) == 64
    assert channels["MysterySignal"]["registry_status"] == "unmapped"
    assert channels["MysterySignal"]["variation"] == "constant"
    assert channels["SteeringWheelTorque_ST"]["canonical_name"] == "steering_wheel_torque_subtick_nm"
    assert channels["SteeringWheelTorque_ST"]["effective_sample_rate_hz"] == 360
    assert channels["SteeringWheelTorque_ST"]["variation"] == "varying"


def test_schema_fingerprint_changes_when_declaration_changes() -> None:
    header = IBTHeader(version=2, telemetry_rate_hz=60, record_length=32)
    original = _definitions()
    changed = [definition.model_copy(deep=True) for definition in original]
    changed[1].unit = "different-widget"

    assert schema_fingerprint(header, original) != schema_fingerprint(header, changed)


def test_canonical_mapping_kinds_are_explicit_and_fail_safe() -> None:
    assert canonical_mapping_kind("Speed") == "exact_alias"
    assert canonical_mapping_kind("LFshockDefl") == "unit_converted_alias"
    assert canonical_mapping_kind("LFSHshockDefl") == "derived_fallback"
    assert canonical_mapping_kind("speed_mps") == "incompatible_similarly_named_channel"
    assert canonical_mapping_kind("FutureSignal") == "unknown"


def test_legacy_cache_requires_source_reimport_instead_of_lossy_migration(tmp_path: Path) -> None:
    run_id = "legacy-cache"
    write_telemetry_cache(
        run_id,
        [],
        normalized_frame=pl.DataFrame({"speed_mph": [100.0, 101.0]}),
        data_dir=tmp_path,
    )

    payload = build_telemetry_capability_payload(run_id, tmp_path)

    assert payload["cache_compatibility"]["status"] == "reimport_required"
    assert payload["cache_compatibility"]["required_action"] == "reimport_original_ibt"
    assert payload["cache_compatibility"]["automatic_migration_supported"] is False
    assert payload["capability_summary"]["lossless_archive_complete"] is False


def test_newer_archive_requires_app_upgrade() -> None:
    assessment = assess_cache_compatibility(
        {
            "manifest_schema_version": 999,
            "universal_archive_version": 999,
            "lossless_archive_complete": True,
        },
        cache_present=True,
    )

    assert assessment["status"] == "app_upgrade_required"
    assert assessment["required_action"] == "upgrade_racerzlab"


def test_older_manifest_schema_requires_reimport_for_new_provenance_contracts() -> None:
    assessment = assess_cache_compatibility(
        {
            "manifest_schema_version": 2,
            "universal_archive_version": 1,
            "lossless_archive_complete": True,
        },
        cache_present=True,
    )

    assert assessment["status"] == "reimport_required"
    assert assessment["required_action"] == "reimport_original_ibt"


def test_race_context_registry_is_evidence_only_and_preserves_distance_sentinel() -> None:
    expected = {
        "CarDistAhead": "car_distance_ahead_m",
        "CarDistBehind": "car_distance_behind_m",
        "PlayerCarPosition": "player_race_position",
        "PlayerCarClassPosition": "player_class_position",
        "PlayerCarClass": "player_car_class_id",
        "PlayerCarIdx": "player_car_index",
        "PlayerTrackSurface": "player_track_surface",
        "PlayerTrackSurfaceMaterial": "player_track_surface_material",
        "OnPitRoad": "on_pit_road",
        "PlayerCarInPitStall": "player_in_pit_stall",
        "PlayerCarTowTime": "player_tow_service_time_s",
        "PlayerCarMyIncidentCount": "player_incident_count",
        "PaceMode": "pace_mode",
        "PlayerTireCompound": "player_tire_compound",
        "TireSetsUsed": "tire_sets_used",
    }
    assert {name: canonical_name(name) for name in expected} == expected

    definition = IBTVariableDefinition(
        name="CarDistAhead", unit="m", data_type="float", data_type_id=4, offset=0
    )
    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=4, record_count=2),
        [definition],
        pl.DataFrame({"CarDistAhead": [12.5, 1_000_000.0]}),
    )
    channel = manifest["channels"][0]
    assert channel["observed_max"] == 1_000_000
    assert channel["health_status"] == "healthy"
    proximity = next(
        capability
        for capability in manifest["capabilities"]
        if capability["capability_id"] == "nearby_car_context"
    )
    assert proximity["caveat"].startswith("Distance channels provide context only")


def test_catalog_represents_raw_canonical_alias_with_manifest_health_provenance(tmp_path: Path) -> None:
    run_id = "canonical-provenance"
    definition = IBTVariableDefinition(
        name="LFbrakeLinePress",
        description="Left front brake line pressure",
        unit="bar",
        data_type="float",
        data_type_id=4,
        offset=0,
    )
    subtick_definition = IBTVariableDefinition(
        name="SteeringWheelTorque_ST",
        description="High-rate steering torque",
        unit="N*m",
        data_type="float",
        data_type_id=4,
        offset=4,
        count=6,
        count_as_time=True,
    )
    frame = pl.DataFrame(
        {
            "LFbrakeLinePress": [0.0, 12.0],
            "lf_brake_line_pressure_bar": [0.0, 12.0],
            "SteeringWheelTorque_ST": [[1.0] * 6, [2.0] * 6],
            "steering_wheel_torque_subtick_nm": [[1.0] * 6, [2.0] * 6],
        }
    )
    write_telemetry_cache(run_id, [], normalized_frame=frame, data_dir=tmp_path)
    write_channel_metadata(run_id, [definition, subtick_definition], data_dir=tmp_path)
    write_telemetry_manifest(
        run_id,
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=28, record_count=2),
        [definition, subtick_definition],
        frame,
        data_dir=tmp_path,
    )

    catalog = {item["name"]: item for item in build_channel_catalog(run_id, tmp_path)}
    alias = catalog["lf_brake_line_pressure_bar"]
    raw = catalog["LFbrakeLinePress"]

    assert alias["is_canonical_alias"] is True
    assert alias["is_calculated"] is False
    assert alias["source"] == "canonical_alias"
    assert alias["raw_name"] == "LFbrakeLinePress"
    assert alias["provenance"] == "ibt_variable_definition"
    assert alias["health_status"] == "healthy"
    assert alias["health_warnings"] == []
    assert raw["is_raw"] is True
    assert raw["archive_column"] == "LFbrakeLinePress"
    subtick_alias = catalog["steering_wheel_torque_subtick_nm"]
    assert subtick_alias["is_canonical_alias"] is True
    assert subtick_alias["is_calculated"] is False
    assert subtick_alias["count"] == 6
    assert subtick_alias["count_as_time"] is True
    assert subtick_alias["effective_sample_rate_hz"] == 360
    summary_alias = {
        item["name"]: item for item in build_channel_summary(run_id, tmp_path)
    }["lf_brake_line_pressure_bar"]
    assert summary_alias["is_canonical_alias"] is True
    assert summary_alias["is_calculated"] is False
    assert summary_alias["source"] == "canonical_alias"
    assert summary_alias["health_status"] == "healthy"
    assert ChannelCatalogItem(**alias).model_dump()["is_canonical_alias"] is True
    assert ChannelSummaryItem(**summary_alias).model_dump()["provenance"] == "ibt_variable_definition"


def test_real_atlanta_archive_health_has_no_false_faults(tmp_path: Path) -> None:
    fixture = Path(
        "data/imports/ibt/stockcars chevycamarozl12022_atlanta 2022 oval "
        "2026-02-17 14-41-23.ibt"
    )
    if not fixture.exists():
        pytest.skip("Local Atlanta .ibt fixture is unavailable")

    result, _cache = ImportService(
        db_path=tmp_path / "racelab.sqlite",
        data_dir=tmp_path / "data",
    ).import_ibt_file(fixture)
    assert result.overview is not None
    frame = result.get_normalized_frame()
    assert frame is not None
    assert frame.height == 26_556
    assert frame.width >= 539
    assert not any(column.startswith("raw__") for column in frame.columns)
    assert {
        "player_race_position",
        "player_class_position",
        "player_car_index",
        "player_track_surface_material",
        "player_in_pit_stall",
        "player_tow_service_time_s",
        "player_incident_count",
        "pace_mode",
        "player_tire_compound",
        "tire_sets_used",
        "precipitation",
        "track_wetness",
    }.issubset(frame.columns)
    manifest = read_telemetry_manifest(result.overview.run_id, tmp_path / "data")

    assert manifest["declared_channel_count"] == 277
    assert manifest["cached_channel_count"] == 277
    assert manifest["complete_channel_count"] == 277
    assert manifest["lossless_archive_complete"] is True
    assert manifest["health_summary"] == {
        "status": "healthy",
        "warning_channel_count": 0,
        "non_finite_sample_count": 0,
        "impossible_sample_count": 0,
        "malformed_array_record_count": 0,
    }
    assert manifest["sample_continuity"]["estimated_dropped_tick_count"] == 0
    assert manifest["sample_continuity"]["timestamp_gap_count"] == 1
    advertised_aliases = {
        channel["canonical_name"]
        for channel in manifest["channels"]
        if channel["canonical_name"] is not None
    }
    assert advertised_aliases.issubset(frame.columns)
    shock_channel = next(
        channel for channel in manifest["channels"] if channel["raw_name"] == "LFshockDefl"
    )
    assert shock_channel["canonical_name"] == "lf_shock_defl_in"
    assert shock_channel["canonical_mapping_kind"] == "unit_converted_alias"
    saturation = {
        channel["raw_name"]: channel["saturation_status"]
        for channel in manifest["channels"]
        if channel["saturation_status"] != "none_detected"
    }
    assert saturation == {
        "Throttle": "normal_control_boundary_occupancy",
        "Brake": "normal_control_boundary_occupancy",
        "Clutch": "normal_control_boundary_occupancy",
    }


def test_manifest_records_compatibility_identity_from_current_session() -> None:
    session_yaml = """
WeekendInfo:
  TrackID: 447
  TrackName: atlanta 2022 oval
  TrackConfigName: Oval
  TrackVersion: 2025.12.29.01
  BuildVersion: 2026.02.02.02
  BuildType: Release
DriverInfo:
  DriverCarIdx: 0
  DriverCarVersion: 2026.01.30.02
  Drivers:
    - CarIdx: 0
      UserID: 424242
      TeamID: 777
      CarID: 139
      CarPath: stockcars chevycamarozl12022
      CarScreenName: NASCAR Chevrolet Camaro ZL1
      CarCfg: 2
      CarCfgName: Superspeedway
SessionInfo:
  CurrentSessionNum: 1
  Sessions:
    - SessionNum: 0
      SessionType: Practice
    - SessionNum: 1
      SessionType: Race
      SessionName: RACE
"""
    identity = compatibility_identity(session_yaml)
    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=32, record_count=2),
        _definitions(),
        pl.DataFrame(
            {
                "Speed": [10.0, 11.0],
                "MysterySignal": [1.0, 2.0],
                "SteeringWheelTorque_ST": [[1.0] * 6, [2.0] * 6],
            }
        ),
        session_yaml,
    )

    assert identity["car_id"] == 139
    assert identity["car_version"] == "2026.01.30.02"
    assert identity["driver_user_id"] == 424242
    assert identity["team_id"] == 777
    assert identity["track_configuration_name"] == "Oval"
    assert identity["track_version"] == "2025.12.29.01"
    assert identity["iracing_build_version"] == "2026.02.02.02"
    assert identity["session_type"] == "Race"
    assert identity["missing_required_fields"] == []
    assert len(manifest["compatibility_fingerprint"]) == 64

    other_driver = dict(identity, driver_user_id=999999, team_id=888)
    assert manifest["compatibility_fingerprint"] == compatibility_fingerprint(
        manifest["schema_fingerprint"], other_driver
    )


def test_manifest_detects_non_finite_impossible_saturated_gapped_and_malformed_samples() -> None:
    definitions = [
        IBTVariableDefinition(name="SessionTick", data_type_id=2, offset=0),
        IBTVariableDefinition(name="SessionTime", unit="s", data_type_id=5, offset=4),
        IBTVariableDefinition(name="Throttle", unit="%", data_type_id=4, offset=12),
        IBTVariableDefinition(name="Speed", unit="m/s", data_type_id=4, offset=16),
        IBTVariableDefinition(name="ArrayFuture", data_type_id=4, offset=20, count=3),
    ]
    frame = pl.DataFrame(
        {
            "SessionTick": [10, 11, 14, 14],
            "SessionTime": [0.0, 1 / 60, 4 / 60, 4 / 60],
            "Throttle": [0.0, 1.0, 1.0, 1.2],
            "Speed": [10.0, math.nan, math.inf, -2.0],
            "ArrayFuture": [[1.0, 2.0, 3.0], [4.0, 5.0], [6.0, 7.0, 8.0], [9.0, 10.0, 11.0]],
        },
        strict=False,
    )
    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=40, record_count=4),
        definitions,
        frame,
    )
    channels = {channel["raw_name"]: channel for channel in manifest["channels"]}

    assert channels["Speed"]["non_finite_sample_count"] == 2
    assert channels["Speed"]["impossible_sample_count"] == 1
    assert channels["Throttle"]["impossible_sample_count"] == 1
    assert channels["Throttle"]["saturation_status"] == "normal_control_boundary_occupancy"
    assert channels["ArrayFuture"]["malformed_array_record_count"] == 1
    assert manifest["health_summary"]["status"] == "warning"
    assert manifest["sample_continuity"]["estimated_dropped_tick_count"] == 2
    assert manifest["sample_continuity"]["duplicate_tick_transition_count"] == 1
    assert manifest["sample_continuity"]["timestamp_gap_count"] == 1
    assert manifest["sample_continuity"]["non_monotonic_timestamp_transition_count"] == 1


def test_manifest_numeric_health_keeps_null_and_non_finite_counts_distinct() -> None:
    definition = IBTVariableDefinition(name="Speed", unit="m/s", data_type_id=4, offset=0)
    frame = pl.DataFrame({
        "Speed": [None, math.nan, math.inf, -math.inf, -2.0, 10.0],
    })

    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=4, record_count=6),
        [definition],
        frame,
    )
    health = manifest["channels"][0]

    assert health["record_count"] == 6
    assert health["valid_record_count"] == 5
    assert health["missing_fraction"] == pytest.approx(1 / 6)
    assert health["non_finite_sample_count"] == 3
    assert health["impossible_sample_count"] == 1


def test_archive_invariant_rejects_missing_unknown_future_channel(tmp_path: Path) -> None:
    cache = write_telemetry_cache(
        "future-channel",
        [],
        normalized_frame=pl.DataFrame({"Speed": [1.0, 2.0]}),
        data_dir=tmp_path,
    )

    with pytest.raises(RuntimeError, match="UnknownFutureChannel"):
        _assert_declared_channels_archived(cache, ["Speed", "UnknownFutureChannel"])


def test_archive_invariant_and_manifest_reject_incomplete_record_count(tmp_path: Path) -> None:
    definition = IBTVariableDefinition(name="FutureSignal", data_type_id=4, offset=0)
    frame = pl.DataFrame({"FutureSignal": [1.0]})
    cache = write_telemetry_cache(
        "short-archive",
        [],
        normalized_frame=frame,
        data_dir=tmp_path,
    )

    with pytest.raises(RuntimeError, match="expected 2 records"):
        _assert_declared_channels_archived(
            cache,
            {"FutureSignal": "FutureSignal"},
            expected_record_count=2,
        )

    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=4, record_count=2),
        [definition],
        frame,
    )
    assert manifest["cached_channel_count"] == 1
    assert manifest["complete_channel_count"] == 0
    assert manifest["lossless_archive_complete"] is False


def test_archive_invariant_and_manifest_reject_null_primitive_samples(tmp_path: Path) -> None:
    definition = IBTVariableDefinition(name="FutureSignal", data_type_id=4, offset=0)
    frame = pl.DataFrame({"FutureSignal": [None, None]})
    cache = write_telemetry_cache(
        "null-archive",
        [],
        normalized_frame=frame,
        data_dir=tmp_path,
    )

    with pytest.raises(RuntimeError, match="FutureSignal.*2"):
        _assert_declared_channels_archived(
            cache,
            {"FutureSignal": "FutureSignal"},
            expected_record_count=2,
        )

    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=4, record_count=2),
        [definition],
        frame,
    )
    assert manifest["channels"][0]["health_status"] == "warning"
    assert manifest["channels"][0]["valid_record_count"] == 0
    assert manifest["complete_channel_count"] == 0
    assert manifest["lossless_archive_complete"] is False


def test_columnar_decoder_preserves_mixed_scalar_array_string_and_bitfield() -> None:
    header = IBTHeader(record_length=24, data_offset=0, record_count=1)
    definitions = [
        IBTVariableDefinition(name="Label", data_type_id=0, offset=0, count=8),
        IBTVariableDefinition(name="Scalar", data_type_id=4, offset=8),
        IBTVariableDefinition(name="Flags", data_type_id=3, offset=12),
        IBTVariableDefinition(name="Array", data_type_id=2, offset=16, count=2),
    ]
    data = bytearray(24)
    data[0:8] = b"future\0\0"
    struct.pack_into("<f", data, 8, 12.5)
    struct.pack_into("<I", data, 12, 0b10101)
    struct.pack_into("<2i", data, 16, 7, 9)

    columns = _read_records_columnar(bytes(data), header, definitions)

    assert columns["Label"] == ["future"]
    assert columns["Scalar"] == [12.5]
    assert columns["Flags"] == [0b10101]
    assert columns["Array"] == [[7, 9]]


def test_vectorized_list_of_rows_preserves_subtick_array_shape() -> None:
    frame = normalize_telemetry_frame(
        [
            {"SessionTime": 0.0, "SteeringWheelTorque_ST": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]},
            {"SessionTime": 1 / 60, "SteeringWheelTorque_ST": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]},
        ]
    )

    assert frame["steering_wheel_torque_subtick_nm"].dtype == pl.List(pl.Float64)
    assert frame["steering_wheel_torque_subtick_nm"].to_list()[0] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


@pytest.mark.parametrize(
    "definition, message",
    [
        (IBTVariableDefinition(name="BadCount", data_type_id=4, offset=0, count=0), "invalid element count"),
        (IBTVariableDefinition(name="PastRecord", data_type_id=5, offset=12, count=1), "exceeds"),
        (IBTVariableDefinition(name="BadType", data_type_id=99, offset=0), "Unsupported"),
    ],
)
def test_malformed_variable_definitions_are_rejected(
    definition: IBTVariableDefinition,
    message: str,
) -> None:
    with pytest.raises(IBTParseError, match=message):
        _validate_variable_definitions(IBTHeader(record_length=16), [definition])


def test_duplicate_variable_names_are_rejected() -> None:
    definition = IBTVariableDefinition(name="FutureSignal", data_type_id=4, offset=0)
    with pytest.raises(IBTParseError, match="Duplicate"):
        _validate_variable_definitions(
            IBTHeader(record_length=8),
            [definition, definition.model_copy(update={"offset": 4})],
        )
