from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.setup import SetupSnapshot


@dataclass(frozen=True)
class IntelligenceSnapshotIdentity:
    reasoning_snapshot_sha256: str
    setup_id: str | None
    setup_snapshot_sha256: str | None


def intelligence_snapshot_identity(
    reasoning_snapshot: Any,
    *,
    run_id: str,
    setup_snapshot: SetupSnapshot | None,
) -> IntelligenceSnapshotIdentity:
    """Return the exact public P19 snapshot identity used by the P26 projection."""
    if setup_snapshot is not None and setup_snapshot.run_id != run_id:
        raise ValueError("Intelligence setup snapshot does not match the reasoning run.")
    return IntelligenceSnapshotIdentity(
        reasoning_snapshot_sha256=canonical_json_sha256(reasoning_snapshot),
        setup_id=setup_snapshot.setup_id if setup_snapshot is not None else None,
        setup_snapshot_sha256=(
            canonical_json_sha256(setup_snapshot) if setup_snapshot is not None else None
        ),
    )


__all__ = ["IntelligenceSnapshotIdentity", "intelligence_snapshot_identity"]
