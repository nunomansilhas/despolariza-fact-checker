"""Agente Polígrafo - Análise completa de transcrição com fact-checking."""

import asyncio
import json
import logging
import re
from typing import Optional
from dataclasses import dataclass
import httpx

from .base import BaseAgent
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class Claim:
    """Uma afirmação factual extraída."""
    text: str
    speaker: str
    chapter: str
    timestamp: Optional[float] = None


@dataclass
class ClaimVerdict:
    """Veredicto de uma afirmação."""
    claim: Claim
    verdict: str  # VERDADEIRO, FALSO, PARCIALMENTE_VERDADEIRO, NAO_VERIFICAVEL
    explanation: str
    correction: Optional[str] = None
    sources: list[str] = None
    confidence: float = 0.0


class PoligrafoAgent(BaseAgent):
    """
    Agente que faz análise completa de uma transcrição:
    1. Separa por speaker
    2. Extrai claims factuais
    3. Verifica cada claim
    """

    def __init__(self):
        super().__init__("poligrafo")
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        await super().start()
        self._client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout

    async def stop(self):
        if self._client:
            await self._client.aclose()
        await super().stop()

    async def process(self, item: dict) -> dict:
        """Processa transcrição completa."""
        transcript = item.get("transcript", "")
        chapters = item.get("chapters", [])
        speaker_names = item.get("speaker_names", ["Entrevistador", "Convidado"])

        result = await self.analyze_full(transcript, chapters, speaker_names)
        return result

    async def _call_ollama(self, prompt: str, temperature: float = 0.3) -> str:
        """Faz chamada ao Ollama."""
        try:
            response = await self._client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 8000
                    }
                }
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return ""

            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Ollama call error: {e}")
            return ""

    def _parse_json(self, text: str) -> list | dict | None:
        """Extrai JSON da resposta."""
        # Tentar parse direto
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Procurar array ou objeto JSON
        json_match = re.search(r'[\[{][\s\S]*[\]}]', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Limpar markdown
        text = text.strip()
        for prefix in ["```json", "```"]:
            if text.startswith(prefix):
                text = text[len(prefix):]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    async def separate_speakers(
        self,
        transcript: str,
        chapters: list[dict],
        speaker_names: list[str]
    ) -> list[dict]:
        """
        Separa a transcrição por speaker.

        Returns:
            Lista de segmentos: [{"speaker": "Nome", "text": "...", "chapter": "..."}]
        """
        speakers_str = ", ".join(speaker_names)

        # Preparar contexto dos capítulos
        chapters_context = "\n".join([
            f"- {ch.get('title', 'Capítulo')} ({ch.get('start_time', 0):.0f}s - {ch.get('end_time', 0):.0f}s)"
            for ch in chapters[:10]  # Primeiros 10 para contexto
        ])

        prompt = f"""Analisa esta transcrição de podcast e separa por speaker.

SPEAKERS: {speakers_str}

CAPÍTULOS:
{chapters_context}

REGRAS:
1. O entrevistador/host faz perguntas curtas e dirige a conversa
2. O convidado dá respostas longas e opiniões detalhadas
3. Identifica mudanças de speaker por:
   - Perguntas vs respostas
   - Mudança de tom/assunto
   - Frases como "sim", "pois", "exato" são do ouvinte
4. Se falarem ao mesmo tempo: speaker = "AMBOS"

FORMATO DE RESPOSTA (JSON array):
[
  {{"speaker": "Nome", "text": "O que disse...", "chapter": "Título do capítulo"}},
  ...
]

TRANSCRIÇÃO:
{transcript[:15000]}

RESPOSTA JSON:"""

        response = await self._call_ollama(prompt)
        segments = self._parse_json(response)

        if isinstance(segments, list):
            logger.info(f"Separated into {len(segments)} speaker segments")
            return segments

        logger.warning("Could not parse speaker segments")
        return []

    async def extract_claims(
        self,
        separated_transcript: list[dict],
        speaker_names: list[str]
    ) -> list[dict]:
        """
        Extrai afirmações factuais verificáveis.

        Returns:
            Lista de claims: [{"text": "...", "speaker": "...", "chapter": "..."}]
        """
        # Formatar transcript para análise
        formatted = "\n".join([
            f"[{seg.get('speaker', '?')}] ({seg.get('chapter', '')}): {seg.get('text', '')}"
            for seg in separated_transcript[:50]  # Limitar para não exceder contexto
        ])

        prompt = f"""Analisa esta transcrição e extrai APENAS afirmações FACTUAIS VERIFICÁVEIS.

IMPORTANTE - Extrai apenas afirmações que:
1. Contêm dados, números, datas, estatísticas
2. Referem eventos históricos específicos
3. Citam leis, políticas, decisões
4. Fazem comparações quantificáveis
5. São verificáveis com fontes públicas

NÃO extrair:
- Opiniões pessoais
- Especulações sobre o futuro
- Generalidades vagas
- Perguntas

TRANSCRIÇÃO:
{formatted}

FORMATO DE RESPOSTA (JSON array):
[
  {{"claim": "Afirmação exacta...", "speaker": "Nome de quem disse", "chapter": "Capítulo", "context": "Contexto breve"}},
  ...
]

Extrai entre 10 a 30 claims mais importantes.

RESPOSTA JSON:"""

        response = await self._call_ollama(prompt)
        claims = self._parse_json(response)

        if isinstance(claims, list):
            logger.info(f"Extracted {len(claims)} claims")
            return claims

        logger.warning("Could not parse claims")
        return []

    async def verify_claim(self, claim: dict) -> dict:
        """
        Verifica uma afirmação.

        Returns:
            Veredicto: {"claim": ..., "verdict": ..., "explanation": ..., "correction": ...}
        """
        claim_text = claim.get("claim", claim.get("text", ""))
        speaker = claim.get("speaker", "?")
        context = claim.get("context", "")

        prompt = f"""Verifica se esta afirmação é verdadeira ou falsa.

AFIRMAÇÃO: "{claim_text}"
DITO POR: {speaker}
CONTEXTO: {context}

Analisa a afirmação e determina:
1. Se é VERDADEIRO, FALSO, PARCIALMENTE_VERDADEIRO, ou NAO_VERIFICAVEL
2. Explica o porquê
3. Se falso ou parcialmente verdadeiro, indica a correção
4. Indica o nível de confiança (0-100%)

IMPORTANTE: Baseia-te em conhecimento factual. Se não tiveres certeza, marca como NAO_VERIFICAVEL.

FORMATO DE RESPOSTA (JSON):
{{
  "verdict": "VERDADEIRO|FALSO|PARCIALMENTE_VERDADEIRO|NAO_VERIFICAVEL",
  "explanation": "Explicação detalhada...",
  "correction": "Correção se aplicável ou null",
  "confidence": 85,
  "sources": ["Fonte 1", "Fonte 2"]
}}

RESPOSTA JSON:"""

        response = await self._call_ollama(prompt, temperature=0.2)
        result = self._parse_json(response)

        if isinstance(result, dict):
            return {
                "claim": claim_text,
                "speaker": speaker,
                "chapter": claim.get("chapter", ""),
                "context": context,
                "verdict": result.get("verdict", "NAO_VERIFICAVEL"),
                "explanation": result.get("explanation", ""),
                "correction": result.get("correction"),
                "confidence": result.get("confidence", 0),
                "sources": result.get("sources", [])
            }

        return {
            "claim": claim_text,
            "speaker": speaker,
            "chapter": claim.get("chapter", ""),
            "verdict": "NAO_VERIFICAVEL",
            "explanation": "Não foi possível verificar",
            "confidence": 0
        }

    async def analyze_full(
        self,
        transcript: str,
        chapters: list[dict],
        speaker_names: list[str],
        on_progress: callable = None
    ) -> dict:
        """
        Análise completa: separar speakers, extrair claims, verificar.

        Args:
            transcript: Texto completo da transcrição
            chapters: Lista de capítulos
            speaker_names: Nomes dos speakers
            on_progress: Callback para progresso (stage, current, total)

        Returns:
            {
                "separated_transcript": [...],
                "claims": [...],
                "verdicts": [...],
                "summary": {...}
            }
        """
        result = {
            "separated_transcript": [],
            "claims": [],
            "verdicts": [],
            "summary": {}
        }

        # 1. Separar por speaker
        if on_progress:
            on_progress("separating", 0, 3)

        logger.info("Step 1/3: Separating by speaker...")
        result["separated_transcript"] = await self.separate_speakers(
            transcript, chapters, speaker_names
        )

        # 2. Extrair claims
        if on_progress:
            on_progress("extracting", 1, 3)

        logger.info("Step 2/3: Extracting claims...")
        result["claims"] = await self.extract_claims(
            result["separated_transcript"], speaker_names
        )

        # 3. Verificar cada claim
        if on_progress:
            on_progress("verifying", 2, 3)

        logger.info(f"Step 3/3: Verifying {len(result['claims'])} claims...")

        for i, claim in enumerate(result["claims"]):
            if on_progress:
                on_progress("verifying", i, len(result["claims"]))

            verdict = await self.verify_claim(claim)
            result["verdicts"].append(verdict)

            # Pequena pausa entre verificações
            await asyncio.sleep(0.5)

        # Resumo
        verdicts_count = {}
        for v in result["verdicts"]:
            verdict = v.get("verdict", "NAO_VERIFICAVEL")
            verdicts_count[verdict] = verdicts_count.get(verdict, 0) + 1

        result["summary"] = {
            "total_claims": len(result["claims"]),
            "verdicts": verdicts_count,
            "speakers": speaker_names,
            "chapters_analyzed": len(chapters)
        }

        logger.info(f"Analysis complete: {result['summary']}")
        return result


async def test_poligrafo():
    """Teste básico do polígrafo."""
    agent = PoligrafoAgent()
    await agent.start()

    test_transcript = """
    Bem-vindos ao programa. Hoje vamos falar sobre economia portuguesa.
    O PIB de Portugal cresceu 2.3% em 2024, segundo o INE.
    Sim, foi um crescimento acima da média europeia.
    E a inflação? Está em quanto agora?
    A inflação está nos 2.1%, bem abaixo dos 10% que tivemos em 2022.
    Portugal tem cerca de 10 milhões de habitantes.
    Na verdade, segundo os censos de 2021, são 10.3 milhões.
    """

    chapters = [
        {"title": "Introdução", "start_time": 0, "end_time": 60},
        {"title": "Economia", "start_time": 60, "end_time": 180}
    ]

    result = await agent.analyze_full(
        test_transcript,
        chapters,
        ["Entrevistador", "Economista"]
    )

    print("\n=== RESULTADO ===")
    print(f"Segmentos: {len(result['separated_transcript'])}")
    print(f"Claims: {len(result['claims'])}")
    print(f"Veredictos: {result['summary']}")

    for v in result["verdicts"]:
        emoji = {
            "VERDADEIRO": "✅",
            "FALSO": "❌",
            "PARCIALMENTE_VERDADEIRO": "⚠️",
            "NAO_VERIFICAVEL": "❓"
        }.get(v["verdict"], "?")
        print(f"\n{emoji} {v['claim'][:60]}...")
        print(f"   → {v['verdict']}: {v['explanation'][:100]}...")

    await agent.stop()


if __name__ == "__main__":
    asyncio.run(test_poligrafo())
