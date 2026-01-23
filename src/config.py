"""Configurações do sistema."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Configurações globais da aplicação."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignorar variáveis extra no .env
    )

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    temp_dir: Path = Field(default_factory=lambda: Path("/tmp/despolariza"))

    # Whisper / WhisperX
    whisper_model: str = "large-v3"  # tiny, base, small, medium, large-v3
    whisper_device: str = "auto"  # cpu, cuda, auto
    whisper_compute_type: str = "float16"  # float16, int8, float32
    whisper_language: str = "pt"

    # Speaker Diarization (WhisperX)
    enable_diarization: bool = False  # Diarização por voz (desativado - usar AI para identificar)
    hf_token: str = ""  # HuggingFace token para pyannote (diarização)
    min_speakers: int = 2  # Número mínimo de speakers esperados (podcast = 2)
    max_speakers: int = 2  # Número máximo de speakers esperados (podcast = 2)

    # Audio Capture
    audio_chunk_duration: int = 30  # segundos por chunk
    audio_sample_rate: int = 16000  # Hz (Whisper espera 16kHz)
    audio_buffer_size: int = 10  # número de chunks em buffer

    # YouTube - Cookies para contornar verificação de bot
    # Browsers suportados: chrome, firefox, edge, opera, brave, chromium, safari
    yt_cookies_browser: str = ""  # Ex: "chrome", "firefox", "edge"
    yt_cookies_file: str = ""  # Alternativa: path para ficheiro cookies.txt

    # Audio Cache - guardar áudio descarregado para não repetir downloads
    audio_cache_enabled: bool = True  # Ativar cache de áudio
    audio_cache_dir: str = ""  # Pasta para cache de áudio (deixar vazio para usar ~/.despolariza/audio_cache)

    # Audio local - usar ficheiro de áudio local em vez de YouTube
    local_audio_file: str = ""  # Path para ficheiro de áudio local (mp3, wav, etc)

    # Agents - Anthropic (opcional, fallback)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Agents - Ollama (local, gratuito)
    ollama_enabled: bool = True  # Usar Ollama em vez de Anthropic
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"  # Modelo para fact-checking
    analyzer_max_concurrent: int = 2  # Capítulos a analisar em paralelo (1-4)

    # Feature flags
    fact_check_enabled: bool = True
    rhetoric_analysis_enabled: bool = True

    # WebSocket
    ws_host: str = "0.0.0.0"
    ws_port: int = 3068

    # Chapter Detection
    silence_threshold: float = -40.0  # dB
    min_chapter_duration: int = 60  # segundos mínimos entre capítulos


settings = Settings()

# Criar directório temp se não existir
settings.temp_dir.mkdir(parents=True, exist_ok=True)
