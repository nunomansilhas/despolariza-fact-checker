"""Agente de análise retórica usando Claude."""

import asyncio
import json
import re
from typing import Optional
from uuid import uuid4
import logging

from anthropic import AsyncAnthropic

from .base import BaseAgent
from ..models.transcript import TranscriptChunk
from ..models.analysis import (
    RhetoricTechnique,
    RhetoricAnalysis,
    LanguagePatterns,
    TechniqueType,
    Severity,
)
from ..config import settings

logger = logging.getLogger(__name__)

RHETORIC_ANALYSIS_PROMPT = """Analisa o seguinte excerto de um podcast português quanto a técnicas retóricas e padrões de linguagem.

Texto a analisar:
---
{text}
---

IDENTIFICA:

1. **Técnicas Retóricas** usadas (se houver):
   - appeal_to_emotion: Usar emoções em vez de dados
   - appeal_to_authority: "Os especialistas dizem..." sem citar quem
   - false_dichotomy: Apresentar só 2 opções quando há mais
   - strawman: Distorcer argumento do oponente
   - whataboutism: "E o outro lado que fez X?"
   - ad_hominem: Atacar a pessoa em vez do argumento
   - generalization: "Toda a gente sabe...", "É óbvio que..."
   - cherry_picking: Selecionar só dados favoráveis
   - gish_gallop: Muitos argumentos fracos de uma vez
   - moving_goalposts: Mudar critérios quando refutado
   - repetition: Repetir mensagens-chave

2. **Padrões de Linguagem**:
   - Palavras hedging: "talvez", "possivelmente", "acho que"
   - Linguagem assertiva: afirmações absolutas
   - Vocabulário emocional: palavras carregadas
   - Números vagos vs precisos

3. **Tom geral**: defensivo, agressivo, calmo, pedagógico, condescendente, etc.

Responde em JSON:
```json
{{
  "techniques": [
    {{
      "type": "tipo_da_tecnica",
      "quote": "citação exacta do texto",
      "severity": "low|medium|high",
      "explanation": "breve explicação"
    }}
  ],
  "language_patterns": {{
    "hedging_count": 0,
    "assertive_count": 0,
    "emotional_words": ["palavra1", "palavra2"],
    "vague_numbers": ["milhares", "muitos"],
    "precise_numbers": ["2.5 milhões", "45%"],
    "repeated_phrases": ["frase repetida"]
  }},
  "tone": "descrição do tom",
  "notable_moments": ["momento 1", "momento 2"]
}}
```

Se não encontrares técnicas retóricas problemáticas, responde com {{"techniques": [], ...}}.
Sê objectivo e descritivo, não prescritivo.
"""


class RhetoricAnalyzerAgent(BaseAgent):
    """Agente que analisa retórica e padrões de comunicação."""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("rhetoric_analyzer")
        self._api_key = api_key or settings.anthropic_api_key
        self._client: Optional[AsyncAnthropic] = None

    async def _get_client(self) -> AsyncAnthropic:
        """Obtém ou cria cliente Anthropic."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def process(self, item: TranscriptChunk) -> RhetoricAnalysis:
        """
        Processa um chunk de transcrição.

        Args:
            item: TranscriptChunk com texto a analisar

        Returns:
            RhetoricAnalysis com técnicas identificadas
        """
        if not item.text.strip():
            return RhetoricAnalysis(
                chunk_id=item.chunk_id,
                start_time=item.start_time,
                end_time=item.end_time
            )

        try:
            client = await self._get_client()

            prompt = RHETORIC_ANALYSIS_PROMPT.format(text=item.text)

            response = await client.messages.create(
                model=settings.anthropic_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)

            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(content)

            # Processar técnicas
            techniques = []
            for tech_data in data.get("techniques", []):
                try:
                    # Mapear tipo
                    tech_type = self._map_technique_type(tech_data.get("type", ""))
                    if tech_type is None:
                        continue

                    # Mapear severidade
                    severity_map = {
                        "low": Severity.LOW,
                        "medium": Severity.MEDIUM,
                        "high": Severity.HIGH,
                    }
                    severity = severity_map.get(
                        tech_data.get("severity", "low").lower(),
                        Severity.LOW
                    )

                    # Estimar timestamp (meio do chunk por defeito)
                    timestamp = item.start_time + (item.duration / 2)

                    technique = RhetoricTechnique(
                        id=str(uuid4()),
                        type=tech_type,
                        quote=tech_data.get("quote", ""),
                        timestamp=timestamp,
                        severity=severity,
                        explanation=tech_data.get("explanation"),
                        chunk_id=item.chunk_id,
                    )
                    techniques.append(technique)

                except Exception as e:
                    logger.warning(f"Error parsing technique: {e}")
                    continue

            # Processar padrões de linguagem
            patterns_data = data.get("language_patterns", {})
            patterns = LanguagePatterns(
                hedging_count=patterns_data.get("hedging_count", 0),
                assertive_count=patterns_data.get("assertive_count", 0),
                emotional_words=patterns_data.get("emotional_words", []),
                vague_numbers=patterns_data.get("vague_numbers", []),
                precise_numbers=patterns_data.get("precise_numbers", []),
                repeated_phrases=patterns_data.get("repeated_phrases", []),
            )

            analysis = RhetoricAnalysis(
                chunk_id=item.chunk_id,
                start_time=item.start_time,
                end_time=item.end_time,
                techniques=techniques,
                language_patterns=patterns,
                tone=data.get("tone"),
            )

            logger.info(
                f"Analyzed chunk {item.chunk_id}: "
                f"{len(techniques)} techniques, tone: {analysis.tone}"
            )

            return analysis

        except Exception as e:
            logger.error(f"Error in rhetoric analysis: {e}")
            return RhetoricAnalysis(
                chunk_id=item.chunk_id,
                start_time=item.start_time,
                end_time=item.end_time
            )

    def _map_technique_type(self, type_str: str) -> Optional[TechniqueType]:
        """Mapeia string para TechniqueType."""
        type_map = {
            "appeal_to_emotion": TechniqueType.APPEAL_TO_EMOTION,
            "appeal_to_authority": TechniqueType.APPEAL_TO_AUTHORITY,
            "false_dichotomy": TechniqueType.FALSE_DICHOTOMY,
            "strawman": TechniqueType.STRAWMAN,
            "whataboutism": TechniqueType.WHATABOUTISM,
            "ad_hominem": TechniqueType.AD_HOMINEM,
            "generalization": TechniqueType.GENERALIZATION,
            "cherry_picking": TechniqueType.CHERRY_PICKING,
            "appeal_to_common_sense": TechniqueType.APPEAL_TO_COMMON_SENSE,
            "gish_gallop": TechniqueType.GISH_GALLOP,
            "moving_goalposts": TechniqueType.MOVING_GOALPOSTS,
            "repetition": TechniqueType.REPETITION,
            "hedging": TechniqueType.HEDGING,
            "assertive_language": TechniqueType.ASSERTIVE_LANGUAGE,
            "emotional_vocabulary": TechniqueType.EMOTIONAL_VOCABULARY,
            "vague_numbers": TechniqueType.VAGUE_NUMBERS,
            "evasion": TechniqueType.EVASION,
            "deflection": TechniqueType.DEFLECTION,
            "interruption": TechniqueType.INTERRUPTION,
            "contradiction": TechniqueType.CONTRADICTION,
        }
        return type_map.get(type_str.lower())


async def test_rhetoric_analyzer():
    """Teste básico do analisador retórico."""
    agent = RhetoricAnalyzerAgent()

    chunk = TranscriptChunk(
        chunk_id=1,
        start_time=0.0,
        end_time=30.0,
        text="""
        É óbvio que toda a gente sabe que a situação está muito mal.
        Os especialistas todos dizem que isto não pode continuar assim.
        Milhares e milhares de pessoas estão a sofrer.
        E o que é que a direita fez quando estava no poder? Nada!
        Portanto, só há duas opções: ou mudamos tudo ou afundamo-nos.
        """,
        language="pt",
        confidence=0.9
    )

    await agent.start()

    agent.on_result(lambda r: print(f"Analysis: {r.technique_count} techniques, tone: {r.tone}"))

    await agent.submit(chunk)
    await asyncio.sleep(15)

    await agent.stop()
    print(f"Stats: {agent.stats}")


if __name__ == "__main__":
    asyncio.run(test_rhetoric_analyzer())
