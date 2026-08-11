"""Source-backed setup knowledge; action-producing services remain internal."""

from .loader import SetupKnowledge, load_setup_knowledge

__all__ = [
    "SetupKnowledge",
    "load_setup_knowledge",
]
