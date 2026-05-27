# Archived: setup_diff + context_diff tests (covered by compare API endpoint)
# Kept: lap_grid, interpolation, speed_delta, discipline, verdict tests
import pytest
from racelab_engine.analysis.setup_diff import diff_setups, diff_context
from racelab_engine.analysis.test_discipline import score_test_discipline, TestDisciplineResult

pytestmark = pytest.mark.slow

def test_setup_diff_detects_changes():
    old = {"lf_ride_height_mm": 66, "rear_end_ratio": 3.45}
    new = {"lf_ride_height_mm": 64, "rear_end_ratio": 3.45}
    changes = diff_setups(old, new)
    assert any(c.setup_key == "lf_ride_height_mm" for c in changes)

def test_setup_diff_no_changes():
    setup = {"lf_ride_height_mm": 66}
    changes = diff_setups(setup, setup)
    assert len(changes) == 0

def test_setup_diff_none_setups():
    changes = diff_setups(None, None)
    assert changes == []

def test_context_diff_detects_weather():
    old = {"air_temp": 20.0, "track_temp": 30.0}
    new = {"air_temp": 18.0, "track_temp": 32.0}
    changes = diff_context(old, new)
    assert any(c.key == "air_temp" for c in changes)
