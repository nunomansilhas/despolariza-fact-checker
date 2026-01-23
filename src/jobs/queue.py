"""Fila de jobs."""

import asyncio
from collections import deque
from typing import Optional, Callable, Any
import logging

from .types import Job, JobType, JobStatus

logger = logging.getLogger(__name__)


class JobQueue:
    """Fila de jobs com prioridade por tipo."""

    def __init__(self):
        self._queues: dict[JobType, deque[Job]] = {
            job_type: deque() for job_type in JobType
        }
        self._all_jobs: dict[str, Job] = {}
        self._callbacks: dict[str, list[Callable]] = {
            "job_added": [],
            "job_started": [],
            "job_completed": [],
            "job_failed": [],
        }

    def on(self, event: str, callback: Callable):
        """Registar callback para evento."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    async def _notify(self, event: str, job: Job):
        """Notificar callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(job)
                else:
                    callback(job)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")

    def add(self, job: Job) -> Job:
        """Adicionar job à fila."""
        self._queues[job.type].append(job)
        self._all_jobs[job.id] = job
        logger.info(f"Job added: {job.type.value} ({job.id[:8]})")
        asyncio.create_task(self._notify("job_added", job))
        return job

    def create(self, job_type: JobType, data: dict = None) -> Job:
        """Criar e adicionar job."""
        job = Job(type=job_type, data=data or {})
        return self.add(job)

    def get_next(self, job_type: JobType = None) -> Optional[Job]:
        """Obter próximo job da fila (por prioridade ou tipo específico)."""
        if job_type:
            if self._queues[job_type]:
                return self._queues[job_type][0]
            return None

        # Prioridade: DOWNLOAD > TRANSCRIBE > ANALYZE > FACT_CHECK
        for jt in JobType:
            if self._queues[jt]:
                return self._queues[jt][0]
        return None

    def pop_next(self, job_type: JobType = None) -> Optional[Job]:
        """Remover e retornar próximo job."""
        if job_type:
            if self._queues[job_type]:
                return self._queues[job_type].popleft()
            return None

        for jt in JobType:
            if self._queues[jt]:
                return self._queues[jt].popleft()
        return None

    def get_job(self, job_id: str) -> Optional[Job]:
        """Obter job por ID."""
        return self._all_jobs.get(job_id)

    def get_pending(self, job_type: JobType = None) -> list[Job]:
        """Obter jobs pendentes."""
        if job_type:
            return [j for j in self._queues[job_type] if j.status == JobStatus.PENDING]
        return [j for q in self._queues.values() for j in q if j.status == JobStatus.PENDING]

    def get_by_status(self, status: JobStatus) -> list[Job]:
        """Obter jobs por estado."""
        return [j for j in self._all_jobs.values() if j.status == status]

    def count(self, job_type: JobType = None) -> int:
        """Contar jobs na fila."""
        if job_type:
            return len(self._queues[job_type])
        return sum(len(q) for q in self._queues.values())

    def clear(self, job_type: JobType = None):
        """Limpar fila."""
        if job_type:
            self._queues[job_type].clear()
        else:
            for q in self._queues.values():
                q.clear()
            self._all_jobs.clear()

    async def mark_started(self, job: Job):
        """Marcar job como iniciado."""
        job.status = JobStatus.RUNNING
        job.started_at = asyncio.get_event_loop().time()
        await self._notify("job_started", job)

    async def mark_completed(self, job: Job, result: Any = None):
        """Marcar job como concluído."""
        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = asyncio.get_event_loop().time()
        await self._notify("job_completed", job)
        logger.info(f"Job completed: {job.type.value} ({job.id[:8]})")

    async def mark_failed(self, job: Job, error: str):
        """Marcar job como falhado."""
        job.status = JobStatus.FAILED
        job.error = error
        job.completed_at = asyncio.get_event_loop().time()
        await self._notify("job_failed", job)
        logger.error(f"Job failed: {job.type.value} ({job.id[:8]}): {error}")
