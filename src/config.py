"""Configurações do sistema."""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Configurações globais da aplicação."""

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    temp_dir: Path = Field(default_factory=lambda: Path("/tmp/despolariza"))

    # Whisper
    whisper_model: str = "large-v3"  # tiny, base, small, medium, large-v3
    whisper_device: str = "auto"  # cpu, cuda, auto
    whisper_compute_type: str = "float16"  # float16, int8, float32
    whisper_language: str = "pt"

    # Audio Capture
    audio_chunk_duration: int = 30  # segundos por chunk
    audio_sample_rate: int = 16000  # Hz (Whisper espera 16kHz)
    audio_buffer_size: int = 10  # número de chunks em buffer

    # Agents
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    fact_check_enabled: bool = True
    rhetoric_analysis_enabled: bool = True

    # WebSocket
    ws_host: str = "0.0.0.0"
    ws_port: int = 3068

    # Chapter Detection
    silence_threshold: float = -40.0  # dB
    min_chapter_duration: int = 60  # segundos mínimos entre capítulos

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Criar directório temp se não existir
settings.temp_dir.mkdir(parents=True, exist_ok=True)
