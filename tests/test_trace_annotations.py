from __future__ import annotations

from racelab_engine.analysis.trace_annotations import annotate_delta_traces


def test_positive_only_traces_do_not_emit_fake_negative_events() -> None:
    result = annotate_delta_traces(
        {
            "speed_mph": {"delta_values": [0.10, 0.20, 0.30]},
            "cfs_ride_height_in": {"delta_values": [0.01, 0.02, 0.03]},
            "rpm": {"delta_values": [100.0, 150.0, 200.0]},
            "throttle_pct": {"delta_values": [2.0, 3.0, 4.0]},
        },
        [0.0, 50.0, 100.0],
        [0.0, 500.0, 1_000.0],
    )

    kinds = {annotation.kind for annotation in result.annotations}
    assert "SPEED_GAIN" in kinds
    assert "SPEED_LOSS" not in kinds
    assert "CFS_COMPRESSION" not in kinds
    assert "RPM_FLATTENING" not in kinds
    assert "THROTTLE_LIFT" not in kinds


def test_negative_events_require_crossing_their_negative_threshold() -> None:
    result = annotate_delta_traces(
        {
            "speed_mph": {"delta_values": [-0.01, -0.06]},
            "cfs_ride_height_in": {"delta_values": [-0.0005, -0.002]},
            "rpm": {"delta_values": [-20.0, -80.0]},
            "throttle_pct": {"delta_values": [-1.0, -3.0]},
        },
        [0.0, 100.0],
        [0.0, 1_000.0],
    )

    assert {annotation.kind for annotation in result.annotations} == {
        "SPEED_LOSS",
        "CFS_COMPRESSION",
        "RPM_FLATTENING",
        "THROTTLE_LIFT",
    }
