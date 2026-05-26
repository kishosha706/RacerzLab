from __future__ import annotations

from pathlib import Path

from racelab_engine.io.ibt_reader import read_session_yaml
from racelab_engine.io.session_yaml import extract_session_summary, extract_setup_snapshot


def test_real_session_yaml_extracts_summary_and_setup(talladega_ibt_path: Path) -> None:
    yaml_text = read_session_yaml(talladega_ibt_path)
    session = extract_session_summary(yaml_text, run_id="real-run")
    setup = extract_setup_snapshot(yaml_text, run_id="real-run")

    assert "WeekendInfo:" in yaml_text
    assert "CarSetup:" in yaml_text
    assert session.car_name == "Chevrolet Camaro ZL1 Class A"
    assert session.track_display_name == "Talladega Super Speedway"
    assert session.setup_name == "talladega.sto"
    assert session.weather_summary == "Clear"
    assert setup.setup_name == "talladega.sto"
    assert setup.tape_percent == 10
    assert setup.rear_end_ratio == 3.45
    assert setup.lf_ride_height_mm == 66
    assert setup.rf_ride_height_mm == 77
    assert setup.lr_ride_height_mm == 127
    assert setup.rr_ride_height_mm == 137
    assert setup.steering_ratio == "10:1"
