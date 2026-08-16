"""Source-backed setup knowledge; action-producing services remain internal."""

from .loader import SetupKnowledge, load_setup_knowledge
from .engineering_knowledge import (
    compile_engineering_knowledge_coverage,
    compile_mechanism_setup_bridges,
)

__all__ = [
    "SetupKnowledge",
    "load_setup_knowledge",
    "compile_engineering_knowledge_coverage",
    "compile_mechanism_setup_bridges",
]
