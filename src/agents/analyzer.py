"""Agente de análise - resume capítulos e extrai conceitos."""

import asyncio
import json
import re
import httpx
from typing import Optional
from dataclasses import dataclass
import logging

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChapterInsights:
    """Insights extraídos de um capítulo pelo LLM."""
    chapter_id: str
    chapter_title: str
    summary: str
    key_topics: list[str]
    key_claims: list[str]  # Afirmações que podem ser verificadas
    speakers_mentioned: list[str]
    sentiment: str  # positive, negative, neutral, mixed


class OllamaClient:
    """Cliente para Ollama API."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self._client = httpx.AsyncClient(timeout=300.0)  # 5min timeout para modelos grandes

    async def generate(self, prompt: str) -> str:
        try:
            response = await self._client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 4000,
                    }
                }
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise

    async def close(self):
        await self._client.aclose()


ANALYSIS_PROMPT = """Analisa o seguinte excerto de um podcast português.

CAPÍTULO: {chapter_title}
TEXTO:
---
{text}
---

Responde APENAS em JSON válido com este formato:
{{
  "resumo": "Resumo de 2-3 frases do que foi discutido",
  "topicos": ["Tópico 1", "Tópico 2", "Tópico 3"],
  "afirmacoes_verificaveis": [
    "Afirmação factual 1 que pode ser verificada",
    "Afirmação factual 2 que pode ser verificada"
  ],
  "pessoas_mencionadas": ["Nome 1", "Nome 2"],
  "tom": "positivo|negativo|neutro|misto"
}}

Se não houver afirmações verificáveis, deixa a lista vazia.
Foca-te em factos concretos, não opiniões.
"""


class AnalyzerAgent:
    """Agente que analisa transcrições e extrai insights."""

    def __init__(self):
        self._client: Optional[OllamaClient] = None

    async def start(self):
        if settings.ollama_enabled:
            self._client = OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model
            )
            logger.info(f"Analyzer using Ollama ({settings.ollama_model})")

    async def stop(self):
        if self._client:
            await self._client.close()

    def _extract_json(self, text: str) -> dict:
        """Extrai JSON da resposta."""
        # Tentar extrair de bloco markdown
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            text = match.group(1)

        text = text.strip()
        start = text.find('{')
        end = text.rfind('}')

        if start == -1 or end == -1:
            return {}

        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return {}

    async def analyze_chapter(self, chapter_id: str, chapter_title: str, text: str) -> ChapterInsights:
        """Analisa um capítulo e extrai insights."""
        if not self._client:
            raise RuntimeError("Analyzer not started")

        if not text.strip():
            return ChapterInsights(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                summary="Sem conteúdo para analisar.",
                key_topics=[],
                key_claims=[],
                speakers_mentioned=[],
                sentiment="neutral"
            )

        # Limitar texto a ~4000 palavras para não exceder contexto
        words = text.split()
        if len(words) > 4000:
            text = ' '.join(words[:4000]) + "..."

        prompt = ANALYSIS_PROMPT.format(
            chapter_title=chapter_title,
            text=text
        )

        logger.info(f"Analyzing chapter: {chapter_title}")
        response = await self._client.generate(prompt)
        data = self._extract_json(response)

        analysis = ChapterInsights(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            summary=data.get("resumo", "Não foi possível gerar resumo."),
            key_topics=data.get("topicos", []),
            key_claims=data.get("afirmacoes_verificaveis", []),
            speakers_mentioned=data.get("pessoas_mencionadas", []),
            sentiment=data.get("tom", "neutral")
        )

        logger.info(f"Analysis complete: {len(analysis.key_topics)} topics, {len(analysis.key_claims)} claims")
        return analysis

    async def _analyze_single_chapter(self, i: int, chapter: dict, chapters: list[dict],
                                       transcripts: list[dict]) -> ChapterInsights:
        """Analisa um único capítulo (para uso em paralelo)."""
        ch_start = chapter.get("start_time", 0)
        ch_end = chapter.get("end_time") or (chapters[i+1]["start_time"] if i < len(chapters)-1 else float('inf'))

        chapter_text = ' '.join(
            t.get("text", "") for t in transcripts
            if t.get("start_time", 0) >= ch_start and t.get("start_time", 0) < ch_end
        )

        try:
            return await self.analyze_chapter(
                chapter_id=chapter.get("id", f"ch_{i}"),
                chapter_title=chapter.get("title", f"Capítulo {i+1}"),
                text=chapter_text
            )
        except Exception as e:
            logger.error(f"Error analyzing chapter {chapter.get('title')}: {e}")
            return ChapterInsights(
                chapter_id=chapter.get("id", f"ch_{i}"),
                chapter_title=chapter.get("title", f"Capítulo {i+1}"),
                summary=f"Erro na análise: {str(e)}",
                key_topics=[],
                key_claims=[],
                speakers_mentioned=[],
                sentiment="neutral"
            )

    async def analyze_all_chapters(self, chapters: list[dict], transcripts: list[dict],
                                    on_progress=None, max_concurrent: int = 2) -> list[ChapterInsights]:
        """Analisa todos os capítulos (em paralelo com limite de concorrência)."""
        semaphore = asyncio.Semaphore(max_concurrent)
        results = [None] * len(chapters)
        completed = [0]  # Usar lista para permitir modificação em closure

        async def analyze_with_semaphore(i: int, chapter: dict):
            async with semaphore:
                logger.info(f"Starting analysis {i+1}/{len(chapters)}: {chapter.get('title')}")
                result = await self._analyze_single_chapter(i, chapter, chapters, transcripts)
                results[i] = result
                completed[0] += 1

                if on_progress:
                    await on_progress(completed[0], len(chapters), result)

                return result

        # Lançar todas as tarefas em paralelo (semaphore controla concorrência)
        tasks = [
            analyze_with_semaphore(i, chapter)
            for i, chapter in enumerate(chapters)
        ]

        await asyncio.gather(*tasks)

        return results
