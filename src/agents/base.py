"""Classe base para todos os agentes."""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, Callable
from datetime import datetime
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Estado do agente."""

    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"
    STOPPED = "stopped"


class AgentStats(BaseModel):
    """Estatísticas de um agente."""

    items_processed: int = 0
    items_failed: int = 0
    total_processing_time: float = 0.0
    last_processed_at: Optional[datetime] = None

    @property
    def avg_processing_time(self) -> float:
        if self.items_processed == 0:
            return 0.0
        return self.total_processing_time / self.items_processed


class BaseAgent(ABC):
    """Classe base abstracta para agentes."""

    def __init__(self, name: str):
        self.name = name
        self.status = AgentStatus.IDLE
        self.stats = AgentStats()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable] = []

    @abstractmethod
    async def process(self, item: Any) -> Any:
        """Processa um item. Implementar nos subclasses."""
        pass

    async def start(self):
        """Inicia o agente."""
        if self._running:
            logger.warning(f"Agent {self.name} already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Agent {self.name} started")

    async def stop(self):
        """Para o agente."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.status = AgentStatus.STOPPED
        logger.info(f"Agent {self.name} stopped")

    async def submit(self, item: Any):
        """Submete um item para processamento."""
        await self._queue.put(item)
        logger.debug(f"Agent {self.name} received item, queue size: {self._queue.qsize()}")

    def on_result(self, callback: Callable):
        """Regista um callback para quando há resultados."""
        self._callbacks.append(callback)

    async def _run_loop(self):
        """Loop principal de processamento."""
        while self._running:
            try:
                # Esperar por item com timeout para poder verificar _running
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self.status = AgentStatus.PROCESSING
                start_time = datetime.now()

                try:
                    result = await self.process(item)
                    self.stats.items_processed += 1

                    # Notificar callbacks
                    for callback in self._callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(result)
                            else:
                                callback(result)
                        except Exception as e:
                            logger.error(f"Callback error in {self.name}: {e}")

                except Exception as e:
                    logger.error(f"Agent {self.name} processing error: {e}")
                    self.stats.items_failed += 1
                    self.status = AgentStatus.ERROR

                finally:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    self.stats.total_processing_time += elapsed
                    self.stats.last_processed_at = datetime.now()
                    self.status = AgentStatus.IDLE
                    self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.name} loop error: {e}")

    @property
    def queue_size(self) -> int:
        """Tamanho atual da queue."""
        return self._queue.qsize()

    def get_status_dict(self) -> dict:
        """Retorna estado como dicionário."""
        return {
            "name": self.name,
            "status": self.status.value,
            "queue_size": self.queue_size,
            "stats": self.stats.model_dump(),
        }
