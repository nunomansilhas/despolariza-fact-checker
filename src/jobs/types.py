"""Tipos de jobs e estados."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
from uuid import uuid4


class JobType(str, Enum):
    """Tipos de jobs disponíveis."""
    DOWNLOAD = "download"        # Baixar áudio do YouTube
    TRANSCRIBE = "transcribe"    # Transcrever chunk de áudio
    ANALYZE = "analyze"          # Analisar capítulo (resumo, tópicos, claims)
    FACT_CHECK = "fact_check"    # Verificar claim específica


class JobStatus(str, Enum):
    """Estado do job."""
    PENDING = "pending"          # Na fila
    RUNNING = "running"          # A processar
    COMPLETED = "completed"      # Concluído
    FAILED = "failed"            # Falhou
    CANCELLED = "cancelled"      # Cancelado


@dataclass
class Job:
    """Um job para processamento."""
    type: JobType
    data: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration(self) -> Optional[float]:
        """Duração em segundos."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "data": self.data,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "duration": self.duration
        }
