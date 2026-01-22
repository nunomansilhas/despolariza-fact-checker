"""Agente de fact-checking usando Ollama (local) ou Claude (API)."""

import asyncio
import json
import re
import httpx
from typing import Optional
from uuid import uuid4
import logging

from .base import BaseAgent
from ..models.transcript import TranscriptChunk
from ..models.claim import Claim, FactCheckResult, Verdict
from ..config import settings

logger = logging.getLogger(__name__)

# Prompt para extração de claims
EXTRACT_CLAIMS_PROMPT = """Analisa o seguinte texto de um podcast português e identifica APENAS afirmações factuais verificáveis.

NÃO incluas:
- Opiniões pessoais
- Especulações
- Perguntas
- Afirmações vagas sem dados concretos

INCLUI:
- Estatísticas citadas
- Datas e eventos históricos
- Citações de estudos ou fontes
- Afirmações sobre leis ou políticas
- Factos sobre pessoas ou organizações

Texto a analisar:
---
{text}
---

Responde APENAS em JSON válido com este formato exacto (sem texto adicional):
{{
  "claims": [
    {{
      "text": "A afirmação exacta ou paráfrase fiel",
      "is_verifiable": true,
      "timestamp_hint": "início/meio/fim do texto",
      "context": "Breve contexto se necessário"
    }}
  ]
}}

Se não houver afirmações verificáveis, responde com {{"claims": []}}
"""

# Prompt para verificação
VERIFY_CLAIM_PROMPT = """És um fact-checker imparcial. Verifica a seguinte afirmação:

AFIRMAÇÃO: "{claim}"
CONTEXTO: {context}

Pesquisa nas tuas fontes de conhecimento e avalia:
1. Se é VERDADEIRO - a afirmação corresponde aos factos conhecidos
2. Se é PARCIALMENTE VERDADEIRO - parcialmente correto mas com imprecisões
3. Se é FALSO - a afirmação contradiz os factos conhecidos
4. Se é INCONCLUSIVO - não há informação suficiente para verificar

Responde APENAS em JSON válido (sem texto adicional):
{{
  "verdict": "true|partial|false|inconclusive",
  "confidence": 0.7,
  "explanation": "Explicação detalhada em português",
  "corrected_info": "Informação correta se aplicável, ou null",
  "sources": ["Nome das fontes consultadas"]
}}

Sê rigoroso e imparcial. Se não tiveres certeza, marca como inconclusivo.
"""


class OllamaClient:
    """Cliente simples para Ollama API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url
        self.model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: str) -> str:
        """Gera resposta do modelo."""
        try:
            response = await self._client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # Mais determinístico para fact-checking
                        "num_predict": 2000,
                    }
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise

    async def close(self):
        await self._client.aclose()


class FactCheckerAgent(BaseAgent):
    """Agente que verifica factos usando Ollama (local) ou Claude (API)."""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("fact_checker")
        self._api_key = api_key or settings.anthropic_api_key
        self._ollama_client: Optional[OllamaClient] = None
        self._anthropic_client = None

    async def start(self):
        """Inicia o agente."""
        await super().start()

        if settings.ollama_enabled:
            self._ollama_client = OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model
            )
            logger.info(f"Fact-checker using Ollama ({settings.ollama_model})")
        else:
            logger.info("Fact-checker using Anthropic Claude")

    async def stop(self):
        """Para o agente."""
        if self._ollama_client:
            await self._ollama_client.close()
        await super().stop()

    async def _generate(self, prompt: str) -> str:
        """Gera resposta usando Ollama ou Anthropic."""
        if settings.ollama_enabled and self._ollama_client:
            return await self._ollama_client.generate(prompt)
        else:
            # Fallback para Anthropic
            if not self._anthropic_client:
                from anthropic import AsyncAnthropic
                if not self._api_key:
                    raise ValueError("ANTHROPIC_API_KEY not configured")
                self._anthropic_client = AsyncAnthropic(api_key=self._api_key)

            response = await self._anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text

    def _extract_json(self, text: str) -> dict:
        """Extrai JSON da resposta (com ou sem markdown)."""
        # Tentar extrair de bloco markdown
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)

        # Limpar e parsear
        text = text.strip()

        # Encontrar o início do JSON
        start = text.find('{')
        if start == -1:
            return {"claims": []}

        # Encontrar o fim do JSON (último })
        end = text.rfind('}')
        if end == -1:
            return {"claims": []}

        json_str = text[start:end+1]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            logger.debug(f"Attempted to parse: {json_str[:200]}...")
            return {"claims": []}

    async def process(self, item: TranscriptChunk) -> list[FactCheckResult]:
        """
        Processa um chunk de transcrição.

        Args:
            item: TranscriptChunk com texto a verificar

        Returns:
            Lista de FactCheckResult
        """
        if not item.text.strip():
            return []

        # 1. Extrair claims do texto
        claims = await self._extract_claims(item)

        if not claims:
            logger.debug(f"No verifiable claims found in chunk {item.chunk_id}")
            return []

        logger.info(f"Found {len(claims)} claims in chunk {item.chunk_id}")

        # 2. Verificar cada claim
        results = []
        for claim in claims:
            try:
                result = await self._verify_claim(claim)
                results.append(result)
            except Exception as e:
                logger.error(f"Error verifying claim: {e}")
                # Criar resultado com erro
                results.append(FactCheckResult(
                    claim=claim,
                    verdict=Verdict.INCONCLUSIVE,
                    explanation=f"Erro na verificação: {str(e)}",
                    confidence=0.0
                ))

        return results

    async def _extract_claims(self, chunk: TranscriptChunk) -> list[Claim]:
        """Extrai claims verificáveis do texto."""
        try:
            prompt = EXTRACT_CLAIMS_PROMPT.format(text=chunk.text)
            response = await self._generate(prompt)
            data = self._extract_json(response)

            claims = []
            for i, claim_data in enumerate(data.get("claims", [])):
                if not claim_data.get("is_verifiable", True):
                    continue

                # Estimar timestamp baseado na posição
                position = claim_data.get("timestamp_hint", "meio")
                if position == "início":
                    timestamp = chunk.start_time + (chunk.duration * 0.1)
                elif position == "fim":
                    timestamp = chunk.start_time + (chunk.duration * 0.9)
                else:
                    timestamp = chunk.start_time + (chunk.duration * 0.5)

                claim = Claim(
                    id=str(uuid4()),
                    text=claim_data.get("text", ""),
                    timestamp=timestamp,
                    chunk_id=chunk.chunk_id,
                    context=claim_data.get("context"),
                    is_verifiable=True
                )
                if claim.text:  # Só adicionar se tiver texto
                    claims.append(claim)

            return claims

        except Exception as e:
            logger.error(f"Error extracting claims: {e}")
            return []

    async def _verify_claim(self, claim: Claim) -> FactCheckResult:
        """Verifica uma claim individual."""
        try:
            prompt = VERIFY_CLAIM_PROMPT.format(
                claim=claim.text,
                context=claim.context or "Podcast político português"
            )

            response = await self._generate(prompt)
            data = self._extract_json(response)

            # Mapear verdict
            verdict_map = {
                "true": Verdict.TRUE,
                "verdadeiro": Verdict.TRUE,
                "partial": Verdict.PARTIAL,
                "parcial": Verdict.PARTIAL,
                "parcialmente": Verdict.PARTIAL,
                "false": Verdict.FALSE,
                "falso": Verdict.FALSE,
                "inconclusive": Verdict.INCONCLUSIVE,
                "inconclusivo": Verdict.INCONCLUSIVE,
            }
            verdict_str = str(data.get("verdict", "inconclusive")).lower().strip()
            verdict = verdict_map.get(verdict_str, Verdict.INCONCLUSIVE)

            result = FactCheckResult(
                claim=claim,
                verdict=verdict,
                confidence=float(data.get("confidence", 0.5)),
                explanation=data.get("explanation", "Sem explicação disponível"),
                sources=data.get("sources", []),
                corrected_info=data.get("corrected_info"),
            )

            logger.info(f"Verified claim: {verdict.emoji} {claim.text[:50]}...")

            return result

        except Exception as e:
            logger.error(f"Error in verification: {e}")
            raise

    async def verify_single_claim(self, text: str, context: str = "") -> FactCheckResult:
        """Método de conveniência para verificar uma única claim."""
        claim = Claim(
            id=str(uuid4()),
            text=text,
            timestamp=0.0,
            chunk_id=0,
            context=context,
            is_verifiable=True
        )
        return await self._verify_claim(claim)


async def test_fact_checker():
    """Teste básico do fact-checker."""
    agent = FactCheckerAgent()

    chunk = TranscriptChunk(
        chunk_id=1,
        start_time=0.0,
        end_time=30.0,
        text="Portugal recebe mais de 100 mil imigrantes por ano. "
             "O PIB português cresceu 2% em 2024. "
             "A descolonização portuguesa foi completada em 1975.",
        language="pt",
        confidence=0.9
    )

    await agent.start()

    results = await agent.process(chunk)
    for r in results:
        print(f"{r.verdict.emoji} {r.claim.text}")
        print(f"   → {r.explanation}")
        print()

    await agent.stop()
    print(f"Stats: {agent.stats}")


if __name__ == "__main__":
    asyncio.run(test_fact_checker())
