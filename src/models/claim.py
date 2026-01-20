"""Modelos de fact-checking."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class Verdict(str, Enum):
    """Vereditos possíveis para uma afirmação."""

    TRUE = "true"  # ✅
    PARTIAL = "partial"  # ⚠️
    FALSE = "false"  # ❌
    INCONCLUSIVE = "inconclusive"  # ❓
    OPINION = "opinion"  # Não verificável (opinião)
    PENDING = "pending"  # Ainda a verificar

    @property
    def emoji(self) -> str:
        """Retorna o emoji correspondente."""
        return {
            Verdict.TRUE: "✅",
            Verdict.PARTIAL: "⚠️",
            Verdict.FALSE: "❌",
            Verdict.INCONCLUSIVE: "❓",
            Verdict.OPINION: "💭",
            Verdict.PENDING: "⏳",
        }[self]

    @property
    def label_pt(self) -> str:
        """Retorna o label em português."""
        return {
            Verdict.TRUE: "Verdadeiro",
            Verdict.PARTIAL: "Parcialmente Verdadeiro",
            Verdict.FALSE: "Falso",
            Verdict.INCONCLUSIVE: "Inconclusivo",
            Verdict.OPINION: "Opinião",
            Verdict.PENDING: "A verificar",
        }[self]


class Claim(BaseModel):
    """Uma afirmação identificada no discurso."""

    id: str
    text: str  # A afirmação original
    speaker: Optional[str] = None  # Quem disse
    timestamp: float  # Quando foi dita (segundos)
    chunk_id: int  # De que chunk veio
    is_verifiable: bool = True  # Se é verificável factualmente
    context: Optional[str] = None  # Contexto circundante


class FactCheckResult(BaseModel):
    """Resultado da verificação de uma afirmação."""

    claim: Claim
    verdict: Verdict = Verdict.PENDING
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    explanation: str = ""
    sources: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    corrected_info: Optional[str] = None  # Informação correta, se diferente
    checked_at: datetime = Field(default_factory=datetime.now)

    @property
    def summary(self) -> str:
        """Resumo curto do resultado."""
        return f"{self.verdict.emoji} {self.verdict.label_pt}: {self.claim.text[:50]}..."
