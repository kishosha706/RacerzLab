from __future__ import annotations

from pathlib import Path


def read_mt2(path: str | Path) -> None:
    """Placeholder for MoTeC `.mt2` track map decoding.

    MVP 1 does not claim `.mt2` support. Future work should validate the
    `MoTeCTrackV2` marker, decode point records, and return a typed track map.
    """

    Path(path).stat()
    raise NotImplementedError("MT2 decoding is not implemented in MVP 1.")
