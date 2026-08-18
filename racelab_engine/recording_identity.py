"""Canonical physical-recording identity and independence guards.

One original ``.ibt`` byte stream is one physical observation.  Filenames,
session membership, and legacy run aliases are presentation/membership facts;
they must never manufacture another independent telemetry source.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECORDING_RUN_ID_PREFIX = "recording-"
SAME_RECORDING_MESSAGE = (
    "SAME RECORDING: These entries reference identical telemetry and cannot be "
    "compared or counted as independent runs."
)


class RecordingIdentityError(ValueError):
    """Raised when physical recording identity cannot be trusted."""


class SameRecordingError(RecordingIdentityError):
    """Raised when two named evidence units resolve to the same source bytes."""


def normalize_source_sha256(value: object) -> str | None:
    """Return one normalized full SHA-256, never a prefix or filename token."""

    text = str(value or "").strip().lower()
    return text if _SHA256_RE.fullmatch(text) else None


def canonical_recording_run_id(source_sha256: object) -> str:
    """Return the stable run/artifact owner ID for one physical recording."""

    normalized = normalize_source_sha256(source_sha256)
    if normalized is None:
        raise RecordingIdentityError(
            "A full source-file SHA-256 is required for recording identity."
        )
    return f"{RECORDING_RUN_ID_PREFIX}{normalized}"


def resolve_recording_sha256(
    *,
    run_id: str,
    stored_source_sha256: object = None,
    manifest_source_sha256: object = None,
) -> str:
    """Resolve one run to its physical source and reject conflicting owners.

    The normalized run row and immutable telemetry manifest are independent
    persistence paths.  Either can upgrade a legacy record, but if both are
    present they must agree exactly.
    """

    stored = normalize_source_sha256(stored_source_sha256)
    manifested = normalize_source_sha256(manifest_source_sha256)
    if stored is not None and manifested is not None and stored != manifested:
        raise RecordingIdentityError(
            f"Recording identity mismatch for run {run_id}: stored source and "
            "telemetry manifest disagree. Re-import this recording."
        )
    resolved = stored or manifested
    if resolved is None:
        raise RecordingIdentityError(
            f"Recording identity is unavailable for run {run_id}. Re-import the "
            "original .ibt before using it as independent evidence."
        )
    return resolved


def require_independent_recordings(
    source_sha256_by_run: Mapping[str, object],
    *,
    ordered_run_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Return ordered full source identities or fail closed on an alias.

    This reusable boundary deliberately reasons in full source hashes rather
    than run IDs.  It is suitable for Compare, controlled A/B/A2 stages, and
    any later recurrence/admission counter.
    """

    run_ids = tuple(ordered_run_ids or source_sha256_by_run.keys())
    if not run_ids:
        raise RecordingIdentityError("At least one recording identity is required.")
    normalized: list[str] = []
    owner_by_sha: dict[str, str] = {}
    for run_id in run_ids:
        source_sha = normalize_source_sha256(source_sha256_by_run.get(run_id))
        if source_sha is None:
            raise RecordingIdentityError(
                f"Recording identity is unavailable for run {run_id}. Re-import the "
                "original .ibt before using it as independent evidence."
            )
        previous_owner = owner_by_sha.get(source_sha)
        if previous_owner is not None:
            raise SameRecordingError(
                f"{SAME_RECORDING_MESSAGE} Runs {previous_owner} and {run_id} share "
                f"source SHA-256 {source_sha}."
            )
        owner_by_sha[source_sha] = run_id
        normalized.append(source_sha)
    return tuple(normalized)


__all__ = [
    "RECORDING_RUN_ID_PREFIX",
    "SAME_RECORDING_MESSAGE",
    "RecordingIdentityError",
    "SameRecordingError",
    "canonical_recording_run_id",
    "normalize_source_sha256",
    "require_independent_recordings",
    "resolve_recording_sha256",
]
