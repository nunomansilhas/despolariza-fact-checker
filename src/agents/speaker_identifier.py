"""Agente de identificação de speakers usando LLM."""

import asyncio
import json
import logging
import re
from typing import Optional
import httpx

from .base import BaseAgent
from ..config import settings

logger = logging.getLogger(__name__)


class SpeakerIdentifierAgent(BaseAgent):
    """Agente que identifica speakers usando LLM baseado no contexto."""

    def __init__(self):
        super().__init__("speaker_identifier")
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        await super().start()
        self._client = httpx.AsyncClient(timeout=120.0)

    async def stop(self):
        if self._client:
            await self._client.aclose()
        await super().stop()

    async def process(self, item: dict) -> list[dict]:
        """Processa um item (transcript) e identifica speakers."""
        transcript_text = item.get("text", "")
        speaker_names = item.get("speaker_names", ["Entrevistador", "Convidado"])
        context = item.get("context", "")
        return await self.identify_speakers(transcript_text, speaker_names, context)

    async def identify_speakers(
        self,
        transcript_text: str,
        speaker_names: list[str],
        context: str = ""
    ) -> list[dict]:
        """
        Identifica quem disse o quê no transcript.

        Args:
            transcript_text: Texto da transcrição (sem speaker labels)
            speaker_names: Lista de nomes dos speakers (ex: ["Daniel Oliveira", "Convidado"])
            context: Contexto adicional (ex: título do vídeo, descrição)

        Returns:
            Lista de segmentos com speaker identificado:
            [{"text": "...", "speaker": "Daniel Oliveira"}, ...]
        """
        if not settings.ollama_enabled:
            logger.warning("Ollama not enabled")
            return []

        # Preparar prompt
        speakers_str = ", ".join(speaker_names)

        prompt = f"""Analisa esta transcrição de um podcast/entrevista e identifica quem está a falar em cada parte.

SPEAKERS POSSÍVEIS: {speakers_str}

CONTEXTO: {context}

INSTRUÇÕES:
1. Identifica quem está a falar baseado no contexto:
   - O entrevistador/host normalmente faz perguntas curtas e diretas
   - O convidado normalmente dá respostas longas e opiniões detalhadas
   - Presta atenção a nomes mencionados, pronomes, e referências
   - Se estiverem a falar ao mesmo tempo ou houver interjeições curtas, usa "AMBOS" como speaker
2. Divide o texto em partes, atribuindo cada parte ao speaker correto
3. Segmentos muito curtos (1-2 palavras) como "sim", "pois", "exato" podem ser do speaker que está a ouvir
4. Responde APENAS em JSON válido, sem markdown

FORMATO DE RESPOSTA (JSON array):
[
  {{"speaker": "Nome do Speaker", "text": "O que ele disse..."}},
  {{"speaker": "Outro Speaker", "text": "O que ele disse..."}},
  {{"speaker": "AMBOS", "text": "Quando falam ao mesmo tempo..."}}
]

TRANSCRIÇÃO:
{transcript_text[:8000]}

RESPOSTA JSON:"""

        try:
            response = await self._client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 4000
                    }
                }
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return []

            result = response.json()
            text = result.get("response", "")

            # Tentar extrair JSON da resposta
            segments = self._parse_json_response(text)

            if segments:
                logger.info(f"Identified {len(segments)} speaker segments")
                return segments
            else:
                logger.warning("Could not parse speaker segments from response")
                return []

        except Exception as e:
            logger.error(f"Speaker identification error: {e}")
            return []

    def _parse_json_response(self, text: str) -> list[dict]:
        """Extrai JSON da resposta do LLM."""
        # Tentar parse direto
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Tentar encontrar array JSON na resposta
        json_match = re.search(r'\[[\s\S]*\]', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Tentar limpar e fazer parse
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return []

    async def process_chapter(
        self,
        chapter_text: str,
        speaker_names: list[str],
        chapter_title: str = ""
    ) -> list[dict]:
        """
        Processa um capítulo e identifica speakers.

        Args:
            chapter_text: Texto do capítulo
            speaker_names: Nomes dos speakers
            chapter_title: Título do capítulo para contexto

        Returns:
            Segmentos com speakers identificados
        """
        context = f"Capítulo: {chapter_title}" if chapter_title else ""
        return await self.identify_speakers(chapter_text, speaker_names, context)


async def test_speaker_identifier():
    """Teste básico do identificador."""
    agent = SpeakerIdentifierAgent()
    await agent.start()

    test_transcript = """
    Bem-vindos ao programa. Hoje temos um convidado muito especial.
    Obrigado pelo convite, é um prazer estar aqui.
    Então, conte-nos sobre o seu novo livro.
    O livro fala sobre a história de Portugal no século XX,
    especialmente sobre o período da ditadura.
    Muito interessante. E o que o motivou a escrever sobre este tema?
    """

    segments = await agent.identify_speakers(
        test_transcript,
        ["Entrevistador", "Autor"],
        "Programa de entrevistas sobre livros"
    )

    for seg in segments:
        print(f"[{seg['speaker']}]: {seg['text'][:50]}...")

    await agent.stop()


if __name__ == "__main__":
    asyncio.run(test_speaker_identifier())
