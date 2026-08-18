from __future__ import annotations

from pathlib import Path

import polars as pl

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.channel_registry import canonical_name
from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame
from racelab_engine.io.ibt_types import IBTHeader, IBTVariableDefinition
from racelab_engine.io.telemetry_manifest import (
    _CHANNEL_ENGINEERING_ROLES,
    build_telemetry_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def test_reviewed_next_gen_unmapped_inventory_has_one_explicit_role_each() -> None:
    reviewed = {
        raw_name: role
        for role, raw_names in _CHANNEL_ENGINEERING_ROLES.items()
        for raw_name in raw_names
    }
    assert len(reviewed) == 62
    definitions = [
        IBTVariableDefinition(
            name=name,
            description=f"Reviewed {name}",
            unit="state",
            data_type="int",
            data_type_id=2,
            offset=index * 4,
        )
        for index, name in enumerate(reviewed)
    ]
    frame = pl.DataFrame({name: [0, 1] for name in reviewed})
    manifest = build_telemetry_manifest(
        IBTHeader(
            telemetry_rate_hz=60,
            record_count=2,
            variable_count=len(definitions),
            record_length=len(definitions) * 4,
        ),
        definitions,
        frame,
    )
    channels = {item["raw_name"]: item for item in manifest["channels"]}

    assert set(channels) == set(reviewed)
    for raw_name, role in reviewed.items():
        assert channels[raw_name]["engineering_role"] == role
        assert channels[raw_name]["engineering_admission_state"] != "admitted"
        assert channels[raw_name]["engineering_authority_limit"]


def test_unknown_future_channel_is_archived_without_runtime_authority() -> None:
    definition = IBTVariableDefinition(
        name="FutureUnreviewedSignal",
        description="Future value",
        unit="future",
        data_type="float",
        data_type_id=4,
    )
    manifest = build_telemetry_manifest(
        IBTHeader(telemetry_rate_hz=60, record_count=2, variable_count=1),
        [definition],
        pl.DataFrame({"FutureUnreviewedSignal": [1.0, 2.0]}),
    )
    channel = manifest["channels"][0]

    assert channel["engineering_role"] == "inventory_debug"
    assert channel["engineering_admission_state"] == "archived_only"
    assert canonical_name("FutureUnreviewedSignal") is None


def test_per_corner_tire_inventory_is_pit_snapshot_only_with_row_frame_parity() -> None:
    raw = [{
        "LFTiresUsed": 1,
        "RFTiresUsed": 2,
        "LRTiresUsed": 3,
        "RRTiresUsed": 4,
        "LFTiresAvailable": 5,
        "RFTiresAvailable": 6,
        "LRTiresAvailable": 7,
        "RRTiresAvailable": 8,
    }]
    row = normalize_telemetry_rows(raw)[0]
    frame = normalize_telemetry_frame(pl.DataFrame(raw)).to_dicts()[0]

    for corner, expected_used, expected_available in (
        ("lf", 1, 5),
        ("rf", 2, 6),
        ("lr", 3, 7),
        ("rr", 4, 8),
    ):
        assert canonical_name(f"{corner.upper()}TiresUsed") == f"{corner}_tires_used"
        assert row[f"{corner}_tires_used"] == expected_used
        assert frame[f"{corner}_tires_used"] == expected_used
        assert row[f"{corner}_tires_available"] == expected_available
        assert frame[f"{corner}_tires_available"] == expected_available

    definition = IBTVariableDefinition(
        name="LFTiresUsed",
        description="Left-front tires used",
        unit="count",
        data_type="int",
        data_type_id=2,
    )
    manifest = build_telemetry_manifest(
        IBTHeader(telemetry_rate_hz=60, record_count=2, variable_count=1),
        [definition],
        pl.DataFrame({"LFTiresUsed": [1, 1]}),
    )
    channel = manifest["channels"][0]
    assert channel["engineering_role"] == "pit_snapshot"
    assert channel["engineering_admission_state"] == "pit_boundary_only"
    assert "never continuous on-track evidence" in channel["engineering_authority_limit"]


def test_learning_mode_capability_inventory_and_custom_lane_are_reachable() -> None:
    app = (ROOT / "ui/src/App.tsx").read_text(encoding="utf-8")
    inspector = (ROOT / "ui/src/components/EvidenceInspector.tsx").read_text(
        encoding="utf-8"
    )
    catalog = (ROOT / "ui/src/tabs/RawChannelsTab.tsx").read_text(encoding="utf-8")
    platform = (ROOT / "ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")

    assert 'loadRawChannelsTab = () => import("./tabs/RawChannelsTab")' in app
    assert 'selection.selectedMode === "learning"' in app.split(
        'if (ws === "channels")', 1
    )[1].split('if (ws === "laps")', 1)[0]
    assert "Telemetry Capabilities" in inspector
    for role in (
        "admitted_analysis",
        "measurement_candidate",
        "corroboration",
        "pit_snapshot",
        "control_state",
        "integrity",
        "inventory_debug",
    ):
        assert f'<option value="{role}">' in catalog
    assert "engineering_authority_limit" in catalog
    assert "observation-only" in catalog
    assert "selection.selectedChannel" in platform
    assert "selectedCatalogChannel?.is_proxy" in platform
