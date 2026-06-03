"""Deterministic setup knowledge for local RacerZLab guidance."""

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
    "RunContextSetupQueryResult",
    "RunEvidenceContext",
    "RunEvidenceGroup",
    "SetupKnowledge",
    "SetupQueryResult",
    "build_run_evidence_context",
    "load_setup_knowledge",
    "query_setup_for_run_context",
    "query_setup_knowledge",
    "run_context_result_to_dict",
]
