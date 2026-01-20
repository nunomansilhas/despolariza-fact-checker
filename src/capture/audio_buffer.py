"""Buffer circular para chunks de áudio."""

from collections import deque
from pathlib import Path
from typing import Optional
import logging

from .youtube import AudioChunk

logger = logging.getLogger(__name__)


class AudioBuffer:
    """Buffer circular que mantém os últimos N chunks de áudio."""

    def __init__(self, max_size: int = 10):
        """
        Args:
            max_size: Número máximo de chunks a manter em memória
        """
        self.max_size = max_size
        self._buffer: deque[AudioChunk] = deque(maxlen=max_size)
        self._processed_ids: set[int] = set()

    def add(self, chunk: AudioChunk):
        """Adiciona um chunk ao buffer."""
        # NOTE: We don't delete chunk files when the buffer rotates anymore.
        # Files remain in the temp directory until the transcriber processes them.
        # The temp directory cleanup at session end handles all files.
        # This is important because transcription can be slow (especially on first run
        # when the Whisper model needs to be downloaded).
        self._buffer.append(chunk)
        logger.debug(f"Buffer: added chunk {chunk.chunk_id}, size: {len(self._buffer)}")

    def get(self, chunk_id: int) -> Optional[AudioChunk]:
        """Obtém um chunk pelo ID."""
        for chunk in self._buffer:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def get_latest(self) -> Optional[AudioChunk]:
        """Obtém o chunk mais recente."""
        if self._buffer:
            return self._buffer[-1]
        return None

    def get_unprocessed(self) -> list[AudioChunk]:
        """Obtém chunks que ainda não foram processados."""
        return [c for c in self._buffer if c.chunk_id not in self._processed_ids]

    def mark_processed(self, chunk_id: int):
        """Marca um chunk como processado."""
        self._processed_ids.add(chunk_id)

    def get_range(self, start_time: float, end_time: float) -> list[AudioChunk]:
        """Obtém chunks num intervalo de tempo."""
        return [
            c for c in self._buffer
            if c.start_time < end_time and (c.start_time + c.duration) > start_time
        ]

    def _cleanup_chunk(self, chunk: AudioChunk):
        """Remove ficheiro de áudio do chunk."""
        try:
            if chunk.path.exists():
                chunk.path.unlink()
                logger.debug(f"Cleaned up chunk file: {chunk.path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup chunk {chunk.chunk_id}: {e}")

    def clear(self):
        """Limpa todo o buffer."""
        for chunk in self._buffer:
            self._cleanup_chunk(chunk)
        self._buffer.clear()
        self._processed_ids.clear()

    @property
    def size(self) -> int:
        """Número de chunks no buffer."""
        return len(self._buffer)

    @property
    def time_span(self) -> tuple[float, float]:
        """Intervalo de tempo coberto pelo buffer (start, end)."""
        if not self._buffer:
            return (0.0, 0.0)
        start = self._buffer[0].start_time
        end_chunk = self._buffer[-1]
        end = end_chunk.start_time + end_chunk.duration
        return (start, end)

    def __len__(self) -> int:
        return len(self._buffer)

    def __iter__(self):
        return iter(self._buffer)
