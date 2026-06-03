"""Deterministic setup knowledge for local RacerZLab guidance."""

from .dial_in_schema import Clarification, DialInResponse, DialInSwing, HiddenEvidenceSummary
from .dial_in_service import build_dial_in_response
from .evidence_adapter import (
    RunContextSetupQueryResult,
    build_run_evidence_context,
    query_setup_for_run_context,
    run_context_result_to_dict,
)
from .evidence_schema import CandidateEvidenceReadiness, RunEvidenceContext, RunEvidenceGroup
from .loader import SetupKnowledge, load_setup_knowledge
from .matcher import SetupQueryResult, query_setup_knowledge

__all__ = [
    "CandidateEvidenceReadiness",
    "Clarification",
    "DialInResponse",
    "DialInSwing",
    "HiddenEvidenceSummary",
    "RunContextSetupQueryResult",
    "RunEvidenceContext",
    "RunEvidenceGroup",
    "SetupKnowledge",
    "SetupQueryResult",
    "build_dial_in_response",
    "build_run_evidence_context",
    "load_setup_knowledge",
    "query_setup_for_run_context",
    "query_setup_knowledge",
    "run_context_result_to_dict",
]
