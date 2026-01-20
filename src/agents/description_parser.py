"""Parser para extrair cronologia/timestamps da descrição do vídeo."""

import re
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class DescriptionChapter:
    """Um capítulo/tópico extraído da descrição."""

    title: str
    start_time: float  # segundos
    end_time: Optional[float] = None  # calculado depois
    raw_timestamp: str = ""  # timestamp original (ex: "1:23:45")


def parse_timestamp(timestamp: str) -> float:
    """
    Converte timestamp em segundos.

    Suporta formatos:
    - "1:23:45" (h:mm:ss)
    - "23:45" (mm:ss)
    - "45" (ss)
    - "01:23:45"
    """
    parts = timestamp.strip().split(":")
    parts = [int(p) for p in parts]

    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    else:
        return 0.0


def parse_description_chapters(description: str, video_duration: float = None) -> list[DescriptionChapter]:
    """
    Extrai capítulos/cronologia da descrição do vídeo.

    Procura padrões como:
    - "00:00:00 - Introdução"
    - "1:23:45 Tema qualquer"
    - "[00:00] Início"
    - "00:00 | Abertura"

    Args:
        description: Texto da descrição do vídeo
        video_duration: Duração total do vídeo (para calcular end_time)

    Returns:
        Lista de DescriptionChapter ordenados por tempo
    """
    chapters = []

    # Padrões para timestamps
    # Formato: timestamp seguido de separador e título
    patterns = [
        # "00:00:00 - Título" ou "0:00:00 - Título"
        r'(\d{1,2}:\d{2}:\d{2})\s*[-–—|:]\s*(.+?)(?=\n|$)',
        # "00:00 - Título" ou "0:00 - Título"
        r'(\d{1,2}:\d{2})\s*[-–—|:]\s*(.+?)(?=\n|$)',
        # "00:00:00 Título" (sem separador)
        r'(\d{1,2}:\d{2}:\d{2})\s+([A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][^\n]+?)(?=\n|$)',
        # "00:00 Título" (sem separador)
        r'(\d{1,2}:\d{2})\s+([A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][^\n]+?)(?=\n|$)',
        # "[00:00:00] Título"
        r'\[(\d{1,2}:\d{2}:\d{2})\]\s*(.+?)(?=\n|$)',
        # "[00:00] Título"
        r'\[(\d{1,2}:\d{2})\]\s*(.+?)(?=\n|$)',
    ]

    found_timestamps = set()

    for pattern in patterns:
        matches = re.finditer(pattern, description, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            timestamp_str = match.group(1)
            title = match.group(2).strip()

            # Limpar título
            title = re.sub(r'\s+', ' ', title)  # Normalizar espaços
            title = title.rstrip('.')  # Remover ponto final

            # Evitar duplicados
            time_seconds = parse_timestamp(timestamp_str)
            if time_seconds in found_timestamps:
                continue
            found_timestamps.add(time_seconds)

            # Ignorar timestamps que parecem ser outras coisas
            if len(title) < 3 or title.isdigit():
                continue

            chapter = DescriptionChapter(
                title=title,
                start_time=time_seconds,
                raw_timestamp=timestamp_str
            )
            chapters.append(chapter)

    # Ordenar por tempo
    chapters.sort(key=lambda c: c.start_time)

    # Calcular end_time para cada capítulo
    for i, chapter in enumerate(chapters):
        if i < len(chapters) - 1:
            chapter.end_time = chapters[i + 1].start_time
        elif video_duration:
            chapter.end_time = video_duration

    logger.info(f"Extracted {len(chapters)} chapters from description")

    return chapters


def find_cronologia_section(description: str) -> Optional[str]:
    """
    Tenta encontrar a secção de cronologia na descrição.

    Procura por headers como:
    - "CRONOLOGIA"
    - "ÍNDICE"
    - "TIMESTAMPS"
    - "TEMAS"
    - "CAPÍTULOS"
    """
    headers = [
        r'(?:CRONOLOGIA|ÍNDICE|INDEX|TIMESTAMPS?|TEMAS?|CAPÍTULOS?|CHAPTERS?|CONTEÚDO|CONTENTS?)[\s:]*\n',
    ]

    for header_pattern in headers:
        match = re.search(header_pattern, description, re.IGNORECASE)
        if match:
            # Extrair texto após o header até próxima secção ou fim
            start = match.end()
            # Procurar fim da secção (linha em branco dupla ou outro header)
            end_match = re.search(r'\n\n[A-Z]{3,}|\n\n\n', description[start:])
            if end_match:
                return description[start:start + end_match.start()]
            return description[start:]

    return None


def extract_chapters_smart(description: str, video_duration: float = None) -> list[DescriptionChapter]:
    """
    Extração inteligente de capítulos.

    1. Tenta encontrar secção de cronologia
    2. Se não encontrar, procura em toda a descrição
    3. Filtra resultados improváveis
    """
    # Primeiro tentar encontrar secção específica
    cronologia = find_cronologia_section(description)

    if cronologia:
        logger.info("Found CRONOLOGIA section in description")
        chapters = parse_description_chapters(cronologia, video_duration)
        if chapters:
            return chapters

    # Fallback: procurar em toda a descrição
    chapters = parse_description_chapters(description, video_duration)

    # Filtrar se tivermos poucos capítulos (podem ser timestamps aleatórios)
    if len(chapters) < 3:
        logger.warning("Few chapters found, might be false positives")

    return chapters


def format_chapter_duration(chapter: DescriptionChapter) -> str:
    """Formata duração do capítulo."""
    if not chapter.end_time:
        return "?"

    duration = chapter.end_time - chapter.start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)

    if minutes > 0:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


# Teste
if __name__ == "__main__":
    test_description = """
    Mais um episódio do Despolariza!

    CRONOLOGIA:
    00:00:00 - Introdução
    00:05:30 - Imigração em Portugal
    00:25:00 - A Nova Esquerda
    00:45:15 - O PREC e a Revolução
    01:10:00 - Descolonização
    01:35:30 - Habitação e Crise
    02:00:00 - 25 de Abril, 50 anos depois
    02:30:00 - Conclusões

    Segue-nos nas redes sociais!
    """

    chapters = extract_chapters_smart(test_description, video_duration=9786)

    print(f"\nEncontrados {len(chapters)} capítulos:\n")
    for ch in chapters:
        duration = format_chapter_duration(ch)
        print(f"  [{ch.raw_timestamp}] {ch.title} ({duration})")
