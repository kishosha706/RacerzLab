"""Typed bridge from qualified handling signatures to canonical Dial-In symptoms.

This module is a source-aware resolver for one path of the required chain:

    qualified handling observation -> canonical symptom -> Dial-In knowledge

It loads the SAME symptom vocabulary that Dial-In uses (79 entries at review
time). It never fabricates driver wording, never submits a complaint string,
and never changes DriverIntent. A mapping that is not backed by the loaded
vocabulary returns ``None`` with an explicit blocker instead of guessing.
"""

from __future__ import annotations

from functools import lru_cache

from racelab_engine.models.handling_balance import HandlingClassification

from .loader import load_setup_knowledge

# Canonical phase families used by the vocabulary's phase field.
_PHASE_FAMILY = {
    "turn_in": "entry",
    "entry": "entry",
    "brake_release": "entry",
    "apex_region": "center",
    "center": "center",
    "initial_throttle": "exit",
    "full_throttle_exit": "exit",
    "following_straight_carry": "exit",
}

_BALANCE_TOKEN = {
    HandlingClassification.ROTATION_RESPONSE_DEFICIT: "tight",
    HandlingClassification.ROTATION_RESPONSE_EXCESS: "loose",
}


@lru_cache(maxsize=1)
def _canonical_symptoms() -> frozenset[str]:
    knowledge = load_setup_knowledge()
    return frozenset({
        entry.canonical_symptom
        for entry in knowledge.symptom_vocabulary
        if getattr(entry, "canonical_symptom", None)
    })


def phase_family(phase: str | None) -> str | None:
    """Map a canonical engineering phase to the vocabulary's phase family."""
    if phase is None:
        return None
    return _PHASE_FAMILY.get(phase, phase)


def resolve_canonical_symptom(
    classification: HandlingClassification,
    phase: str | None,
) -> tuple[str | None, str | None]:
    """Resolve one canonical symptom ID for a qualified signature.

    Returns (canonical_symptom_id, blocker_reason). Exactly one of the two is
    meaningful. The mapping is deterministic and vocabulary-bound; it cannot
    produce a symptom the Dial-In vocabulary does not define.
    """
    balance = _BALANCE_TOKEN.get(classification)
    family = phase_family(phase)
    if balance is None or family is None:
        return None, (
            "Canonical symptom mapping requires a qualified deficit or excess "
            "signature in a known corner-phase family."
        )
    candidate = f"{balance}_{family}"
    if candidate not in _canonical_symptoms():
        return None, (
            f"Signature {classification.value} in phase {phase} has no reviewed "
            "canonical symptom in the loaded vocabulary."
        )
    return candidate, None


__all__ = ["phase_family", "resolve_canonical_symptom"]
