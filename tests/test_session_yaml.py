from __future__ import annotations

from racelab_engine.io.session_yaml import extract_session_summary, extract_setup_snapshot


def test_session_yaml_extracts_session_and_setup_values() -> None:
    yaml_text = """
WeekendInfo:
  TrackName: talladega
  TrackDisplayName: Talladega Super Speedway
  WeekendStartTime: 2026-05-07 17:48:51
DriverInfo:
  DriverCarName: Chevrolet Camaro ZL1 Class A
  DriverCarPath: stockcars/camarozl12018
SessionInfo:
  SessionType: Test
WeatherInfo:
  Skies: Clear
  AirTemp: 78 F
  TrackTemp: 102 F
CarSetup:
  SetupName: talladega.sto
  Tape: 10%
  Rear end ratio: 3.45
  LF ride height: 66 mm
  RF ride height: 77 mm
  LR ride height: 127 mm
  RR ride height: 137 mm
  LF front spring: 1750 N/mm
  RF front spring: 1750 N/mm
  LR rear spring: 140 N/mm
  RR rear spring: 52 N/mm
  Nose weight: 53.4%
  Cross weight: 47.9%
  Front brake bias: 65.0%
  Steering ratio: "10:1"
  Steering offset: +10 deg
"""

    session = extract_session_summary(yaml_text, run_id="run-yaml")
    setup = extract_setup_snapshot(yaml_text, run_id="run-yaml")

    assert session.track_display_name == "Talladega Super Speedway"
    assert session.car_name == "Chevrolet Camaro ZL1 Class A"
    assert session.session_type == "Test"
    assert session.air_temp == 78
    assert setup.setup_name == "talladega.sto"
    assert setup.tape_percent == 10
    assert setup.rear_end_ratio == 3.45
    assert setup.lf_ride_height_mm == 66
    assert setup.rr_ride_height_mm == 137
    assert setup.steering_ratio == "10:1"
    assert setup.steering_offset_deg == 10


def test_next_gen_rear_ratio_and_steering_pinion_aliases() -> None:
    setup = extract_setup_snapshot(
        """
CarSetup:
  Chassis:
    Front:
      SteeringPinion: 60 mm/rev
    Rear:
      FinalDriveRatio: 3.684
""",
        run_id="next-gen",
    )

    assert setup.rear_end_ratio == 3.684
    assert setup.steering_ratio == "60 mm/rev"


def test_discrete_tape_configuration_is_not_discarded_as_non_numeric() -> None:
    setup = extract_setup_snapshot(
        """
CarSetup:
  Chassis:
    Front:
      TapeConfiguration: Qual
""",
        run_id="late-model",
    )

    assert setup.tape_percent == "Qual"


def test_session_summary_uses_current_session_number_not_first_session() -> None:
    session = extract_session_summary(
        """
WeekendInfo:
  EventType: Race
SessionInfo:
  CurrentSessionNum: 2
  Sessions:
    - SessionNum: 0
      SessionType: Practice
    - SessionNum: 1
      SessionType: Lone Qualify
    - SessionNum: 2
      SessionType: Race
      SessionLaps: 50
""",
        run_id="current-race",
    )

    assert session.session_type == "Race"


def test_next_gen_arb_and_diff_fields_use_real_paths_and_discrete_arm_types() -> None:
    setup = extract_setup_snapshot(
        """
CarSetup:
  Chassis:
    FrontArb:
      Diameter: 51 mm
      ArbArm: P5 (stiff)
      Preload: -65.1 Nm
      Attach: 1
    Rear:
      Diameter: 51 mm
      ArbArm: P3
      ArbPreload: 0.0 Nm
      Attach: 1
      DiffPreload: 34 Nm
""",
        run_id="next-gen-arb",
    )

    values = setup.extracted_values
    assert values["front_arb_diameter_mm"] == 51.0
    assert values["front_arb_arm_position"] == "P5"
    assert values["front_arb_preload_nm"] == -65.1
    assert values["front_arb_attach"] == 1.0
    assert values["rear_arb_diameter_mm"] == 51.0
    assert values["rear_arb_arm_position"] == "P3"
    assert values["rear_arb_preload_nm"] == 0.0
    assert values["rear_arb_attach"] == 1.0
    assert values["diff_preload_nm"] == 34.0
