# Despolariza Real-Time Analyzer

Sistema de análise em tempo real de podcasts do YouTube com múltiplos agentes especializados.

## Funcionalidades

- **Transcrição em tempo real** usando Whisper (local)
- **Fact-checking automático** com Claude AI
- **Análise retórica** - identifica técnicas de persuasão
- **Dashboard web** com updates via WebSocket
- **Export** para Markdown

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                     WEB DASHBOARD (React)                    │
│   Transcrição | Fact-Check | Análise Retórica | Timeline    │
└─────────────────────────────────────────────────────────────┘
                           ▲ WebSocket
┌─────────────────────────┴───────────────────────────────────┐
│                    BACKEND (FastAPI)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Transcritor │  │Fact-Checker │  │  Analisador │         │
│  │  (Whisper)  │  │  (Claude)   │  │  Retórico   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                         ▲                                    │
│  ┌──────────────────────┴──────────────────────────────┐    │
│  │              YouTube Audio Capture                   │    │
│  │                   (yt-dlp)                          │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## Requisitos

### Sistema
- Python 3.10+
- Node.js 18+
- ffmpeg
- 8GB+ RAM (16GB recomendado para Whisper large)
- GPU NVIDIA opcional (10x mais rápido)

### API Keys
- `ANTHROPIC_API_KEY` - para fact-checking e análise retórica

## Instalação

### Backend

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar API key
cp .env.example .env
# Editar .env com a tua ANTHROPIC_API_KEY
```

### Frontend

```bash
cd frontend
npm install
```

## Uso

### 1. Iniciar o Backend

```bash
# Na raiz do projeto
python -m src.main
# ou
uvicorn src.main:app --reload
```

O servidor inicia em http://localhost:8000

### 2. Iniciar o Frontend

```bash
cd frontend
npm run dev
```

O dashboard abre em http://localhost:3000

### 3. Analisar um Podcast

1. Cola o URL do YouTube no campo de input
2. Clica em "Analisar"
3. Observa a transcrição, fact-checks e análise retórica em tempo real
4. Clica em 📥 para exportar o relatório

## API

### REST Endpoints

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/session/start` | POST | Inicia análise `{url: "..."}` |
| `/api/session` | GET | Estado da sessão |
| `/api/session/stop` | POST | Para análise |
| `/api/export` | GET | Exporta Markdown |
| `/api/transcript` | GET | Transcrição completa |

### WebSocket

Conecta a `ws://localhost:8000/ws` para receber:

```javascript
// Eventos recebidos
{ type: "transcript", data: {...} }
{ type: "fact_check", data: {...} }
{ type: "rhetoric", data: {...} }
{ type: "progress", data: {current_time, total_duration, percentage} }
{ type: "complete", data: {...} }
{ type: "error", message: "..." }

// Comandos enviados
{ type: "start", url: "..." }
{ type: "stop" }
```

## Configuração

Cria um ficheiro `.env` na raiz:

```env
ANTHROPIC_API_KEY=sk-ant-...

# Whisper
WHISPER_MODEL=large-v3  # tiny, base, small, medium, large-v3
WHISPER_DEVICE=auto     # cpu, cuda, auto

# Análise
FACT_CHECK_ENABLED=true
RHETORIC_ANALYSIS_ENABLED=true

# Server
WS_HOST=0.0.0.0
WS_PORT=8000
```

## Técnicas Retóricas Detectadas

- **Apelo à emoção** - usar medo, raiva em vez de dados
- **Apelo à autoridade** - "os especialistas dizem..." sem citar
- **Generalização** - "toda a gente sabe..."
- **Falsa dicotomia** - só 2 opções quando há mais
- **Whataboutism** - "e o outro lado?"
- **Strawman** - distorcer argumento do oponente
- **Cherry-picking** - selecionar só dados favoráveis
- **Gish gallop** - muitos argumentos fracos
- E mais...

## Estrutura do Projeto

```
despolariza-fact-checker/
├── src/
│   ├── main.py           # FastAPI app
│   ├── orchestrator.py   # Coordenador
│   ├── config.py         # Configurações
│   ├── agents/           # Agentes
│   │   ├── transcriber.py
│   │   ├── fact_checker.py
│   │   └── rhetoric.py
│   ├── capture/          # YouTube capture
│   └── models/           # Pydantic models
├── frontend/             # React dashboard
├── tests/
├── requirements.txt
└── README.md
```

## Desenvolvimento

```bash
# Testes
pytest tests/

# Lint
ruff check src/

# Type check
mypy src/
```

## Limitações

- Requer API key do Anthropic (Claude)
- Whisper local pode ser lento sem GPU
- YouTube pode bloquear downloads excessivos
- Fact-checking depende do conhecimento do modelo

## Licença

MIT

## Créditos

- [Whisper](https://github.com/openai/whisper) - OpenAI
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - CTranslate2
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube download
- [Claude](https://anthropic.com) - Anthropic
