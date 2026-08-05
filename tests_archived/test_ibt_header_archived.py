# Archived: test_real_ibt_header (duplicate — covered by test_real_telemetry_normalization)
# Kept:   test_file_fingerprint_and_invalid_ibt_error

import pytest
from pathlib import Path
from racelab_engine.io.ibt_reader import import_ibt

pytestmark = pytest.mark.slow

def test_real_ibt_header(talladega_ibt_path: Path) -> None:
    result = import_ibt(talladega_ibt_path)
    assert result.header is not None
    assert result.header.buf_len > 0
    assert result.header.num_vars > 0
    assert result.header.status == 1
