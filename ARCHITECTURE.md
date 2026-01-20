# Despolariza Real-Time Analyzer - Arquitectura

## Visão Geral

Sistema de análise em tempo real de vídeos YouTube com múltiplos agentes especializados.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WEB DASHBOARD                                   │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────────────────────┐  │
│  │ Video Player│  │   Transcrição   │  │      Análise por Capítulo       │  │
│  │  (YouTube)  │  │   (em tempo     │  │  ┌─────────┐ ┌───────────────┐  │  │
│  │             │  │     real)       │  │  │  Fact   │ │   Retórica    │  │  │
│  │             │  │                 │  │  │  Check  │ │   Analysis    │  │  │
│  └─────────────┘  └─────────────────┘  │  └─────────┘ └───────────────┘  │  │
└─────────────────────────────────────────────────────────────────────────────┘
                              ▲ WebSocket
                              │
┌─────────────────────────────┴───────────────────────────────────────────────┐
│                           BACKEND (FastAPI)                                  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        ORCHESTRATOR                                   │   │
│  │   - Gestão de sessões                                                │   │
│  │   - Routing de mensagens                                             │   │
│  │   - Deteção de capítulos                                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                    │                      │                      │
│           ▼                    ▼                      ▼                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │    AGENTE 1     │  │    AGENTE 2     │  │    AGENTE 3     │             │
│  │   TRANSCRITOR   │  │  FACT-CHECKER   │  │   ANALISADOR    │             │
│  │                 │  │                 │  │    RETÓRICO     │             │
│  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │             │
│  │  │  Whisper  │  │  │  │Claude API │  │  │  │Claude API │  │             │
│  │  │  (local)  │  │  │  │+ WebSearch│  │  │  │           │  │             │
│  │  └───────────┘  │  │  └───────────┘  │  │  └───────────┘  │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│           ▲                                                                  │
│           │                                                                  │
│  ┌────────┴─────────────────────────────────────────────────────────────┐   │
│  │                     AUDIO CAPTURE                                     │   │
│  │   - yt-dlp streaming                                                  │   │
│  │   - Chunking (30s segments)                                          │   │
│  │   - Buffer circular                                                   │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. Audio Capture (`src/capture/`)

Responsável por extrair áudio do YouTube em tempo real.

```python
# Fluxo:
YouTube URL → yt-dlp (streaming) → FFmpeg → Audio Chunks (30s WAV)
```

**Tecnologias:**
- `yt-dlp` - Download/streaming de YouTube
- `ffmpeg` - Conversão e segmentação de áudio
- `asyncio` - Processamento assíncrono

### 2. Agente Transcritor (`src/agents/transcriber.py`)

Converte áudio em texto usando Whisper local.

```python
# Fluxo:
Audio Chunk → Whisper → Texto + Timestamps → Queue
```

**Tecnologias:**
- `faster-whisper` ou `whisper.cpp` - Transcrição local otimizada
- Modelo: `large-v3` para PT (ou `medium` para menos recursos)

**Output:**
```json
{
  "chunk_id": 5,
  "start_time": 150.0,
  "end_time": 180.0,
  "text": "E portanto a questão da imigração...",
  "confidence": 0.94,
  "language": "pt"
}
```

### 3. Agente Fact-Checker (`src/agents/fact_checker.py`)

Identifica e verifica afirmações factuais.

```python
# Fluxo:
Texto → Extração de Claims → Pesquisa Web → Verificação → Veredito
```

**Responsabilidades:**
1. Identificar afirmações verificáveis (não opiniões)
2. Pesquisar fontes online
3. Comparar com factos conhecidos
4. Emitir veredito: ✅ ⚠️ ❌ ❓

**Output:**
```json
{
  "claim": "Portugal recebe 100 mil imigrantes por ano",
  "verdict": "partial",
  "confidence": 0.8,
  "sources": ["INE", "AIMA"],
  "explanation": "O número varia entre 80-120 mil dependendo do ano...",
  "timestamp": 165.3
}
```

### 4. Agente Analisador Retórico (`src/agents/rhetoric_analyzer.py`)

Identifica técnicas de persuasão e padrões de comunicação.

```python
# Fluxo:
Texto → Análise de Padrões → Classificação → Exemplos
```

**Técnicas Detetadas:**
- Apelo à emoção
- Generalização
- Strawman
- Whataboutism
- Cherry-picking
- etc.

**Output:**
```json
{
  "chapter": "Imigração",
  "techniques": [
    {
      "type": "appeal_to_emotion",
      "quote": "estas pessoas que fogem da miséria...",
      "timestamp": 172.5,
      "severity": "low"
    }
  ],
  "language_patterns": {
    "hedging": 3,
    "assertive": 7,
    "emotional_vocabulary": ["crise", "urgente", "dramático"]
  }
}
```

### 5. Orchestrator (`src/orchestrator.py`)

Coordena os agentes e gere o fluxo de dados.

**Responsabilidades:**
- Iniciar/parar sessões de análise
- Detetar mudanças de capítulo (por silêncio, tópico, ou manual)
- Distribuir trabalho aos agentes
- Agregar resultados
- Comunicar com frontend via WebSocket

### 6. Web Dashboard (`frontend/`)

Interface para visualização em tempo real.

**Tecnologias:**
- React + Vite
- Tailwind CSS
- WebSocket client

**Funcionalidades:**
- Player YouTube embebido (sincronizado)
- Transcrição live com scroll automático
- Painel de fact-checks com cores
- Timeline de técnicas retóricas
- Export para Markdown

---

## Estrutura de Ficheiros

```
despolariza-fact-checker/
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Configurações
│   ├── orchestrator.py         # Coordenador principal
│   │
│   ├── capture/
│   │   ├── __init__.py
│   │   ├── youtube.py          # yt-dlp streaming
│   │   └── audio_buffer.py     # Buffer circular
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py             # Classe base Agent
│   │   ├── transcriber.py      # Whisper agent
│   │   ├── fact_checker.py     # Fact-check agent
│   │   └── rhetoric.py         # Análise retórica
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── transcript.py       # Modelos de transcrição
│   │   ├── claim.py            # Modelos de fact-check
│   │   └── analysis.py         # Modelos de análise
│   │
│   └── utils/
│       ├── __init__.py
│       ├── chapter_detector.py # Deteção de capítulos
│       └── web_search.py       # Pesquisa web
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── VideoPlayer.jsx
│       │   ├── Transcript.jsx
│       │   ├── FactCheckPanel.jsx
│       │   └── RhetoricTimeline.jsx
│       └── hooks/
│           └── useWebSocket.js
│
├── tests/
├── requirements.txt
├── package.json
├── README.md
└── ARCHITECTURE.md
```

---

## Fluxo de Dados

```
1. User submete URL do YouTube
         │
         ▼
2. Orchestrator inicia sessão
         │
         ▼
3. Audio Capture começa streaming
         │
         ▼
4. A cada 30s, chunk é enviado ao Transcritor
         │
         ▼
5. Transcritor processa e envia texto ao Orchestrator
         │
         ├──────────────────────┐
         ▼                      ▼
6. Fact-Checker           7. Rhetoric Analyzer
   analisa claims            analisa padrões
         │                      │
         └──────────┬───────────┘
                    ▼
8. Orchestrator agrega resultados
                    │
                    ▼
9. WebSocket envia updates ao Dashboard
                    │
                    ▼
10. Dashboard atualiza UI em tempo real
```

---

## APIs

### REST Endpoints

```
POST /api/session/start     - Iniciar análise de um vídeo
POST /api/session/stop      - Parar análise
GET  /api/session/{id}      - Estado da sessão
GET  /api/chapters/{id}     - Lista de capítulos detetados
GET  /api/export/{id}       - Exportar relatório MD
```

### WebSocket Events

```javascript
// Cliente → Servidor
{ "type": "start", "url": "https://youtube.com/watch?v=..." }
{ "type": "stop" }
{ "type": "set_chapter", "timestamp": 1234 }

// Servidor → Cliente
{ "type": "transcript", "data": { "text": "...", "timestamp": 123 } }
{ "type": "fact_check", "data": { "claim": "...", "verdict": "..." } }
{ "type": "rhetoric", "data": { "technique": "...", "quote": "..." } }
{ "type": "chapter_detected", "data": { "title": "...", "start": 123 } }
{ "type": "error", "message": "..." }
```

---

## Requisitos de Sistema

### Mínimos
- Python 3.10+
- Node.js 18+
- 8GB RAM (Whisper medium)
- GPU opcional mas recomendado

### Recomendados
- 16GB RAM (Whisper large-v3)
- NVIDIA GPU com CUDA (10x mais rápido)
- SSD para buffer de áudio

### Dependências Python
```
fastapi
uvicorn
websockets
yt-dlp
faster-whisper
anthropic
httpx
pydantic
python-multipart
```

---

## Próximos Passos

1. [ ] Setup inicial do projeto
2. [ ] Implementar Audio Capture básico
3. [ ] Integrar Whisper para transcrição
4. [ ] Criar WebSocket server
5. [ ] Implementar Fact-Checker agent
6. [ ] Implementar Rhetoric Analyzer agent
7. [ ] Criar dashboard React
8. [ ] Testes end-to-end
9. [ ] Otimização de performance
