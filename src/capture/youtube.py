"""Captura de áudio do YouTube usando yt-dlp."""

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional, AsyncGenerator, Callable
from dataclasses import dataclass
import logging
import json
import tempfile
import shutil

from ..config import settings

logger = logging.getLogger(__name__)

# Usar python -m yt_dlp para compatibilidade com Windows
YT_DLP_CMD = [sys.executable, "-m", "yt_dlp"]


def cleanup_old_temp_dirs():
    """
    Limpa todas as pastas temporárias antigas do despolariza.
    Deve ser chamado ao iniciar uma nova sessão.
    """
    temp_base = Path(tempfile.gettempdir())
    cleaned = 0

    for temp_dir in temp_base.glob("despolariza_*"):
        if temp_dir.is_dir():
            try:
                shutil.rmtree(temp_dir)
                cleaned += 1
                logger.info(f"Cleaned old temp dir: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean {temp_dir}: {e}")

    if cleaned > 0:
        logger.info(f"Cleaned {cleaned} old temporary directories")

    return cleaned


@dataclass
class VideoInfo:
    """Informação sobre um vídeo do YouTube."""

    id: str
    title: str
    channel: str
    duration: float  # segundos
    description: str
    chapters: list[dict]  # [{"title": "...", "start_time": 0, "end_time": 60}, ...]
    thumbnail_url: Optional[str] = None
    upload_date: Optional[str] = None


@dataclass
class AudioChunk:
    """Um chunk de áudio extraído."""

    chunk_id: int
    path: Path
    start_time: float  # segundos desde início
    duration: float  # segundos


class YouTubeCapture:
    """Extrai áudio de vídeos do YouTube."""

    def __init__(self, url: str):
        self.url = url
        self.video_info: Optional[VideoInfo] = None
        self._temp_dir: Optional[Path] = None
        self._process: Optional[subprocess.Popen] = None
        self._running = False

    async def get_video_info(self) -> VideoInfo:
        """Obtém informação sobre o vídeo."""
        if self.video_info:
            return self.video_info

        logger.info(f"Fetching video info for: {self.url}")

        cmd = YT_DLP_CMD + [
            "--dump-json",
            "--no-download",
            self.url
        ]

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            )

            if result.returncode != 0:
                raise RuntimeError(f"yt-dlp error: {result.stderr}")

            data = json.loads(result.stdout)

            # Extrair capítulos
            chapters = []
            for ch in data.get("chapters", []):
                chapters.append({
                    "title": ch.get("title", ""),
                    "start_time": ch.get("start_time", 0),
                    "end_time": ch.get("end_time", 0),
                })

            self.video_info = VideoInfo(
                id=data.get("id", ""),
                title=data.get("title", ""),
                channel=data.get("channel", data.get("uploader", "")),
                duration=data.get("duration", 0),
                description=data.get("description", ""),
                chapters=chapters,
                thumbnail_url=data.get("thumbnail"),
                upload_date=data.get("upload_date"),
            )

            logger.info(f"Video: {self.video_info.title} ({self.video_info.duration}s)")

            return self.video_info

        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout getting video info")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from yt-dlp: {e}")

    async def download_audio(self, output_path: Optional[Path] = None) -> Path:
        """
        Faz download do áudio completo do vídeo.

        Args:
            output_path: Path para o ficheiro de saída. Se None, usa temp.

        Returns:
            Path para o ficheiro de áudio (WAV, 16kHz mono)
        """
        if output_path is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="despolariza_"))
            output_path = self._temp_dir / "audio.wav"

        logger.info(f"Downloading audio to: {output_path}")

        # yt-dlp para extrair áudio + ffmpeg para converter para WAV 16kHz
        cmd = YT_DLP_CMD + [
            "-x",  # Extract audio
            "--audio-format", "wav",
            "--postprocessor-args",
            f"ffmpeg:-ar {settings.audio_sample_rate} -ac 1",  # 16kHz mono
            "-o", str(output_path.with_suffix("")),  # yt-dlp adiciona extensão
            self.url
        ]

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            )

            if result.returncode != 0:
                raise RuntimeError(f"yt-dlp download error: {result.stderr}")

            # yt-dlp pode criar com nome diferente
            actual_path = output_path.with_suffix(".wav")
            if not actual_path.exists():
                # Procurar ficheiro criado
                wav_files = list(output_path.parent.glob("*.wav"))
                if wav_files:
                    actual_path = wav_files[0]
                else:
                    raise RuntimeError("Audio file not created")

            logger.info(f"Audio downloaded: {actual_path}")
            return actual_path

        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout downloading audio")

    async def stream_chunks(
        self,
        chunk_duration: int = None,
        on_chunk: Optional[Callable[[AudioChunk], None]] = None
    ) -> AsyncGenerator[AudioChunk, None]:
        """
        Stream de chunks de áudio.

        Para vídeos já disponíveis, faz download completo e depois divide.
        Para livestreams, faria captura em tempo real (não implementado).

        Args:
            chunk_duration: Duração de cada chunk em segundos
            on_chunk: Callback opcional para cada chunk

        Yields:
            AudioChunk para cada segmento
        """
        if chunk_duration is None:
            chunk_duration = settings.audio_chunk_duration

        # Obter info do vídeo
        await self.get_video_info()

        # Download do áudio completo
        audio_path = await self.download_audio()

        # Dividir em chunks usando ffmpeg
        self._running = True
        chunk_id = 0
        current_time = 0.0
        total_duration = self.video_info.duration

        while current_time < total_duration and self._running:
            # Calcular duração deste chunk
            remaining = total_duration - current_time
            this_duration = min(chunk_duration, remaining)

            # Extrair chunk com ffmpeg
            chunk_path = audio_path.parent / f"chunk_{chunk_id:04d}.wav"

            cmd = [
                "ffmpeg",
                "-y",  # Overwrite
                "-ss", str(current_time),  # Start time
                "-t", str(this_duration),  # Duration
                "-i", str(audio_path),
                "-ar", str(settings.audio_sample_rate),
                "-ac", "1",  # Mono
                str(chunk_path)
            ]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=60)
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

            # Avançar
            chunk_id += 1
            current_time += chunk_duration

            # Pequena pausa para não sobrecarregar
            await asyncio.sleep(0.1)

    def stop(self):
        """Para o streaming."""
        self._running = False
        if self._process:
            self._process.terminate()

    def cleanup(self):
        """Limpa ficheiros temporários."""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
            logger.info(f"Cleaned up temp dir: {self._temp_dir}")

    def __del__(self):
        self.cleanup()


async def test_youtube_capture():
    """Teste básico da captura."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Teste com vídeo curto

    capture = YouTubeCapture(url)

    try:
        info = await capture.get_video_info()
        print(f"Title: {info.title}")
        print(f"Duration: {info.duration}s")
        print(f"Chapters: {len(info.chapters)}")

        # Testar chunks (só primeiros 2)
        count = 0
        async for chunk in capture.stream_chunks(chunk_duration=30):
            print(f"Chunk {chunk.chunk_id}: {chunk.path}")
            count += 1
            if count >= 2:
                capture.stop()
                break

    finally:
        capture.cleanup()


if __name__ == "__main__":
    asyncio.run(test_youtube_capture())
