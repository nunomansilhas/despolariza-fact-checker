"""Modelos de transcrição."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TranscriptSegment(BaseModel):
    """Um segmento individual de transcrição (palavra ou frase)."""

    text: str
    start: float  # segundos desde início
    end: float
    confidence: float = Field(ge=0.0, le=1.0)
    speaker: Optional[str] = None  # SPEAKER_00, SPEAKER_01, etc.


class TranscriptChunk(BaseModel):
    """Um chunk de transcrição (tipicamente 30s de áudio)."""

    chunk_id: int
    start_time: float  # segundos desde início do vídeo
    end_time: float
    text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    language: str = "pt"
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    processed_at: datetime = Field(default_factory=datetime.now)

    @property
    def duration(self) -> float:
        """Duração do chunk em segundos."""
        return self.end_time - self.start_time

    def get_text_at(self, timestamp: float) -> Optional[str]:
        """Retorna o texto no timestamp especificado."""
        for segment in self.segments:
            if segment.start <= timestamp <= segment.end:
                return segment.text
        return None
