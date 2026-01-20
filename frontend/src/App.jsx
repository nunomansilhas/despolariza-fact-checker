import { useState, useEffect, useRef, useCallback } from 'react'

// Hook para WebSocket
function useWebSocket(url) {
  const [messages, setMessages] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)

  const connect = useCallback(() => {
    const ws = new WebSocket(url)

    ws.onopen = () => {
      setIsConnected(true)
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setMessages(prev => [...prev, data])
    }

    ws.onclose = () => {
      setIsConnected(false)
      console.log('WebSocket disconnected')
      // Reconectar após 3s
      setTimeout(connect, 3000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    wsRef.current = ws
  }, [url])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  const send = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { messages, isConnected, send }
}

// Formatar tempo em HH:MM:SS ou MM:SS
function formatTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Componente de Status
function StatusBanner({ status }) {
  const stageEmoji = {
    'fetching_info': '🔍',
    'parsing_chapters': '📑',
    'loading_model': '🧠',
    'model_ready': '✓',
    'downloading': '📥',
    'transcribing': '🎤',
  }

  if (!status) return null

  return (
    <div className="bg-blue-900/50 text-blue-200 px-4 py-2 flex items-center gap-2 animate-pulse">
      <span>{stageEmoji[status.stage] || '⏳'}</span>
      <span>{status.message}</span>
    </div>
  )
}

// Componente de Capítulo/Cronologia
function ChapterItem({ chapter, isActive, onClick }) {
  return (
    <div
      onClick={onClick}
      className={`p-2 rounded cursor-pointer transition ${
        isActive
          ? 'bg-blue-600 text-white'
          : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono text-gray-400">
          {formatTime(chapter.start_time)}
        </span>
        <span className="text-sm flex-1 truncate">{chapter.title}</span>
      </div>
    </div>
  )
}

// Componente de Fact-Check
function FactCheckItem({ factCheck }) {
  const verdictEmoji = {
    true: '✅',
    partial: '⚠️',
    false: '❌',
    inconclusive: '❓',
    pending: '⏳'
  }

  const verdictClass = {
    true: 'border-l-green-500',
    partial: 'border-l-yellow-500',
    false: 'border-l-red-500',
    inconclusive: 'border-l-gray-500',
    pending: 'border-l-gray-600'
  }

  return (
    <div className={`bg-gray-800 p-3 rounded-lg mb-2 border-l-4 ${verdictClass[factCheck.verdict] || 'border-l-gray-600'}`}>
      <div className="flex items-start gap-2">
        <span className="text-xl">{verdictEmoji[factCheck.verdict] || '❓'}</span>
        <div className="flex-1">
          <p className="font-medium text-gray-200">
            {factCheck.claim?.text}
          </p>
          {factCheck.explanation && (
            <p className="text-sm text-gray-400 mt-1">{factCheck.explanation}</p>
          )}
          {factCheck.sources?.length > 0 && (
            <p className="text-xs text-gray-500 mt-1">
              Fontes: {factCheck.sources.join(', ')}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// Componente de Técnica Retórica
function RhetoricItem({ technique }) {
  const severityColors = {
    low: 'border-l-blue-500 bg-blue-900/20',
    medium: 'border-l-yellow-500 bg-yellow-900/20',
    high: 'border-l-red-500 bg-red-900/20'
  }

  return (
    <div className={`p-3 rounded-lg mb-2 border-l-4 ${severityColors[technique.severity] || 'border-l-gray-600 bg-gray-800'}`}>
      <div className="font-medium text-blue-400">{technique.type}</div>
      <p className="text-sm text-gray-300 mt-1 italic">"{technique.quote}"</p>
      {technique.explanation && (
        <p className="text-xs text-gray-500 mt-1">{technique.explanation}</p>
      )}
    </div>
  )
}

// Componente de Transcrição
function TranscriptPanel({ transcripts, chapters }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [transcripts])

  // Agrupar transcrições por capítulo
  const getChapterForTime = (time) => {
    for (let i = chapters.length - 1; i >= 0; i--) {
      if (time >= chapters[i].start_time) {
        return chapters[i]
      }
    }
    return null
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto p-4 space-y-2">
      {transcripts.map((t, i) => {
        const chapter = getChapterForTime(t.start_time)
        const prevChapter = i > 0 ? getChapterForTime(transcripts[i-1].start_time) : null
        const showChapterHeader = chapter && (!prevChapter || chapter.id !== prevChapter?.id)

        return (
          <div key={i}>
            {showChapterHeader && (
              <div className="bg-blue-900/30 px-3 py-1 rounded-lg mb-2 mt-4 first:mt-0">
                <span className="text-blue-400 font-medium text-sm">
                  📌 {chapter.title}
                </span>
              </div>
            )}
            <div className="flex gap-3">
              <span className="text-xs text-gray-500 whitespace-nowrap font-mono">
                {formatTime(t.start_time)}
              </span>
              <p className="text-sm text-gray-300">{t.text}</p>
            </div>
          </div>
        )
      })}
      {transcripts.length === 0 && (
        <p className="text-gray-500 text-center">A aguardar transcrição...</p>
      )}
    </div>
  )
}

// App Principal
export default function App() {
  const [url, setUrl] = useState('')
  const [session, setSession] = useState(null)
  const [transcripts, setTranscripts] = useState([])
  const [factChecks, setFactChecks] = useState([])
  const [rhetoricTechniques, setRhetoricTechniques] = useState([])
  const [chapters, setChapters] = useState([])
  const [progress, setProgress] = useState({ current: 0, total: 0, currentChapter: null, chunksProcessed: 0 })
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const { messages, isConnected, send } = useWebSocket(
    `ws://${window.location.hostname}:3068/ws`
  )

  // Processar mensagens do WebSocket
  useEffect(() => {
    if (messages.length === 0) return

    const lastMessage = messages[messages.length - 1]

    switch (lastMessage.type) {
      case 'transcript':
        setTranscripts(prev => [...prev, lastMessage.data])
        break
      case 'fact_check':
        setFactChecks(prev => [...prev, lastMessage.data])
        break
      case 'rhetoric':
        if (lastMessage.data.techniques) {
          setRhetoricTechniques(prev => [...prev, ...lastMessage.data.techniques])
        }
        break
      case 'chapter':
        setChapters(prev => [...prev, lastMessage.data])
        break
      case 'progress':
        setProgress({
          current: lastMessage.data.current_time,
          total: lastMessage.data.total_duration,
          currentChapter: lastMessage.data.current_chapter,
          chunksProcessed: lastMessage.data.chunks_processed || 0
        })
        break
      case 'status':
        setStatus(lastMessage.data)
        break
      case 'complete':
        setSession(prev => prev ? { ...prev, status: 'completed' } : null)
        setStatus(null)
        break
      case 'error':
        setError(lastMessage.message || lastMessage.data)
        setStatus(null)
        break
    }
  }, [messages])

  const handleStart = async () => {
    if (!url.trim()) return

    setLoading(true)
    setError(null)
    setTranscripts([])
    setFactChecks([])
    setRhetoricTechniques([])
    setChapters([])
    setStatus({ stage: 'fetching_info', message: 'A iniciar...' })

    try {
      const response = await fetch('/api/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to start session')
      }

      const data = await response.json()
      setSession(data)
      setProgress({ current: 0, total: data.video_duration || 0 })
    } catch (e) {
      setError(e.message)
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    try {
      await fetch('/api/session/stop', { method: 'POST' })
      setSession(prev => prev ? { ...prev, status: 'stopped' } : null)
      setStatus(null)
    } catch (e) {
      setError(e.message)
    }
  }

  const handleExport = async () => {
    try {
      const response = await fetch('/api/export')
      const text = await response.text()

      const blob = new Blob([text], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'analysis.md'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message)
    }
  }

  const progressPercent = progress.total > 0
    ? Math.min(100, (progress.current / progress.total) * 100)
    : 0

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 p-4 shadow-lg">
        <div className="max-w-7xl mx-auto flex items-center gap-4">
          <h1 className="text-xl font-bold">🔍 Despolariza Analyzer</h1>

          <div className="flex-1 flex gap-2">
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Cole o URL do YouTube..."
              className="flex-1 px-4 py-2 bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading || session?.status === 'running'}
              onKeyDown={(e) => e.key === 'Enter' && handleStart()}
            />

            {!session || session.status !== 'running' ? (
              <button
                onClick={handleStart}
                disabled={loading || !url.trim()}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg font-medium transition"
              >
                {loading ? 'A iniciar...' : 'Analisar'}
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="px-6 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-medium transition"
              >
                Parar
              </button>
            )}

            {session && (
              <button
                onClick={handleExport}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition"
                title="Exportar Markdown"
              >
                📥
              </button>
            )}
          </div>

          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
               title={isConnected ? 'Conectado' : 'Desconectado'} />
        </div>

        {/* Progress bar */}
        {session && progress.total > 0 && (
          <div className="max-w-7xl mx-auto mt-3">
            <div className="flex items-center gap-3">
              <div className="flex-1 bg-gray-700 rounded-full h-2">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="text-sm text-gray-400 whitespace-nowrap">
                {formatTime(progress.current)} / {formatTime(progress.total)}
              </span>
              <span className="text-xs text-gray-500">
                ({progress.chunksProcessed} chunks)
              </span>
            </div>
            {progress.currentChapter && (
              <div className="text-xs text-gray-400 mt-1">
                📌 {progress.currentChapter}
              </div>
            )}
          </div>
        )}
      </header>

      {/* Status banner */}
      <StatusBanner status={status} />

      {/* Error banner */}
      {error && (
        <div className="bg-red-900 text-red-200 px-4 py-2 flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200">✕</button>
        </div>
      )}

      {/* Session info */}
      {session && (
        <div className="bg-gray-800 px-4 py-2 border-b border-gray-700">
          <div className="max-w-7xl mx-auto flex items-center gap-4 text-sm">
            <span className="text-gray-400 truncate flex-1">📺 {session.video_title}</span>
            <span className={`px-2 py-0.5 rounded text-xs ${
              session.status === 'running' ? 'bg-green-900 text-green-300' :
              session.status === 'completed' ? 'bg-blue-900 text-blue-300' :
              'bg-gray-700 text-gray-400'
            }`}>
              {session.status}
            </span>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Chapters sidebar */}
        {chapters.length > 0 && (
          <div className="w-64 bg-gray-900 border-r border-gray-700 flex flex-col">
            <div className="p-3 bg-gray-800 border-b border-gray-700">
              <h2 className="font-medium text-sm">📑 Cronologia ({chapters.length})</h2>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {chapters.map((ch, i) => (
                <ChapterItem
                  key={i}
                  chapter={ch}
                  isActive={progress.currentChapter === ch.title}
                />
              ))}
            </div>
          </div>
        )}

        {/* Transcription panel */}
        <div className="flex-1 border-r border-gray-700 flex flex-col">
          <div className="p-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
            <h2 className="font-medium">📝 Transcrição</h2>
            <span className="text-sm text-gray-400">{transcripts.length} segmentos</span>
          </div>
          <div className="flex-1 overflow-hidden">
            <TranscriptPanel transcripts={transcripts} chapters={chapters} />
          </div>
        </div>

        {/* Analysis panels */}
        <div className="w-96 flex flex-col">
          {/* Fact-checks */}
          <div className="flex-1 border-b border-gray-700 flex flex-col">
            <div className="p-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
              <h2 className="font-medium">✅ Fact-Check</h2>
              <span className="text-sm text-gray-400">{factChecks.length}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              {factChecks.map((fc, i) => (
                <FactCheckItem key={i} factCheck={fc} />
              ))}
              {factChecks.length === 0 && (
                <p className="text-gray-500 text-center text-sm">
                  {session?.status === 'running' ? 'A processar...' : 'Sem fact-checks ainda'}
                </p>
              )}
            </div>
          </div>

          {/* Rhetoric */}
          <div className="flex-1 flex flex-col">
            <div className="p-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
              <h2 className="font-medium">🎭 Retórica</h2>
              <span className="text-sm text-gray-400">{rhetoricTechniques.length}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              {rhetoricTechniques.map((tech, i) => (
                <RhetoricItem key={i} technique={tech} />
              ))}
              {rhetoricTechniques.length === 0 && (
                <p className="text-gray-500 text-center text-sm">
                  {session?.status === 'running' ? 'A analisar...' : 'Sem técnicas detetadas'}
                </p>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-gray-800 p-2 text-center text-xs text-gray-500">
        Despolariza Analyzer v0.1.0 | Powered by Whisper + Claude
      </footer>
    </div>
  )
}
