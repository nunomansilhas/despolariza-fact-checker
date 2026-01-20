"""Agente de fact-checking usando Claude."""

import asyncio
import json
import re
from typing import Optional
from uuid import uuid4
import logging

from anthropic import AsyncAnthropic

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

Responde em JSON com este formato exacto:
```json
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
```

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

Responde em JSON:
```json
{{
  "verdict": "true|partial|false|inconclusive",
  "confidence": 0.0-1.0,
  "explanation": "Explicação detalhada em português",
  "corrected_info": "Informação correta se aplicável, ou null",
  "sources": ["Nome das fontes consultadas"]
}}
```

Sê rigoroso e imparcial. Se não tiveres certeza, marca como inconclusivo.
"""


class FactCheckerAgent(BaseAgent):
    """Agente que verifica factos usando Claude."""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("fact_checker")
        self._api_key = api_key or settings.anthropic_api_key
        self._client: Optional[AsyncAnthropic] = None

    async def _get_client(self) -> AsyncAnthropic:
        """Obtém ou cria cliente Anthropic."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

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
            logger.info(f"No verifiable claims found in chunk {item.chunk_id}")
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
            client = await self._get_client()

            prompt = EXTRACT_CLAIMS_PROMPT.format(text=chunk.text)

            response = await client.messages.create(
                model=settings.anthropic_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            # Extrair JSON da resposta
            content = response.content[0].text
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)

            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Tentar parsear directamente
                data = json.loads(content)

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
                    text=claim_data["text"],
                    timestamp=timestamp,
                    chunk_id=chunk.chunk_id,
                    context=claim_data.get("context"),
                    is_verifiable=True
                )
                claims.append(claim)

            return claims

        except Exception as e:
            logger.error(f"Error extracting claims: {e}")
            return []

    async def _verify_claim(self, claim: Claim) -> FactCheckResult:
        """Verifica uma claim individual."""
        try:
            client = await self._get_client()

            prompt = VERIFY_CLAIM_PROMPT.format(
                claim=claim.text,
                context=claim.context or "Podcast político português"
            )

            response = await client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)

            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(content)

            # Mapear verdict
            verdict_map = {
                "true": Verdict.TRUE,
                "partial": Verdict.PARTIAL,
                "false": Verdict.FALSE,
                "inconclusive": Verdict.INCONCLUSIVE,
            }
            verdict = verdict_map.get(data.get("verdict", "").lower(), Verdict.INCONCLUSIVE)

            result = FactCheckResult(
                claim=claim,
                verdict=verdict,
                confidence=float(data.get("confidence", 0.5)),
                explanation=data.get("explanation", ""),
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
    # Precisa de ANTHROPIC_API_KEY configurada
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

    agent.on_result(lambda r: print(f"Results: {len(r)} fact-checks"))

    await agent.submit(chunk)
    await asyncio.sleep(30)  # Esperar processamento

    await agent.stop()
    print(f"Stats: {agent.stats}")


if __name__ == "__main__":
    asyncio.run(test_fact_checker())
