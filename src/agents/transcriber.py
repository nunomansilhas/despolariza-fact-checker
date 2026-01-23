"""Agente de transcrição usando Whisper/WhisperX com diarização opcional."""

import asyncio
import math
from pathlib import Path
from typing import Optional
import logging

from .base import BaseAgent
from ..models.transcript import TranscriptChunk, TranscriptSegment
from ..config import settings

logger = logging.getLogger(__name__)


class TranscriberAgent(BaseAgent):
    """Agente que transcreve áudio usando Whisper ou WhisperX (com diarização)."""

    def __init__(self):
        super().__init__("transcriber")
        self._model = None
        self._diarize_model = None
        self._model_loaded = False
        self._use_whisperx = False
        self._align_model = None
        self._align_metadata = None

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

        # Debug: mostrar configuração de diarização
        logger.info(f"Diarization config: enable={settings.enable_diarization}, hf_token={'SET' if settings.hf_token else 'NOT SET'}")

        # Tentar WhisperX primeiro se diarização está ativada
        if settings.enable_diarization and settings.hf_token:
            try:
                # Workaround para PyTorch 2.6+ (weights_only=True por defeito)
                # Os modelos pyannote/whisperx são de fontes confiáveis (HuggingFace)
                # então usamos weights_only=False temporariamente
                import torch
                _original_torch_load = torch.load

                def _patched_torch_load(*args, **kwargs):
                    # Forçar weights_only=False para carregar modelos legacy
                    kwargs['weights_only'] = False
                    return _original_torch_load(*args, **kwargs)

                torch.load = _patched_torch_load
                logger.info("Patched torch.load with weights_only=False for WhisperX/pyannote models")

                try:
                    import whisperx
                    logger.info("Loading WhisperX with diarization support...")

                    self._model = whisperx.load_model(
                        settings.whisper_model,
                        device=device,
                        compute_type=compute_type,
                        language=settings.whisper_language
                    )

                    # Carregar modelo de diarização
                    logger.info("Loading diarization model...")
                    self._diarize_model = whisperx.DiarizationPipeline(
                        use_auth_token=settings.hf_token,
                        device=device
                    )

                    self._use_whisperx = True
                    logger.info("WhisperX loaded with diarization support")
                    return

                finally:
                    # Restaurar torch.load original
                    torch.load = _original_torch_load
                    logger.info("Restored original torch.load")

            except ImportError as e:
                logger.warning(f"WhisperX not installed: {e}, falling back to faster-whisper")
            except Exception as e:
                logger.warning(f"Failed to load WhisperX: {e}", exc_info=True)

        # Fallback para faster-whisper
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                settings.whisper_model,
                device=device,
                compute_type=compute_type,
            )
            self._use_whisperx = False
            logger.info("Using faster-whisper (no diarization)")

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

        if self._use_whisperx:
            result = await loop.run_in_executor(
                None,
                self._transcribe_whisperx,
                str(audio_path),
                start_time
            )
        else:
            result = await loop.run_in_executor(
                None,
                self._transcribe_faster_whisper,
                str(audio_path),
                start_time
            )

        segments, full_text, language, avg_confidence = result

        # Determinar end_time
        end_time = segments[-1].end if segments else start_time + settings.audio_chunk_duration

        chunk = TranscriptChunk(
            chunk_id=chunk_id,
            start_time=start_time,
            end_time=end_time,
            text=full_text,
            segments=segments,
            language=language,
            confidence=avg_confidence
        )

        # Log com info de speakers
        speakers = set(s.speaker for s in segments if s.speaker)
        speaker_info = f", speakers: {speakers}" if speakers else ""
        logger.info(f"Transcribed chunk {chunk_id}: {len(full_text)} chars, {len(segments)} segments{speaker_info}")

        return chunk

    def _transcribe_whisperx(self, audio_path: str, start_time: float) -> tuple:
        """Transcrição com WhisperX e diarização."""
        import whisperx

        # Carregar áudio
        audio = whisperx.load_audio(audio_path)

        # Transcrever
        result = self._model.transcribe(audio, batch_size=16)

        # Alinhar com timestamps precisos
        if self._align_model is None:
            device = settings.whisper_device
            if device == "auto":
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"

            self._align_model, self._align_metadata = whisperx.load_align_model(
                language_code=settings.whisper_language,
                device=device
            )

        result = whisperx.align(
            result["segments"],
            self._align_model,
            self._align_metadata,
            audio,
            device=settings.whisper_device if settings.whisper_device != "auto" else "cpu",
            return_char_alignments=False
        )

        # Diarização
        if self._diarize_model:
            diarize_segments = self._diarize_model(
                audio,
                min_speakers=settings.min_speakers,
                max_speakers=settings.max_speakers
            )
            result = whisperx.assign_word_speakers(diarize_segments, result)

        # Converter para nosso formato
        segments = []
        full_text_parts = []

        for seg in result.get("segments", []):
            speaker = seg.get("speaker", None)
            text = seg.get("text", "").strip()

            if not text:
                continue

            segment = TranscriptSegment(
                text=text,
                start=start_time + seg.get("start", 0),
                end=start_time + seg.get("end", 0),
                confidence=0.9,  # WhisperX não retorna confidence diretamente
                speaker=speaker
            )
            segments.append(segment)
            full_text_parts.append(f"[{speaker}] {text}" if speaker else text)

        full_text = " ".join(full_text_parts)
        avg_confidence = 0.9

        return segments, full_text, settings.whisper_language, avg_confidence

    def _transcribe_faster_whisper(self, audio_path: str, start_time: float) -> tuple:
        """Transcrição com faster-whisper (sem diarização)."""
        if self._model is None:
            return self._mock_transcribe(audio_path, start_time)

        segments_gen, info = self._model.transcribe(
            audio_path,
            language=settings.whisper_language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
        )

        segments = []
        full_text_parts = []

        for segment in segments_gen:
            raw_logprob = segment.avg_logprob if hasattr(segment, 'avg_logprob') else -0.1
            confidence = max(0.0, min(1.0, math.exp(raw_logprob)))

            seg = TranscriptSegment(
                text=segment.text.strip(),
                start=start_time + segment.start,
                end=start_time + segment.end,
                confidence=confidence,
                speaker=None  # Sem diarização
            )
            segments.append(seg)
            full_text_parts.append(segment.text.strip())

        full_text = " ".join(full_text_parts)
        avg_confidence = (
            sum(s.confidence for s in segments) / len(segments)
            if segments else 0.0
        )

        return segments, full_text, info.language if hasattr(info, 'language') else settings.whisper_language, avg_confidence

    def _mock_transcribe(self, audio_path: str, start_time: float) -> tuple:
        """Transcrição mock para desenvolvimento."""
        mock_segments = [
            TranscriptSegment(
                text=f"[Mock transcript para {Path(audio_path).name}]",
                start=start_time,
                end=start_time + 5.0,
                confidence=0.9,
                speaker="SPEAKER_00"
            ),
            TranscriptSegment(
                text="Esta é uma transcrição de teste gerada automaticamente.",
                start=start_time + 5.0,
                end=start_time + 10.0,
                confidence=0.85,
                speaker="SPEAKER_01"
            ),
            TranscriptSegment(
                text="O modelo Whisper não está instalado.",
                start=start_time + 10.0,
                end=start_time + 15.0,
                confidence=0.88,
                speaker="SPEAKER_00"
            ),
        ]

        full_text = " ".join(f"[{s.speaker}] {s.text}" for s in mock_segments)

        return mock_segments, full_text, "pt", 0.87


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
