from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.io.file_fingerprint import fingerprint_file
from racelab_engine.io.ibt_reader import IBTParseError, import_ibt, read_header


def test_file_fingerprint_and_invalid_ibt_error(tmp_path: Path) -> None:
    ibt_file = tmp_path / "sample.ibt"
    ibt_file.write_bytes(b"not a real ibt")

    fingerprint = fingerprint_file(ibt_file)
    result = import_ibt(ibt_file)

    assert fingerprint.file_size == len(b"not a real ibt")
    assert len(fingerprint.sha256) == 64
    assert result.fingerprint is not None
    assert result.status.status == "error"

    with pytest.raises(IBTParseError):
        read_header(ibt_file)


def test_real_ibt_header(talladega_ibt_path: Path) -> None:
    header = read_header(talladega_ibt_path)

    assert header.version == 2
    assert header.telemetry_rate_hz == 60
    assert header.record_count == 6277
    assert header.variable_count == 275
    assert header.record_length == 1074
    assert header.duration_seconds == pytest.approx(104.6, abs=0.5)
