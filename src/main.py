"""API principal - FastAPI + WebSocket."""

import asyncio
import json
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
import logging

from .orchestrator import Orchestrator
from .config import settings

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Estado global
orchestrator: Optional[Orchestrator] = None
connected_clients: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    global orchestrator
    orchestrator = Orchestrator()
    logger.info("Orchestrator initialized")
    yield
    if orchestrator:
        await orchestrator.stop_session()
    logger.info("Cleanup complete")


app = FastAPI(
    title="Despolariza Analyzer",
    description="Análise em tempo real de podcasts",
    version="0.1.0",
    lifespan=lifespan
)

# CORS para desenvolvimento
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models ---

class ChapterInput(BaseModel):
    id: str
    title: str
    start_time: float
    end_time: Optional[float] = None


class StartSessionRequest(BaseModel):
    url: str
    custom_chapters: Optional[list[ChapterInput]] = None


class SessionResponse(BaseModel):
    session_id: str
    status: str
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    current_time: float = 0.0
    chunks_processed: int = 0


# --- REST Endpoints ---

@app.get("/")
async def root():
    """Página inicial."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Despolariza Analyzer</title>
        <style>
            body { font-family: system-ui; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }
            code { background: #e0e0e0; padding: 2px 6px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>Despolariza Analyzer API</h1>
        <p>Sistema de análise em tempo real de podcasts.</p>

        <h2>Endpoints</h2>

        <div class="endpoint">
            <strong>POST /api/session/start</strong><br>
            Inicia análise de um vídeo. Body: <code>{"url": "https://youtube.com/..."}</code>
        </div>

        <div class="endpoint">
            <strong>GET /api/session</strong><br>
            Estado da sessão atual.
        </div>

        <div class="endpoint">
            <strong>POST /api/session/stop</strong><br>
            Para a sessão atual.
        </div>

        <div class="endpoint">
            <strong>GET /api/export</strong><br>
            Exporta análise em Markdown.
        </div>

        <div class="endpoint">
            <strong>WebSocket /ws</strong><br>
            Conexão em tempo real para receber updates.
        </div>

        <h2>Links</h2>
        <ul>
            <li><a href="/docs">Documentação Swagger</a></li>
            <li><a href="/redoc">ReDoc</a></li>
        </ul>
    </body>
    </html>
    """)


@app.post("/api/session/start", response_model=SessionResponse)
async def start_session(request: StartSessionRequest):
    """Inicia uma nova sessão de análise."""
    global orchestrator

    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    try:
        # Converter custom chapters para formato do orchestrator
        custom_chapters = None
        if request.custom_chapters:
            custom_chapters = [
                {
                    "id": ch.id,
                    "title": ch.title,
                    "start_time": ch.start_time,
                    "end_time": ch.end_time
                }
                for ch in request.custom_chapters
            ]

        session = await orchestrator.start_session(request.url, custom_chapters=custom_chapters)

        # Configurar broadcasts via WebSocket
        async def broadcast(event: str, data):
            message = {
                "type": event,
                "data": _serialize(data)
            }
            await broadcast_message(message)

        orchestrator.on("transcript", lambda d: asyncio.create_task(broadcast("transcript", d)))
        orchestrator.on("fact_check", lambda d: asyncio.create_task(broadcast("fact_check", d)))
        orchestrator.on("rhetoric", lambda d: asyncio.create_task(broadcast("rhetoric", d)))
        orchestrator.on("chapter", lambda d: asyncio.create_task(broadcast("chapter", d)))
        orchestrator.on("progress", lambda d: asyncio.create_task(broadcast("progress", d)))
        orchestrator.on("status", lambda d: asyncio.create_task(broadcast("status", d)))
        orchestrator.on("error", lambda d: asyncio.create_task(broadcast("error", d)))
        orchestrator.on("complete", lambda d: asyncio.create_task(broadcast("complete", d)))

        return SessionResponse(
            session_id=session.id,
            status=session.status,
            video_title=session.video_info.title if session.video_info else None,
            video_duration=session.video_info.duration if session.video_info else None,
        )

    except Exception as e:
        logger.error(f"Error starting session: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/session", response_model=SessionResponse)
async def get_session():
    """Obtém estado da sessão atual."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    session = orchestrator.get_session_state()
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    return SessionResponse(
        session_id=session.id,
        status=session.status,
        video_title=session.video_info.title if session.video_info else None,
        video_duration=session.video_info.duration if session.video_info else None,
        current_time=session.current_time,
        chunks_processed=session.chunks_processed,
    )


@app.post("/api/session/stop")
async def stop_session():
    """Para a sessão atual."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    await orchestrator.stop_session()
    return {"status": "stopped"}


@app.post("/api/session/clear")
async def clear_session():
    """Limpa completamente a sessão e apaga dados guardados."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    await orchestrator.clear_session()
    return {"status": "cleared"}


@app.get("/api/export")
async def export_analysis():
    """Exporta análise em Markdown."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    markdown = orchestrator.export_markdown()
    if not markdown:
        raise HTTPException(status_code=404, detail="No analysis to export")

    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=analysis.md"}
    )


@app.get("/api/transcript")
async def get_transcript():
    """Obtém transcrição completa."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    text = orchestrator.get_full_transcript()
    return {"transcript": text}


@app.get("/api/session/data")
async def get_session_data():
    """Obtém todos os dados da sessão (transcripts, chapters, etc.)."""
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")

    session = orchestrator.get_session_state()

    # Se não há sessão activa, tentar carregar do auto-save
    if not session:
        autosave = orchestrator.load_autosave()
        if autosave:
            return {
                "session_id": autosave.get("session_id"),
                "status": autosave.get("status", "recovered"),
                "video_title": autosave.get("video_info", {}).get("title") if autosave.get("video_info") else None,
                "video_duration": autosave.get("video_info", {}).get("duration") if autosave.get("video_info") else None,
                "current_time": autosave.get("current_time", 0),
                "chunks_processed": autosave.get("chunks_processed", 0),
                "transcripts": autosave.get("transcripts", []),
                "chapters": autosave.get("chapters", []),
                "recovered_from_autosave": True
            }
        raise HTTPException(status_code=404, detail="No active session")

    return {
        "session_id": session.id,
        "status": session.status,
        "video_title": session.video_info.title if session.video_info else None,
        "video_duration": session.video_info.duration if session.video_info else None,
        "current_time": session.current_time,
        "chunks_processed": session.chunks_processed,
        "transcripts": [_serialize(t) for t in session.transcripts],
        "chapters": [_serialize(c) for c in session.chapters],
    }


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Conexão WebSocket para updates em tempo real."""
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")

    try:
        while True:
            # Receber mensagens do cliente
            data = await websocket.receive_text()
            message = json.loads(data)

            # Processar comandos
            if message.get("type") == "start":
                url = message.get("url")
                if url and orchestrator:
                    try:
                        await orchestrator.start_session(url)
                        await websocket.send_json({"type": "session_started"})
                    except Exception as e:
                        await websocket.send_json({"type": "error", "message": str(e)})

            elif message.get("type") == "stop":
                if orchestrator:
                    await orchestrator.stop_session()
                    await websocket.send_json({"type": "session_stopped"})

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        connected_clients.discard(websocket)


async def broadcast_message(message: dict):
    """Envia mensagem para todos os clientes conectados."""
    if not connected_clients:
        return

    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)

    # Remover clientes desconectados
    for client in disconnected:
        connected_clients.discard(client)


def _serialize(obj) -> dict:
    """Serializa objeto para JSON."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    elif hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    elif isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    else:
        return obj


# --- Run ---

def run():
    """Corre o servidor."""
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.ws_host,
        port=settings.ws_port,
        reload=True
    )


if __name__ == "__main__":
    run()
