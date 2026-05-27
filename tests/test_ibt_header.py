from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.io.file_fingerprint import fingerprint_file
from racelab_engine.io.ibt_reader import IBTParseError, import_ibt, read_header

pytestmark = pytest.mark.slow


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
