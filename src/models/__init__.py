"""Modelos de dados."""

from .transcript import TranscriptChunk, TranscriptSegment
from .claim import Claim, FactCheckResult, Verdict
from .analysis import RhetoricTechnique, RhetoricAnalysis, ChapterAnalysis

__all__ = [
    "TranscriptChunk",
    "TranscriptSegment",
    "Claim",
    "FactCheckResult",
    "Verdict",
    "RhetoricTechnique",
    "RhetoricAnalysis",
    "ChapterAnalysis",
]
