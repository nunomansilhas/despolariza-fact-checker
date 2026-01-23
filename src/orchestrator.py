"""Orchestrator - coordena os agentes e o fluxo de dados."""

import asyncio
import json
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
import logging

from .capture.youtube import YouTubeCapture, VideoInfo, AudioChunk, cleanup_old_temp_dirs
from .capture.audio_buffer import AudioBuffer
from .agents.transcriber import TranscriberAgent
from .agents.fact_checker import FactCheckerAgent
from .agents.rhetoric import RhetoricAnalyzerAgent
from .agents.description_parser import extract_chapters_smart, DescriptionChapter
from .models.transcript import TranscriptChunk
from .models.claim import FactCheckResult
from .models.analysis import RhetoricAnalysis, Chapter, ChapterAnalysis
from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Estado de uma sessão de análise."""

    id: str
    url: str
    video_info: Optional[VideoInfo] = None
    status: str = "initializing"  # initializing, running, paused, completed, error
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Dados acumulados
    transcripts: list[TranscriptChunk] = field(default_factory=list)
    fact_checks: list[FactCheckResult] = field(default_factory=list)
    rhetoric_analyses: list[RhetoricAnalysis] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)

    # Progresso
    current_time: float = 0.0
    chunks_processed: int = 0
    error_message: Optional[str] = None


class Orchestrator:
    """Coordena a análise de um podcast/vídeo."""

    def __init__(self):
        # Agentes
        self.transcriber = TranscriberAgent()
        self.fact_checker = FactCheckerAgent()
        self.rhetoric_analyzer = RhetoricAnalyzerAgent()

        # Estado
        self._session: Optional[SessionState] = None
        self._capture: Optional[YouTubeCapture] = None
        self._buffer = AudioBuffer(max_size=settings.audio_buffer_size)

        # Callbacks para notificar o frontend
        self._callbacks: dict[str, list[Callable]] = {
            "transcript": [],
            "fact_check": [],
            "rhetoric": [],
            "chapter": [],
            "progress": [],
            "status": [],      # Status updates (loading model, downloading, etc.)
            "error": [],
            "complete": [],
        }

        # Setup callbacks dos agentes
        self._setup_agent_callbacks()

    def _setup_agent_callbacks(self):
        """Configura callbacks dos agentes (para processamento em background)."""
        pass  # Agora processamos síncronamente no _process_video

    def _get_autosave_path(self) -> Path:
        """Retorna o caminho para o ficheiro de auto-save."""
        return Path("data") / "session_autosave.json"

    def _autosave(self):
        """Guarda sessão atual em ficheiro para recuperação."""
        if not self._session:
            return

        try:
            save_path = self._get_autosave_path()
            save_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "session_id": self._session.id,
                "url": self._session.url,
                "status": self._session.status,
                "video_info": {
                    "title": self._session.video_info.title if self._session.video_info else None,
                    "duration": self._session.video_info.duration if self._session.video_info else None,
                } if self._session.video_info else None,
                "current_time": self._session.current_time,
                "chunks_processed": self._session.chunks_processed,
                "transcripts": [
                    {
                        "chunk_id": t.chunk_id,
                        "text": t.text,
                        "start_time": t.start_time,
                        "end_time": t.end_time,
                        "confidence": t.confidence,
                        "segments": [
                            {"start": s.start, "end": s.end, "text": s.text}
                            for s in (t.segments or [])
                        ]
                    }
                    for t in self._session.transcripts
                ],
                "chapters": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "start_time": c.start_time,
                        "end_time": c.end_time,
                        "detected_by": c.detected_by
                    }
                    for c in self._session.chapters
                ],
                "saved_at": datetime.now().isoformat()
            }

            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Auto-saved session: {self._session.chunks_processed} chunks")

        except Exception as e:
            logger.error(f"Auto-save error: {e}")

    def load_autosave(self) -> Optional[dict]:
        """Carrega sessão de ficheiro se existir."""
        try:
            save_path = self._get_autosave_path()
            if save_path.exists():
                with open(save_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading autosave: {e}")
        return None

    async def _process_fact_check(self, transcript: TranscriptChunk):
        """Processa fact-check em background."""
        try:
            results = await self.fact_checker.process(transcript)
            if self._session and results:
                self._session.fact_checks.extend(results)
                for result in results:
                    await self._notify("fact_check", result)
        except Exception as e:
            logger.error(f"Fact-check error: {e}")

    async def _process_rhetoric(self, transcript: TranscriptChunk):
        """Processa análise retórica em background."""
        try:
            analysis = await self.rhetoric_analyzer.process(transcript)
            if self._session and analysis:
                self._session.rhetoric_analyses.append(analysis)
                await self._notify("rhetoric", analysis)
        except Exception as e:
            logger.error(f"Rhetoric analysis error: {e}")

    def on(self, event: str, callback: Callable):
        """Regista callback para um evento."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    async def _notify(self, event: str, data: Any):
        """Notifica todos os callbacks de um evento."""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")

    async def start_session(self, url: str, custom_chapters: list[dict] = None) -> SessionState:
        """
        Inicia uma nova sessão de análise.

        Args:
            url: URL do vídeo do YouTube
            custom_chapters: Lista de capítulos customizados (opcional)
                            Formato: [{"id": "ch_0", "title": "...", "start_time": 0, "end_time": 60}, ...]

        Returns:
            SessionState com informação da sessão
        """
        # Limpar ficheiros temporários de sessões anteriores
        cleanup_old_temp_dirs()

        # Criar sessão
        self._session = SessionState(
            id=str(uuid4()),
            url=url
        )

        try:
            # Notificar frontend do status
            await self._notify("status", {"stage": "fetching_info", "message": "A obter informação do vídeo..."})

            # Iniciar captura
            self._capture = YouTubeCapture(url)
            self._session.video_info = await self._capture.get_video_info()

            # Usar capítulos customizados se fornecidos
            if custom_chapters:
                await self._notify("status", {"stage": "parsing_chapters", "message": "A usar cronologia manual..."})
                logger.info(f"Using {len(custom_chapters)} custom chapters")

                for ch in custom_chapters:
                    # Calcular end_time se não fornecido (para último capítulo)
                    end_time = ch.get("end_time")
                    if end_time is None:
                        # Procurar próximo capítulo ou usar duração do vídeo
                        idx = custom_chapters.index(ch)
                        if idx < len(custom_chapters) - 1:
                            end_time = custom_chapters[idx + 1]["start_time"]
                        else:
                            end_time = self._session.video_info.duration

                    chapter = Chapter(
                        id=ch["id"],
                        title=ch["title"],
                        start_time=ch["start_time"],
                        end_time=end_time,
                        detected_by="manual"
                    )
                    self._session.chapters.append(chapter)
                    await self._notify("chapter", chapter)
            else:
                await self._notify("status", {"stage": "parsing_chapters", "message": "A extrair cronologia da descrição..."})

                # Extrair capítulos da descrição (CRONOLOGIA)
                description_chapters = extract_chapters_smart(
                    self._session.video_info.description,
                    self._session.video_info.duration
                )

                if description_chapters:
                    logger.info(f"Found {len(description_chapters)} chapters in description")
                    for i, ch in enumerate(description_chapters):
                        chapter = Chapter(
                            id=f"ch_{i}",
                            title=ch.title,
                            start_time=ch.start_time,
                            end_time=ch.end_time,
                            detected_by="description"
                        )
                        self._session.chapters.append(chapter)
                        await self._notify("chapter", chapter)
                else:
                    # Fallback: usar capítulos do vídeo (se existirem)
                    logger.info("No chapters in description, checking video metadata...")
                    for i, ch in enumerate(self._session.video_info.chapters):
                        chapter = Chapter(
                            id=f"ch_{i}",
                            title=ch.get("title", f"Capítulo {i+1}"),
                            start_time=ch.get("start_time", 0),
                            end_time=ch.get("end_time"),
                            detected_by="video"
                        )
                        self._session.chapters.append(chapter)
                        await self._notify("chapter", chapter)

            if not self._session.chapters:
                logger.warning("No chapters found, will process entire video")

            # Iniciar agentes
            await self.transcriber.start()
            await self.fact_checker.start()
            await self.rhetoric_analyzer.start()

            # Preload Whisper model BEFORE processing starts
            # This can take several minutes for large models (downloading ~3GB)
            # If we don't preload, chunks may be deleted before transcription starts
            await self._notify("status", {"stage": "loading_model", "message": "A carregar modelo Whisper..."})
            logger.info("Preloading Whisper model (this may take a few minutes on first run)...")
            await self.transcriber.load_model()
            logger.info("Whisper model ready!")
            await self._notify("status", {"stage": "model_ready", "message": "Modelo pronto!"})

            self._session.status = "running"
            logger.info(f"Session {self._session.id} started for: {self._session.video_info.title}")

            # Iniciar processamento em background
            asyncio.create_task(self._process_video())

            return self._session

        except Exception as e:
            self._session.status = "error"
            self._session.error_message = str(e)
            await self._notify("error", str(e))
            raise

    async def _process_video(self):
        """Processa o vídeo em background."""
        try:
            await self._notify("status", {"stage": "downloading", "message": "A descarregar áudio..."})

            # Passar capítulos para chunking por capítulo (se existirem)
            chapters_data = None
            if self._session.chapters:
                chapters_data = [
                    {"start_time": ch.start_time, "end_time": ch.end_time, "title": ch.title}
                    for ch in self._session.chapters
                ]
                logger.info(f"Using chapter-based chunking with {len(chapters_data)} chapters")

            async for chunk in self._capture.stream_chunks(chapters=chapters_data):
                if self._session.status != "running":
                    break

                # Determinar capítulo atual
                current_chapter = None
                for ch in self._session.chapters:
                    if ch.start_time <= chunk.start_time:
                        if ch.end_time is None or chunk.start_time < ch.end_time:
                            current_chapter = ch

                # Notificar status com capítulo
                chapter_info = f" ({current_chapter.title})" if current_chapter else ""
                await self._notify("status", {
                    "stage": "transcribing",
                    "message": f"A transcrever chunk {chunk.chunk_id}{chapter_info}..."
                })

                # Processar este chunk SINCRONAMENTE (um de cada vez)
                try:
                    # Transcrever diretamente (sem queue)
                    transcript = await self.transcriber.process({
                        "audio_path": str(chunk.path),
                        "chunk_id": chunk.chunk_id,
                        "start_time": chunk.start_time
                    })

                    # Guardar e notificar transcrição
                    self._session.transcripts.append(transcript)
                    await self._notify("transcript", transcript)

                    # Auto-save a cada 5 chunks
                    if self._session.chunks_processed % 5 == 0:
                        self._autosave()

                    # NOTA: Fact-check e análise retórica são agora manuais
                    # O user clica no botão "Verificar Claims" na tab Análise

                except Exception as e:
                    logger.error(f"Error processing chunk {chunk.chunk_id}: {e}")

                # Limpar ficheiro do chunk após processamento
                try:
                    chunk.path.unlink()
                except Exception:
                    pass

                # Atualizar progresso
                self._session.current_time = chunk.start_time + chunk.duration
                self._session.chunks_processed += 1

                # Calcular total de chunks (por capítulo ou por duração fixa)
                total_chunks = len(self._session.chapters) if self._session.chapters else int(self._session.video_info.duration / settings.audio_chunk_duration) + 1

                await self._notify("progress", {
                    "current_time": self._session.current_time,
                    "total_duration": self._session.video_info.duration,
                    "percentage": (self._session.current_time / self._session.video_info.duration) * 100,
                    "chunks_processed": self._session.chunks_processed,
                    "total_chunks": total_chunks,
                    "current_chapter": current_chapter.title if current_chapter else None
                })

            self._session.status = "completed"
            self._session.completed_at = datetime.now()

            # Auto-save final
            self._autosave()
            logger.info(f"Session auto-saved: {self._session.chunks_processed} chunks")

            await self._notify("complete", self._session)

            # Limpar ficheiros temporários após processamento completo
            if self._capture:
                self._capture.cleanup()
                logger.info("Temp files cleaned up after completion")

        except Exception as e:
            logger.error(f"Error processing video: {e}")
            self._session.status = "error"
            self._session.error_message = str(e)
            await self._notify("error", str(e))

            # Limpar ficheiros temporários mesmo em caso de erro
            if self._capture:
                self._capture.cleanup()
                logger.info("Temp files cleaned up after error")

    async def _wait_for_agents(self, timeout: float = 60.0):
        """Espera que os agentes terminem de processar."""
        start = asyncio.get_event_loop().time()

        while True:
            # Verificar se todas as queues estão vazias
            all_empty = (
                self.transcriber.queue_size == 0 and
                self.fact_checker.queue_size == 0 and
                self.rhetoric_analyzer.queue_size == 0
            )

            if all_empty:
                break

            if asyncio.get_event_loop().time() - start > timeout:
                logger.warning("Timeout waiting for agents")
                break

            await asyncio.sleep(0.5)

    async def stop_session(self):
        """Para a sessão atual."""
        if not self._session:
            return

        self._session.status = "stopped"

        if self._capture:
            self._capture.stop()

        await self.transcriber.stop()
        await self.fact_checker.stop()
        await self.rhetoric_analyzer.stop()

        self._buffer.clear()

        if self._capture:
            self._capture.cleanup()

        logger.info(f"Session {self._session.id} stopped")

    async def clear_session(self):
        """Limpa completamente a sessão e apaga o autosave."""
        # Parar sessão se estiver a correr
        await self.stop_session()

        # Apagar ficheiro de autosave
        try:
            save_path = self._get_autosave_path()
            if save_path.exists():
                save_path.unlink()
                logger.info("Autosave file deleted")
        except Exception as e:
            logger.error(f"Error deleting autosave: {e}")

        # Resetar estado
        self._session = None
        self._capture = None
        self._buffer.clear()

        # Limpar callbacks (exceto os registados)
        # Não limpamos os callbacks porque são do frontend

        logger.info("Session cleared completely")

    def get_session_state(self) -> Optional[SessionState]:
        """Retorna o estado atual da sessão."""
        return self._session

    def get_chapter_analysis(self, chapter_id: str) -> Optional[ChapterAnalysis]:
        """Obtém análise completa de um capítulo."""
        if not self._session:
            return None

        # Encontrar capítulo
        chapter = None
        for ch in self._session.chapters:
            if ch.id == chapter_id:
                chapter = ch
                break

        if not chapter:
            return None

        # Agregar dados do capítulo
        start = chapter.start_time
        end = chapter.end_time or (start + 3600)  # Default 1h se não tiver end

        # Transcrições do capítulo
        transcripts = [
            t for t in self._session.transcripts
            if t.start_time >= start and t.start_time < end
        ]
        full_text = " ".join(t.text for t in transcripts)

        # Fact-checks do capítulo
        fact_checks = [
            fc for fc in self._session.fact_checks
            if fc.claim.timestamp >= start and fc.claim.timestamp < end
        ]

        # Análise retórica do capítulo
        rhetoric = None
        for ra in self._session.rhetoric_analyses:
            if ra.start_time >= start and ra.start_time < end:
                rhetoric = ra
                break

        return ChapterAnalysis(
            chapter=chapter,
            transcript_text=full_text,
            fact_checks=fact_checks,
            rhetoric_analysis=rhetoric
        )

    def get_full_transcript(self) -> str:
        """Retorna transcrição completa."""
        if not self._session:
            return ""
        return " ".join(t.text for t in sorted(self._session.transcripts, key=lambda t: t.start_time))

    def export_markdown(self) -> str:
        """Exporta análise em formato Markdown."""
        if not self._session or not self._session.video_info:
            return ""

        from .models.claim import Verdict

        lines = [
            f"# Análise: {self._session.video_info.title}",
            "",
            f"**Canal:** {self._session.video_info.channel}",
            f"**Duração:** {self._session.video_info.duration // 60:.0f}min",
            f"**Data análise:** {self._session.started_at.strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## Resumo Fact-Check",
            "",
        ]

        # Contar vereditos
        verdicts = {}
        for fc in self._session.fact_checks:
            v = fc.verdict
            verdicts[v] = verdicts.get(v, 0) + 1

        total = len(self._session.fact_checks) or 1
        lines.append("| Categoria | Count | % |")
        lines.append("|-----------|-------|---|")
        for v in Verdict:
            count = verdicts.get(v, 0)
            pct = (count / total) * 100
            lines.append(f"| {v.emoji} {v.label_pt} | {count} | {pct:.0f}% |")

        lines.extend(["", "---", "", "## Análise por Capítulo", ""])

        for chapter in self._session.chapters:
            analysis = self.get_chapter_analysis(chapter.id)
            if not analysis:
                continue

            lines.append(f"### [{self._format_time(chapter.start_time)}] {chapter.title}")
            lines.append("")

            if analysis.transcript_text:
                lines.append("#### Resumo")
                lines.append(analysis.transcript_text[:500] + "..." if len(analysis.transcript_text) > 500 else analysis.transcript_text)
                lines.append("")

            if analysis.fact_checks:
                lines.append("#### Fact-Check")
                lines.append("| Afirmação | Veredito |")
                lines.append("|-----------|----------|")
                for fc in analysis.fact_checks[:5]:
                    lines.append(f"| {fc.claim.text[:60]}... | {fc.verdict.emoji} |")
                lines.append("")

            if analysis.rhetoric_analysis and analysis.rhetoric_analysis.techniques:
                lines.append("#### Técnicas Retóricas")
                for tech in analysis.rhetoric_analysis.techniques[:3]:
                    lines.append(f"- **{tech.type.label_pt}**: \"{tech.quote[:50]}...\"")
                lines.append("")

        return "\n".join(lines)

    def _format_time(self, seconds: float) -> str:
        """Formata segundos em HH:MM:SS."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
