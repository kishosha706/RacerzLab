from __future__ import annotations

from pathlib import Path

from racelab_engine.io.ibt_reader import read_variable_definitions


def test_real_ibt_variable_definitions(talladega_ibt_path: Path) -> None:
    variables = read_variable_definitions(talladega_ibt_path)
    by_name = {variable.name: variable for variable in variables}

    assert len(variables) == 275
    assert by_name["SessionTime"].data_type == "double"
    assert by_name["SessionTime"].offset == 0
    assert by_name["Speed"].unit == "m/s"
    assert by_name["Speed"].data_type == "float"
    assert by_name["CFSRrideHeight"].unit == "m"
    assert by_name["CFSRrideHeight"].offset == 1070
