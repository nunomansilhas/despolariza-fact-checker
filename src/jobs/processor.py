"""Processador de jobs."""

import asyncio
from typing import Callable, Any, Optional
from datetime import datetime
import logging

from .types import Job, JobType, JobStatus
from .queue import JobQueue

logger = logging.getLogger(__name__)


class JobProcessor:
    """Processa jobs da fila."""

    def __init__(self, queue: JobQueue, max_concurrent: int = 1):
        self._queue = queue
        self._max_concurrent = max_concurrent
        self._handlers: dict[JobType, Callable] = {}
        self._running = False
        self._active_jobs: set[str] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def register_handler(self, job_type: JobType, handler: Callable):
        """Registar handler para tipo de job."""
        self._handlers[job_type] = handler
        logger.info(f"Handler registered for {job_type.value}")

    async def process_job(self, job: Job) -> Any:
        """Processar um job específico."""
        handler = self._handlers.get(job.type)
        if not handler:
            raise ValueError(f"No handler for job type: {job.type}")

        async with self._semaphore:
            self._active_jobs.add(job.id)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()

            try:
                logger.info(f"Processing job: {job.type.value} ({job.id[:8]})")

                if asyncio.iscoroutinefunction(handler):
                    result = await handler(job.data)
                else:
                    result = handler(job.data)

                job.status = JobStatus.COMPLETED
                job.result = result
                job.completed_at = datetime.now()

                await self._queue.mark_completed(job, result)
                return result

            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now()

                await self._queue.mark_failed(job, str(e))
                logger.error(f"Job failed: {job.type.value}: {e}")
                raise

            finally:
                self._active_jobs.discard(job.id)

    async def start(self):
        """Iniciar processamento contínuo da fila."""
        self._running = True
        logger.info(f"Job processor started (max_concurrent={self._max_concurrent})")

        while self._running:
            job = self._queue.pop_next()
            if job:
                # Processar em background para não bloquear
                asyncio.create_task(self.process_job(job))
            else:
                # Esperar um pouco antes de verificar novamente
                await asyncio.sleep(0.1)

    async def stop(self):
        """Parar processamento."""
        self._running = False
        # Esperar jobs ativos terminarem
        while self._active_jobs:
            await asyncio.sleep(0.1)
        logger.info("Job processor stopped")

    def is_running(self) -> bool:
        return self._running

    @property
    def active_count(self) -> int:
        return len(self._active_jobs)


class TranscriptionProcessor(JobProcessor):
    """Processador especializado para transcrição."""

    def __init__(self, queue: JobQueue, transcriber, on_transcript: Callable = None):
        super().__init__(queue, max_concurrent=1)  # Transcrição é sequencial
        self._transcriber = transcriber
        self._on_transcript = on_transcript

        # Registar handler
        self.register_handler(JobType.TRANSCRIBE, self._handle_transcribe)

    async def _handle_transcribe(self, data: dict) -> dict:
        """Handler para job de transcrição."""
        transcript = await self._transcriber.process(data)

        if self._on_transcript:
            await self._on_transcript(transcript)

        return transcript.to_dict() if hasattr(transcript, 'to_dict') else transcript


class AnalysisProcessor(JobProcessor):
    """Processador especializado para análise."""

    def __init__(self, queue: JobQueue, analyzer, max_concurrent: int = 2, on_analysis: Callable = None):
        super().__init__(queue, max_concurrent=max_concurrent)
        self._analyzer = analyzer
        self._on_analysis = on_analysis

        # Registar handler
        self.register_handler(JobType.ANALYZE, self._handle_analyze)

    async def _handle_analyze(self, data: dict) -> dict:
        """Handler para job de análise."""
        analysis = await self._analyzer.analyze_chapter(
            chapter_id=data["chapter_id"],
            chapter_title=data["chapter_title"],
            text=data["text"]
        )

        if self._on_analysis:
            await self._on_analysis(analysis)

        return {
            "chapter_id": analysis.chapter_id,
            "chapter_title": analysis.chapter_title,
            "summary": analysis.summary,
            "key_topics": analysis.key_topics,
            "key_claims": analysis.key_claims,
            "speakers_mentioned": analysis.speakers_mentioned,
            "sentiment": analysis.sentiment
        }


class FactCheckProcessor(JobProcessor):
    """Processador especializado para fact-checking."""

    def __init__(self, queue: JobQueue, fact_checker, on_result: Callable = None):
        super().__init__(queue, max_concurrent=1)  # Fact-check sequencial
        self._fact_checker = fact_checker
        self._on_result = on_result

        # Registar handler
        self.register_handler(JobType.FACT_CHECK, self._handle_fact_check)

    async def _handle_fact_check(self, data: dict) -> dict:
        """Handler para job de fact-check."""
        result = await self._fact_checker.verify_claim(
            claim=data["claim"],
            context=data.get("context", "")
        )

        if self._on_result:
            await self._on_result(result)

        return result
