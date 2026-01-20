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
    true: 'verdict-true',
    partial: 'verdict-partial',
    false: 'verdict-false',
    inconclusive: 'verdict-inconclusive',
    pending: 'text-gray-500'
  }

  return (
    <div className="bg-gray-800 p-3 rounded-lg mb-2">
      <div className="flex items-start gap-2">
        <span className="text-xl">{verdictEmoji[factCheck.verdict] || '❓'}</span>
        <div className="flex-1">
          <p className={`font-medium ${verdictClass[factCheck.verdict]}`}>
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
  const severityClass = {
    low: 'severity-low',
    medium: 'severity-medium',
    high: 'severity-high'
  }

  return (
    <div className={`bg-gray-800 p-3 rounded-lg mb-2 border-l-4 ${severityClass[technique.severity] || 'border-l-gray-600'}`}>
      <div className="font-medium text-blue-400">{technique.type}</div>
      <p className="text-sm text-gray-300 mt-1 italic">"{technique.quote}"</p>
      {technique.explanation && (
        <p className="text-xs text-gray-500 mt-1">{technique.explanation}</p>
      )}
    </div>
  )
}

// Componente de Transcrição
function TranscriptPanel({ transcripts }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [transcripts])

  const formatTime = (seconds) => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto p-4 space-y-2">
      {transcripts.map((t, i) => (
        <div key={i} className="flex gap-3">
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {formatTime(t.start_time)}
          </span>
          <p className="text-sm text-gray-300">{t.text}</p>
        </div>
      ))}
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
  const [progress, setProgress] = useState({ current: 0, total: 0 })
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
      case 'progress':
        setProgress({
          current: lastMessage.data.current_time,
          total: lastMessage.data.total_duration
        })
        break
      case 'complete':
        setSession(prev => prev ? { ...prev, status: 'completed' } : null)
        break
      case 'error':
        setError(lastMessage.message || lastMessage.data)
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
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    try {
      await fetch('/api/session/stop', { method: 'POST' })
      setSession(prev => prev ? { ...prev, status: 'stopped' } : null)
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
              <span className="text-sm text-gray-400">
                {Math.floor(progress.current / 60)}:{String(Math.floor(progress.current % 60)).padStart(2, '0')}
                {' / '}
                {Math.floor(progress.total / 60)}:{String(Math.floor(progress.total % 60)).padStart(2, '0')}
              </span>
            </div>
          </div>
        )}
      </header>

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
            <span className="text-gray-400">📺 {session.video_title}</span>
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
        {/* Transcription panel */}
        <div className="w-1/2 border-r border-gray-700 flex flex-col">
          <div className="p-3 bg-gray-800 border-b border-gray-700">
            <h2 className="font-medium">📝 Transcrição</h2>
          </div>
          <div className="flex-1 overflow-hidden">
            <TranscriptPanel transcripts={transcripts} />
          </div>
        </div>

        {/* Analysis panels */}
        <div className="w-1/2 flex flex-col">
          {/* Fact-checks */}
          <div className="flex-1 border-b border-gray-700 flex flex-col">
            <div className="p-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
              <h2 className="font-medium">✅ Fact-Check</h2>
              <span className="text-sm text-gray-400">{factChecks.length} verificações</span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {factChecks.map((fc, i) => (
                <FactCheckItem key={i} factCheck={fc} />
              ))}
              {factChecks.length === 0 && (
                <p className="text-gray-500 text-center">A aguardar fact-checks...</p>
              )}
            </div>
          </div>

          {/* Rhetoric */}
          <div className="flex-1 flex flex-col">
            <div className="p-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
              <h2 className="font-medium">🎭 Retórica</h2>
              <span className="text-sm text-gray-400">{rhetoricTechniques.length} técnicas</span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {rhetoricTechniques.map((tech, i) => (
                <RhetoricItem key={i} technique={tech} />
              ))}
              {rhetoricTechniques.length === 0 && (
                <p className="text-gray-500 text-center">A aguardar análise retórica...</p>
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
