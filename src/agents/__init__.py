"""Agentes do sistema."""

from .base import BaseAgent, AgentStatus
from .transcriber import TranscriberAgent
from .fact_checker import FactCheckerAgent
from .rhetoric import RhetoricAnalyzerAgent

__all__ = [
    "BaseAgent",
    "AgentStatus",
    "TranscriberAgent",
    "FactCheckerAgent",
    "RhetoricAnalyzerAgent",
]
