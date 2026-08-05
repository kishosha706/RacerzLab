"""Neutral evidence vocabulary shared by models, analysis, API, and UI contracts."""

from __future__ import annotations

from enum import Enum


class EvidenceState(str, Enum):
    MEASURED = "measured"
    CALCULATED = "calculated"
    ESTIMATED_PROXY = "estimated_proxy"
    OBSERVED_CORRELATION = "observed_correlation"
    CONTROLLED_TEST_EFFECT = "controlled_test_effect"
    UNAVAILABLE = "unavailable"
    BLOCKED_BY_CONTEXT = "blocked_by_context"
    NEEDS_CONFIRMATION = "needs_confirmation"


__all__ = ["EvidenceState"]
