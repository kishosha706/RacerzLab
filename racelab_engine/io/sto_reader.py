from __future__ import annotations

from pathlib import Path


def read_sto(path: str | Path) -> None:
    """Placeholder for iRacing `.sto` setup decoding.

    MVP 1 extracts setup information only from session YAML when provided.
    """

    Path(path).stat()
    raise NotImplementedError("STO decoding is not implemented in MVP 1.")
