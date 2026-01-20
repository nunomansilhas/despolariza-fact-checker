"""Agente de transcrição usando Whisper."""

import asyncio
from pathlib import Path
from typing import Optional
import logging

from .base import BaseAgent
from ..models.transcript import TranscriptChunk, TranscriptSegment
from ..config import settings

logger = logging.getLogger(__name__)


class TranscriberAgent(BaseAgent):
    """Agente que transcreve áudio usando Whisper."""

    def __init__(self):
        super().__init__("transcriber")
        self._model = None
        self._model_loaded = False

    async def load_model(self):
        """Carrega o modelo Whisper (async wrapper)."""
        if self._model_loaded:
            return

        logger.info(f"Loading Whisper model: {settings.whisper_model}")

        # Executar em thread separada porque o load é síncrono e pesado
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)

        self._model_loaded = True
        logger.info("Whisper model loaded successfully")

    def _load_model_sync(self):
        """Carrega o modelo de forma síncrona."""
        try:
            from faster_whisper import WhisperModel

            # Determinar device
            device = settings.whisper_device
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"

            compute_type = settings.whisper_compute_type
            if device == "cpu" and compute_type == "float16":
                compute_type = "int8"  # CPU não suporta float16 bem

            logger.info(f"Using device: {device}, compute_type: {compute_type}")

            self._model = WhisperModel(
                settings.whisper_model,
                device=device,
                compute_type=compute_type,
            )

        except ImportError:
            logger.warning("faster-whisper not installed, using mock transcriber")
            self._model = None

    async def process(self, item: dict) -> TranscriptChunk:
        """
        Processa um chunk de áudio.

        Args:
            item: Dicionário com:
                - audio_path: Path para o ficheiro de áudio
                - chunk_id: ID do chunk
                - start_time: Timestamp de início (segundos)

        Returns:
            TranscriptChunk com a transcrição
        """
        if not self._model_loaded:
            await self.load_model()

        audio_path = Path(item["audio_path"])
        chunk_id = item["chunk_id"]
        start_time = item.get("start_time", 0.0)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Transcrever
        loop = asyncio.get_event_loop()
        segments_data, info = await loop.run_in_executor(
            None,
            self._transcribe_sync,
            str(audio_path)
        )

        # Converter para modelos
        segments = []
        full_text_parts = []

        for segment in segments_data:
            seg = TranscriptSegment(
                text=segment.text.strip(),
                start=start_time + segment.start,
                end=start_time + segment.end,
                confidence=segment.avg_logprob if hasattr(segment, 'avg_logprob') else 0.9
            )
            segments.append(seg)
            full_text_parts.append(segment.text.strip())

        full_text = " ".join(full_text_parts)

        # Calcular confiança média
        avg_confidence = (
            sum(s.confidence for s in segments) / len(segments)
            if segments else 0.0
        )

        # Determinar end_time
        end_time = segments[-1].end if segments else start_time + settings.audio_chunk_duration

        chunk = TranscriptChunk(
            chunk_id=chunk_id,
            start_time=start_time,
            end_time=end_time,
            text=full_text,
            segments=segments,
            language=info.language if hasattr(info, 'language') else settings.whisper_language,
            confidence=avg_confidence
        )

        logger.info(f"Transcribed chunk {chunk_id}: {len(full_text)} chars, {len(segments)} segments")

        return chunk

    def _transcribe_sync(self, audio_path: str) -> tuple:
        """Transcrição síncrona."""
        if self._model is None:
            # Mock para testes
            return self._mock_transcribe(audio_path)

        segments, info = self._model.transcribe(
            audio_path,
            language=settings.whisper_language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,  # Filtrar silêncio
        )

        # Converter generator para lista
        segments_list = list(segments)

        return segments_list, info

    def _mock_transcribe(self, audio_path: str) -> tuple:
        """Transcrição mock para desenvolvimento."""
        from dataclasses import dataclass

        @dataclass
        class MockSegment:
            text: str
            start: float
            end: float
            avg_logprob: float = -0.3

        @dataclass
        class MockInfo:
            language: str = "pt"
            duration: float = 30.0

        # Gerar texto mock
        mock_segments = [
            MockSegment(
                text=f"[Mock transcript para {Path(audio_path).name}]",
                start=0.0,
                end=5.0,
                avg_logprob=-0.2
            ),
            MockSegment(
                text="Esta é uma transcrição de teste gerada automaticamente.",
                start=5.0,
                end=10.0,
                avg_logprob=-0.3
            ),
            MockSegment(
                text="O modelo Whisper não está instalado.",
                start=10.0,
                end=15.0,
                avg_logprob=-0.25
            ),
        ]

        return mock_segments, MockInfo()


async def test_transcriber():
    """Teste básico do transcriber."""
    agent = TranscriberAgent()
    await agent.start()

    # Este teste precisa de um ficheiro de áudio real
    # await agent.submit({
    #     "audio_path": "/path/to/test.wav",
    #     "chunk_id": 1,
    #     "start_time": 0.0
    # })

    await agent.stop()
    print(f"Transcriber stats: {agent.stats}")


if __name__ == "__main__":
    asyncio.run(test_transcriber())
