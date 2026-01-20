"""Modelos de análise retórica e comportamental."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class TechniqueType(str, Enum):
    """Tipos de técnicas retóricas."""

    # Falácias lógicas
    APPEAL_TO_EMOTION = "appeal_to_emotion"
    APPEAL_TO_AUTHORITY = "appeal_to_authority"
    FALSE_DICHOTOMY = "false_dichotomy"
    STRAWMAN = "strawman"
    WHATABOUTISM = "whataboutism"
    AD_HOMINEM = "ad_hominem"

    # Técnicas de persuasão
    GENERALIZATION = "generalization"
    CHERRY_PICKING = "cherry_picking"
    APPEAL_TO_COMMON_SENSE = "appeal_to_common_sense"
    GISH_GALLOP = "gish_gallop"
    MOVING_GOALPOSTS = "moving_goalposts"
    REPETITION = "repetition"

    # Padrões de linguagem
    HEDGING = "hedging"
    ASSERTIVE_LANGUAGE = "assertive_language"
    EMOTIONAL_VOCABULARY = "emotional_vocabulary"
    VAGUE_NUMBERS = "vague_numbers"

    # Comportamento discursivo
    EVASION = "evasion"
    DEFLECTION = "deflection"
    INTERRUPTION = "interruption"
    CONTRADICTION = "contradiction"

    @property
    def label_pt(self) -> str:
        """Nome em português."""
        labels = {
            TechniqueType.APPEAL_TO_EMOTION: "Apelo à Emoção",
            TechniqueType.APPEAL_TO_AUTHORITY: "Apelo à Autoridade",
            TechniqueType.FALSE_DICHOTOMY: "Falsa Dicotomia",
            TechniqueType.STRAWMAN: "Strawman (Espantalho)",
            TechniqueType.WHATABOUTISM: "Whataboutism",
            TechniqueType.AD_HOMINEM: "Ad Hominem",
            TechniqueType.GENERALIZATION: "Generalização",
            TechniqueType.CHERRY_PICKING: "Cherry-picking",
            TechniqueType.APPEAL_TO_COMMON_SENSE: "Apelo ao Senso Comum",
            TechniqueType.GISH_GALLOP: "Gish Gallop",
            TechniqueType.MOVING_GOALPOSTS: "Moving Goalposts",
            TechniqueType.REPETITION: "Repetição",
            TechniqueType.HEDGING: "Linguagem Hedging",
            TechniqueType.ASSERTIVE_LANGUAGE: "Linguagem Assertiva",
            TechniqueType.EMOTIONAL_VOCABULARY: "Vocabulário Emocional",
            TechniqueType.VAGUE_NUMBERS: "Números Vagos",
            TechniqueType.EVASION: "Evasão",
            TechniqueType.DEFLECTION: "Deflexão",
            TechniqueType.INTERRUPTION: "Interrupção",
            TechniqueType.CONTRADICTION: "Contradição",
        }
        return labels.get(self, self.value)

    @property
    def description_pt(self) -> str:
        """Descrição curta em português."""
        descriptions = {
            TechniqueType.APPEAL_TO_EMOTION: "Usar emoções (medo, raiva, empatia) em vez de dados",
            TechniqueType.APPEAL_TO_AUTHORITY: "\"Os especialistas dizem...\" sem citar quem",
            TechniqueType.FALSE_DICHOTOMY: "Apresentar apenas 2 opções quando há mais",
            TechniqueType.STRAWMAN: "Distorcer o argumento do oponente para o atacar",
            TechniqueType.WHATABOUTISM: "Desviar com \"e o outro lado que fez X?\"",
            TechniqueType.AD_HOMINEM: "Atacar a pessoa em vez do argumento",
            TechniqueType.GENERALIZATION: "\"Toda a gente sabe...\", \"É óbvio que...\"",
            TechniqueType.CHERRY_PICKING: "Selecionar só dados que apoiam a narrativa",
            TechniqueType.APPEAL_TO_COMMON_SENSE: "\"É só usar a lógica...\"",
            TechniqueType.GISH_GALLOP: "Bombardear com muitos argumentos fracos",
            TechniqueType.MOVING_GOALPOSTS: "Mudar critérios quando refutado",
            TechniqueType.REPETITION: "Repetir mensagens-chave para persuasão",
            TechniqueType.HEDGING: "\"Talvez\", \"possivelmente\", \"acho que\" - incerteza",
            TechniqueType.ASSERTIVE_LANGUAGE: "Afirmações absolutas sem nuance",
            TechniqueType.EMOTIONAL_VOCABULARY: "Palavras carregadas vs neutras",
            TechniqueType.VAGUE_NUMBERS: "\"Milhões\" vs \"2.3 milhões\" - imprecisão",
            TechniqueType.EVASION: "Evitar responder diretamente",
            TechniqueType.DEFLECTION: "Mudar de assunto quando pressionado",
            TechniqueType.INTERRUPTION: "Interromper o interlocutor",
            TechniqueType.CONTRADICTION: "Inconsistências no discurso",
        }
        return descriptions.get(self, "")


class Severity(str, Enum):
    """Severidade/impacto da técnica."""

    LOW = "low"  # Normal em discurso
    MEDIUM = "medium"  # Notável
    HIGH = "high"  # Problemático


class RhetoricTechnique(BaseModel):
    """Uma técnica retórica identificada."""

    id: str
    type: TechniqueType
    quote: str  # Citação exata
    timestamp: float
    speaker: Optional[str] = None
    severity: Severity = Severity.LOW
    explanation: Optional[str] = None
    chunk_id: int


class LanguagePatterns(BaseModel):
    """Padrões de linguagem detetados num segmento."""

    hedging_count: int = 0
    assertive_count: int = 0
    emotional_words: list[str] = Field(default_factory=list)
    vague_numbers: list[str] = Field(default_factory=list)
    precise_numbers: list[str] = Field(default_factory=list)
    repeated_phrases: list[str] = Field(default_factory=list)


class RhetoricAnalysis(BaseModel):
    """Análise retórica de um chunk/capítulo."""

    chunk_id: int
    start_time: float
    end_time: float
    techniques: list[RhetoricTechnique] = Field(default_factory=list)
    language_patterns: LanguagePatterns = Field(default_factory=LanguagePatterns)
    tone: Optional[str] = None  # "defensivo", "agressivo", "calmo", etc.
    analyzed_at: datetime = Field(default_factory=datetime.now)

    @property
    def technique_count(self) -> int:
        return len(self.techniques)

    @property
    def most_common_technique(self) -> Optional[TechniqueType]:
        if not self.techniques:
            return None
        from collections import Counter
        counts = Counter(t.type for t in self.techniques)
        return counts.most_common(1)[0][0]


class Chapter(BaseModel):
    """Um capítulo/secção do podcast."""

    id: str
    title: str
    start_time: float
    end_time: Optional[float] = None
    detected_by: str = "manual"  # "manual", "silence", "topic_change"


class ChapterAnalysis(BaseModel):
    """Análise completa de um capítulo."""

    chapter: Chapter
    transcript_text: str
    fact_checks: list["FactCheckResult"] = Field(default_factory=list)
    rhetoric_analysis: Optional[RhetoricAnalysis] = None
    summary: Optional[str] = None

    @property
    def fact_check_summary(self) -> dict:
        """Resumo dos fact-checks por veredito."""
        from collections import Counter
        from .claim import Verdict
        counts = Counter(fc.verdict for fc in self.fact_checks)
        return {v: counts.get(v, 0) for v in Verdict}


# Import circular fix
from .claim import FactCheckResult

ChapterAnalysis.model_rebuild()
