"""Canonical content identities shared by evidence and authority contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


CANONICAL_JSON_SHA256_VERSION = "sha256-json-c14n-v1"


def canonical_json_sha256(value: Any) -> str:
    """Hash one JSON-like value with the repository's canonical serialization."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif hasattr(value, "__dict__"):
        value = vars(value)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["CANONICAL_JSON_SHA256_VERSION", "canonical_json_sha256"]
