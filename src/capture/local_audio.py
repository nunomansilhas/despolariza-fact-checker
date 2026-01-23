"""Captura de áudio local (ficheiro no disco)."""

import asyncio
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, AsyncGenerator, Callable
import logging

from .youtube import VideoInfo, AudioChunk
from ..config import settings

logger = logging.getLogger(__name__)


class LocalAudioCapture:
    """Processa áudio de um ficheiro local."""

    def __init__(self, audio_path: Path, video_info: VideoInfo):
        self.audio_path = audio_path
        self.video_info = video_info
        self._temp_dir: Optional[Path] = None
        self._running = False

    async def get_video_info(self) -> VideoInfo:
        """Retorna informação do áudio."""
        return self.video_info

    async def download_audio(self, output_path: Optional[Path] = None) -> Path:
        """
        Prepara o áudio para processamento.
        Converte para WAV 16kHz se necessário.
        """
        self._temp_dir = Path(tempfile.mkdtemp(prefix="despolariza_"))

        # Se já é WAV 16kHz, só copiar
        if self.audio_path.suffix.lower() == ".wav":
            # Verificar se é 16kHz mono
            temp_audio = self._temp_dir / "audio.wav"
            shutil.copy2(self.audio_path, temp_audio)
            logger.info(f"Copied local audio to: {temp_audio}")
            return temp_audio

        # Converter para WAV 16kHz mono
        output_path = self._temp_dir / "audio.wav"

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(self.audio_path),
            "-ar", str(settings.audio_sample_rate),
            "-ac", "1",
            str(output_path)
        ]

        logger.info(f"Converting local audio to WAV 16kHz: {self.audio_path}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, timeout=600)
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr.decode()}")

        logger.info(f"Audio converted: {output_path}")
        return output_path

    async def stream_chunks(
        self,
        chunk_duration: int = None,
        chapters: list[dict] = None,
        on_chunk: Optional[Callable[[AudioChunk], None]] = None
    ) -> AsyncGenerator[AudioChunk, None]:
        """
        Stream de chunks de áudio do ficheiro local.
        """
        if chunk_duration is None:
            chunk_duration = settings.audio_chunk_duration

        # Preparar áudio
        audio_path = await self.download_audio()

        self._running = True
        chunk_id = 0
        total_duration = self.video_info.duration

        # Se temos capítulos, criar um chunk por capítulo
        if chapters and len(chapters) > 0:
            logger.info(f"Using chapter-based chunking ({len(chapters)} chapters)")

            for i, chapter in enumerate(chapters):
                if not self._running:
                    break

                start_time = chapter.get("start_time", 0)
                end_time = chapter.get("end_time")

                if end_time is None:
                    if i < len(chapters) - 1:
                        end_time = chapters[i + 1].get("start_time", total_duration)
                    else:
                        end_time = total_duration

                this_duration = end_time - start_time

                # Extrair chunk com ffmpeg
                chunk_path = audio_path.parent / f"chunk_{chunk_id:04d}.wav"

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss", str(start_time),
                    "-t", str(this_duration),
                    "-i", str(audio_path),
                    "-ar", str(settings.audio_sample_rate),
                    "-ac", "1",
                    str(chunk_path)
                ]

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda cmd=cmd: subprocess.run(cmd, capture_output=True, timeout=120)
                )

                if result.returncode != 0:
                    logger.error(f"FFmpeg error: {result.stderr.decode()}")
                    continue

                chunk = AudioChunk(
                    chunk_id=chunk_id,
                    path=chunk_path,
                    start_time=start_time,
                    duration=this_duration,
                )

                chapter_title = chapter.get("title", f"Chapter {i+1}")
                logger.info(f"Created chunk {chunk_id} for '{chapter_title}': {start_time:.1f}s - {end_time:.1f}s")

                if on_chunk:
                    on_chunk(chunk)

                yield chunk

                chunk_id += 1
                await asyncio.sleep(0.1)
        else:
            # Fixed duration chunks
            current_time = 0.0

            while current_time < total_duration and self._running:
                remaining = total_duration - current_time
                this_duration = min(chunk_duration, remaining)

                chunk_path = audio_path.parent / f"chunk_{chunk_id:04d}.wav"

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss", str(current_time),
                    "-t", str(this_duration),
                    "-i", str(audio_path),
                    "-ar", str(settings.audio_sample_rate),
                    "-ac", "1",
                    str(chunk_path)
                ]

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda cmd=cmd: subprocess.run(cmd, capture_output=True, timeout=60)
                )

                if result.returncode != 0:
                    logger.error(f"FFmpeg error: {result.stderr.decode()}")
                    break

                chunk = AudioChunk(
                    chunk_id=chunk_id,
                    path=chunk_path,
                    start_time=current_time,
                    duration=this_duration,
                )

                logger.info(f"Created chunk {chunk_id}: {current_time:.1f}s - {current_time + this_duration:.1f}s")

                if on_chunk:
                    on_chunk(chunk)

                yield chunk

                chunk_id += 1
                current_time += chunk_duration
                await asyncio.sleep(0.1)

    def stop(self):
        """Para o streaming."""
        self._running = False

    def cleanup(self):
        """Limpa ficheiros temporários."""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
            logger.info(f"Cleaned up temp dir: {self._temp_dir}")

    def __del__(self):
        self.cleanup()
