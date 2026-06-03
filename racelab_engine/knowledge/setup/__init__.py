"""Deterministic setup knowledge for local RacerZLab guidance."""

from .loader import SetupKnowledge, load_setup_knowledge
from .matcher import SetupQueryResult, query_setup_knowledge

__all__ = ["SetupKnowledge", "SetupQueryResult", "load_setup_knowledge", "query_setup_knowledge"]
