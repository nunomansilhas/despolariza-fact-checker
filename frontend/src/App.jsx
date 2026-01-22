import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

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

  return { messages, isConnected }
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

// Parser de cronologia manual
function parseCronologia(text) {
  const lines = text.trim().split('\n')
  const chapters = []

  for (const line of lines) {
    // Match patterns like:
    // "00:00:00 - Title"
    // "00:00:00 – Title" (em dash)
    // "00:00:00 Title"
    // "0:00:00 - Title"
    const match = line.trim().match(/^(\d{1,2}:\d{2}:\d{2})\s*[-–—]?\s*(.+)$/)
    if (match) {
      const [, timestamp, title] = match
      const parts = timestamp.split(':').map(Number)
      const seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]

      chapters.push({
        id: `ch_${chapters.length}`,
        title: title.trim(),
        start_time: seconds,
        end_time: null
      })
    }
  }

  // Calculate end times
  for (let i = 0; i < chapters.length; i++) {
    if (i < chapters.length - 1) {
      chapters[i].end_time = chapters[i + 1].start_time
    }
  }

  return chapters
}

// Componente de Status
function StatusBanner({ status }) {
  const stageInfo = {
    'fetching_info': { emoji: '🔍', color: 'bg-blue-900/50' },
    'parsing_chapters': { emoji: '📑', color: 'bg-blue-900/50' },
    'loading_model': { emoji: '🧠', color: 'bg-yellow-900/50' },
    'model_ready': { emoji: '✓', color: 'bg-green-900/50' },
    'downloading': { emoji: '📥', color: 'bg-orange-900/50' },
    'transcribing': { emoji: '🎤', color: 'bg-purple-900/50' },
  }

  if (!status) return null

  const info = stageInfo[status.stage] || { emoji: '⏳', color: 'bg-gray-900/50' }

  return (
    <div className={`${info.color} text-gray-200 px-4 py-2 flex items-center gap-2`}>
      <span className="animate-pulse">{info.emoji}</span>
      <span>{status.message}</span>
    </div>
  )
}

// Componente de Capítulo na sidebar
function ChapterListItem({ chapter, isActive, isProcessing, transcriptCount, onClick }) {
  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-lg cursor-pointer transition border-l-4 ${
        isActive
          ? 'bg-blue-600 border-l-blue-400 text-white'
          : isProcessing
          ? 'bg-yellow-900/30 border-l-yellow-500 text-yellow-200'
          : transcriptCount > 0
          ? 'bg-gray-800 border-l-green-500 hover:bg-gray-700 text-gray-200'
          : 'bg-gray-800/50 border-l-gray-600 hover:bg-gray-700 text-gray-400'
      }`}
    >
      <div className="flex items-start gap-2">
        <span className="text-xs font-mono text-gray-400 mt-0.5">
          {formatTime(chapter.start_time)}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{chapter.title}</div>
          {transcriptCount > 0 && (
            <div className="text-xs text-gray-400 mt-1">
              {transcriptCount} segmentos
            </div>
          )}
        </div>
        {isProcessing && (
          <span className="animate-pulse text-yellow-400">●</span>
        )}
      </div>
    </div>
  )
}

// Cores para diferentes speakers
const SPEAKER_COLORS = {
  'SPEAKER_00': { bg: 'bg-blue-900/30', border: 'border-l-blue-500', text: 'text-blue-400', name: 'Speaker A' },
  'SPEAKER_01': { bg: 'bg-green-900/30', border: 'border-l-green-500', text: 'text-green-400', name: 'Speaker B' },
  'SPEAKER_02': { bg: 'bg-purple-900/30', border: 'border-l-purple-500', text: 'text-purple-400', name: 'Speaker C' },
  'SPEAKER_03': { bg: 'bg-orange-900/30', border: 'border-l-orange-500', text: 'text-orange-400', name: 'Speaker D' },
}

function getSpeakerStyle(speaker) {
  return SPEAKER_COLORS[speaker] || { bg: 'bg-gray-800/50', border: 'border-l-gray-500', text: 'text-gray-400', name: speaker || 'Unknown' }
}

// Painel de Transcrição de um Capítulo
function ChapterTranscriptPanel({ chapter, transcripts, nextChapterStart }) {
  const scrollRef = useRef(null)

  // Filtrar transcrições deste capítulo
  const chapterTranscripts = useMemo(() => {
    if (!chapter) return []
    const endTime = nextChapterStart || Infinity
    return transcripts.filter(t =>
      t.start_time >= chapter.start_time && t.start_time < endTime
    )
  }, [chapter, transcripts, nextChapterStart])

  // Agrupar segmentos por speaker para visualização em conversa
  const groupedByConversation = useMemo(() => {
    const groups = []
    let currentGroup = null

    for (const transcript of chapterTranscripts) {
      // Se tiver segmentos com speakers, agrupar por speaker
      if (transcript.segments && transcript.segments.length > 0) {
        for (const seg of transcript.segments) {
          const speaker = seg.speaker || null
          if (!currentGroup || currentGroup.speaker !== speaker) {
            currentGroup = {
              speaker,
              segments: [],
              startTime: seg.start
            }
            groups.push(currentGroup)
          }
          currentGroup.segments.push(seg)
        }
      } else {
        // Fallback: usar o transcript inteiro
        if (!currentGroup) {
          currentGroup = { speaker: null, segments: [], startTime: transcript.start_time }
          groups.push(currentGroup)
        }
        currentGroup.segments.push({
          text: transcript.text,
          start: transcript.start_time,
          end: transcript.end_time,
          speaker: null
        })
      }
    }
    return groups
  }, [chapterTranscripts])

  // Verificar se temos diarização
  const hasSpeakers = groupedByConversation.some(g => g.speaker)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [chapterTranscripts])

  if (!chapter) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <div className="text-4xl mb-2">📑</div>
          <div>Seleciona um capítulo para ver a transcrição</div>
        </div>
      </div>
    )
  }

  // Juntar todo o texto do capítulo
  const fullText = chapterTranscripts.map(t => t.text).join(' ')

  // Contar speakers únicos
  const uniqueSpeakers = [...new Set(groupedByConversation.map(g => g.speaker).filter(Boolean))]

  return (
    <div className="h-full flex flex-col">
      {/* Header do capítulo */}
      <div className="p-4 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
          <span>{formatTime(chapter.start_time)}</span>
          {nextChapterStart && (
            <>
              <span>→</span>
              <span>{formatTime(nextChapterStart)}</span>
            </>
          )}
        </div>
        <h2 className="text-lg font-bold text-blue-400">{chapter.title}</h2>
        <div className="text-xs text-gray-500 mt-1 flex items-center gap-3">
          <span>{chapterTranscripts.length} segmentos | {fullText.length} caracteres</span>
          {hasSpeakers && (
            <span className="flex items-center gap-1">
              🎤 {uniqueSpeakers.length} speakers
              {uniqueSpeakers.map(s => {
                const style = getSpeakerStyle(s)
                return (
                  <span key={s} className={`${style.text} text-xs`}>
                    ({style.name})
                  </span>
                )
              })}
            </span>
          )}
        </div>
      </div>

      {/* Texto do capítulo */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
        {chapterTranscripts.length > 0 ? (
          <div className="space-y-4">
            {/* Modo conversa (se houver speakers) */}
            {hasSpeakers ? (
              <div className="space-y-3">
                {groupedByConversation.map((group, i) => {
                  const style = getSpeakerStyle(group.speaker)
                  const groupText = group.segments.map(s => s.text).join(' ')
                  return (
                    <div
                      key={i}
                      className={`${style.bg} ${style.border} border-l-4 rounded-r-lg p-3`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`${style.text} font-medium text-sm`}>
                          {style.name}
                        </span>
                        <span className="text-xs text-gray-500 font-mono">
                          {formatTime(group.startTime)}
                        </span>
                      </div>
                      <p className="text-gray-200 text-sm leading-relaxed">
                        {groupText}
                      </p>
                    </div>
                  )
                })}
              </div>
            ) : (
              /* Modo texto simples (sem speakers) */
              <div className="bg-gray-800/50 rounded-lg p-4">
                <p className="text-gray-200 leading-relaxed whitespace-pre-wrap">
                  {fullText}
                </p>
              </div>
            )}

            {/* Timeline detalhada */}
            <details className="group">
              <summary className="cursor-pointer text-sm text-gray-400 hover:text-gray-300">
                Ver timeline detalhada ({chapterTranscripts.length} segmentos)
              </summary>
              <div className="mt-2 space-y-1 pl-2 border-l-2 border-gray-700">
                {chapterTranscripts.map((t, i) => (
                  <div key={i} className="flex gap-3 py-1">
                    <span className="text-xs text-gray-500 whitespace-nowrap font-mono">
                      {formatTime(t.start_time)}
                    </span>
                    <p className="text-sm text-gray-400">{t.text}</p>
                  </div>
                ))}
              </div>
            </details>
          </div>
        ) : (
          <div className="text-gray-500 text-center py-8">
            <div className="animate-pulse">A aguardar transcrição deste capítulo...</div>
          </div>
        )}
      </div>
    </div>
  )
}

// Modal para input de cronologia
function CronologiaModal({ isOpen, onClose, onSubmit, initialValue }) {
  const [text, setText] = useState(initialValue || '')
  const [preview, setPreview] = useState([])

  useEffect(() => {
    if (text) {
      setPreview(parseCronologia(text))
    } else {
      setPreview([])
    }
  }, [text])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg max-w-2xl w-full max-h-[80vh] flex flex-col">
        <div className="p-4 border-b border-gray-700 flex justify-between items-center">
          <h2 className="text-lg font-bold">📑 Definir Cronologia</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">✕</button>
        </div>

        <div className="p-4 flex-1 overflow-hidden flex flex-col gap-4">
          <div className="text-sm text-gray-400">
            Cola a cronologia no formato:<br />
            <code className="text-blue-400">00:00:00 - Título do capítulo</code>
          </div>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`00:00:00 - Introdução
00:05:30 - Tema 1
00:15:00 - Tema 2
...`}
            className="flex-1 min-h-[200px] p-3 bg-gray-900 rounded-lg font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />

          {preview.length > 0 && (
            <div className="bg-gray-900 rounded-lg p-3 max-h-[150px] overflow-y-auto">
              <div className="text-xs text-gray-400 mb-2">Preview ({preview.length} capítulos):</div>
              <div className="space-y-1">
                {preview.slice(0, 10).map((ch, i) => (
                  <div key={i} className="text-sm flex gap-2">
                    <span className="text-gray-500 font-mono">{formatTime(ch.start_time)}</span>
                    <span className="text-gray-300">{ch.title}</span>
                  </div>
                ))}
                {preview.length > 10 && (
                  <div className="text-gray-500 text-xs">... e mais {preview.length - 10} capítulos</div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-700 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
          >
            Cancelar
          </button>
          <button
            onClick={() => {
              onSubmit(preview)
              onClose()
            }}
            disabled={preview.length === 0}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg"
          >
            Usar esta cronologia ({preview.length})
          </button>
        </div>
      </div>
    </div>
  )
}

// App Principal
export default function App() {
  const [url, setUrl] = useState('')
  const [session, setSession] = useState(null)
  const [transcripts, setTranscripts] = useState([])
  const [chapters, setChapters] = useState([])
  const [customChapters, setCustomChapters] = useState(null) // Cronologia definida pelo user
  const [selectedChapter, setSelectedChapter] = useState(null)
  const [progress, setProgress] = useState({ current: 0, total: 0, currentChapter: null, chunksProcessed: 0, totalChunks: 0 })
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showCronologiaModal, setShowCronologiaModal] = useState(false)

  const { messages, isConnected } = useWebSocket(
    `ws://${window.location.hostname}:3068/ws`
  )

  // Usar custom chapters se definidos, senão usar os do servidor
  const activeChapters = customChapters || chapters

  // Carregar dados existentes da sessão ao conectar
  const loadExistingSession = useCallback(async () => {
    try {
      const response = await fetch('/api/session/data')
      if (response.ok) {
        const data = await response.json()
        console.log('Loaded existing session:', data.chunks_processed, 'chunks')

        setSession({
          session_id: data.session_id,
          status: data.status,
          video_title: data.video_title,
          video_duration: data.video_duration
        })

        if (data.transcripts && data.transcripts.length > 0) {
          setTranscripts(data.transcripts)
        }

        if (data.chapters && data.chapters.length > 0 && !customChapters) {
          setChapters(data.chapters)
        }

        setProgress({
          current: data.current_time || 0,
          total: data.video_duration || 0,
          chunksProcessed: data.chunks_processed || 0
        })
      }
    } catch (e) {
      // Sem sessão ativa - ok
      console.log('No existing session')
    }
  }, [customChapters])

  // Carregar sessão existente ao montar e ao reconectar
  useEffect(() => {
    loadExistingSession()
  }, [loadExistingSession])

  // Recarregar quando WebSocket reconecta
  useEffect(() => {
    if (isConnected) {
      loadExistingSession()
    }
  }, [isConnected, loadExistingSession])

  // Processar mensagens do WebSocket
  useEffect(() => {
    if (messages.length === 0) return

    const lastMessage = messages[messages.length - 1]

    switch (lastMessage.type) {
      case 'transcript':
        setTranscripts(prev => [...prev, lastMessage.data])
        break
      case 'chapter':
        // Só adicionar se não tivermos custom chapters
        if (!customChapters) {
          setChapters(prev => [...prev, lastMessage.data])
        }
        break
      case 'progress':
        setProgress({
          current: lastMessage.data.current_time,
          total: lastMessage.data.total_duration,
          currentChapter: lastMessage.data.current_chapter,
          chunksProcessed: lastMessage.data.chunks_processed || 0,
          totalChunks: lastMessage.data.total_chunks || 0
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
  }, [messages, customChapters])

  // Calcular contagem de transcrições por capítulo
  const chapterTranscriptCounts = useMemo(() => {
    const counts = {}
    activeChapters.forEach((ch, idx) => {
      const nextStart = idx < activeChapters.length - 1 ? activeChapters[idx + 1].start_time : Infinity
      counts[ch.id] = transcripts.filter(t =>
        t.start_time >= ch.start_time && t.start_time < nextStart
      ).length
    })
    return counts
  }, [activeChapters, transcripts])

  // Encontrar próximo capítulo
  const getNextChapterStart = (chapter) => {
    const idx = activeChapters.findIndex(c => c.id === chapter?.id)
    if (idx >= 0 && idx < activeChapters.length - 1) {
      return activeChapters[idx + 1].start_time
    }
    return null
  }

  // Auto-selecionar primeiro capítulo quando carregar
  useEffect(() => {
    if (activeChapters.length > 0 && !selectedChapter) {
      setSelectedChapter(activeChapters[0])
    }
  }, [activeChapters, selectedChapter])

  const handleStart = async () => {
    if (!url.trim()) return

    setLoading(true)
    setError(null)
    setTranscripts([])
    setChapters([])
    setSelectedChapter(null)
    setStatus({ stage: 'fetching_info', message: 'A iniciar...' })

    try {
      const response = await fetch('/api/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          custom_chapters: customChapters // Enviar cronologia custom se existir
        })
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
      const exportUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = exportUrl
      a.download = 'analysis.md'
      a.click()
      URL.revokeObjectURL(exportUrl)
    } catch (e) {
      setError(e.message)
    }
  }

  const handleClearSession = async () => {
    if (!confirm('Tens a certeza que queres limpar toda a sessão? Isto apaga todas as transcrições.')) {
      return
    }

    try {
      await fetch('/api/session/clear', { method: 'POST' })
      // Resetar todo o estado do frontend
      setSession(null)
      setTranscripts([])
      setChapters([])
      setCustomChapters(null)
      setSelectedChapter(null)
      setProgress({ current: 0, total: 0, currentChapter: null, chunksProcessed: 0, totalChunks: 0 })
      setStatus(null)
      setError(null)
      setUrl('')
    } catch (e) {
      setError(e.message)
    }
  }

  const handleSetCronologia = (chapters) => {
    setCustomChapters(chapters)
    setSelectedChapter(chapters[0] || null)
  }

  const progressPercent = progress.total > 0
    ? Math.min(100, (progress.current / progress.total) * 100)
    : 0

  return (
    <div className="min-h-screen flex flex-col bg-gray-900 text-gray-100">
      {/* Header */}
      <header className="bg-gray-800 p-4 shadow-lg">
        <div className="max-w-7xl mx-auto flex items-center gap-4">
          <h1 className="text-xl font-bold">📑 Despolariza Transcriber</h1>

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

            <button
              onClick={() => setShowCronologiaModal(true)}
              disabled={session?.status === 'running'}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded-lg font-medium transition"
              title="Definir cronologia manual"
            >
              📑 {customChapters ? `(${customChapters.length})` : ''}
            </button>

            {!session || session.status !== 'running' ? (
              <button
                onClick={handleStart}
                disabled={loading || !url.trim()}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg font-medium transition"
              >
                {loading ? 'A iniciar...' : 'Transcrever'}
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="px-6 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-medium transition"
              >
                Parar
              </button>
            )}

            {transcripts.length > 0 && (
              <>
                <button
                  onClick={handleExport}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition"
                  title="Exportar Markdown"
                >
                  📥
                </button>
                <button
                  onClick={handleClearSession}
                  disabled={session?.status === 'running'}
                  className="px-4 py-2 bg-red-900 hover:bg-red-800 disabled:bg-gray-600 rounded-lg transition"
                  title="Limpar sessão"
                >
                  🗑️
                </button>
              </>
            )}
          </div>

          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
               title={isConnected ? 'Conectado' : 'Desconectado'} />
        </div>

        {/* Custom chapters indicator */}
        {customChapters && (
          <div className="max-w-7xl mx-auto mt-2">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-purple-400">📑 Cronologia manual: {customChapters.length} capítulos</span>
              <button
                onClick={() => {
                  setCustomChapters(null)
                  setSelectedChapter(null)
                }}
                className="text-gray-400 hover:text-red-400 text-xs"
              >
                (limpar)
              </button>
            </div>
          </div>
        )}

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
                ({progress.chunksProcessed}{progress.totalChunks ? ` / ${progress.totalChunks}` : ''})
              </span>
            </div>
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
        <div className="bg-gray-800/50 px-4 py-2 border-b border-gray-700">
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
        {/* Chapters sidebar - CRONOLOGIA */}
        <div className="w-80 bg-gray-900 border-r border-gray-700 flex flex-col">
          <div className="p-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
            <h2 className="font-medium">
              📑 CRONOLOGIA
              {customChapters && <span className="text-purple-400 text-xs ml-1">(manual)</span>}
            </h2>
            <span className="text-sm text-gray-400">{activeChapters.length} temas</span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {activeChapters.length > 0 ? (
              activeChapters.map((ch, idx) => (
                <ChapterListItem
                  key={ch.id}
                  chapter={ch}
                  isActive={selectedChapter?.id === ch.id}
                  isProcessing={progress.currentChapter === ch.title}
                  transcriptCount={chapterTranscriptCounts[ch.id] || 0}
                  onClick={() => setSelectedChapter(ch)}
                />
              ))
            ) : (
              <div className="text-gray-500 text-center py-8 text-sm">
                <button
                  onClick={() => setShowCronologiaModal(true)}
                  className="text-purple-400 hover:text-purple-300 underline"
                >
                  Clica para definir cronologia
                </button>
                <div className="mt-2 text-gray-600">ou introduz URL para auto-detetar</div>
              </div>
            )}
          </div>

          {/* Stats no fundo */}
          {transcripts.length > 0 && (
            <div className="p-3 bg-gray-800 border-t border-gray-700 text-xs text-gray-400">
              <div>Total: {transcripts.length} segmentos</div>
              <div>{transcripts.reduce((acc, t) => acc + t.text.length, 0).toLocaleString()} caracteres</div>
            </div>
          )}
        </div>

        {/* Transcription panel */}
        <div className="flex-1 flex flex-col bg-gray-900">
          <ChapterTranscriptPanel
            chapter={selectedChapter}
            transcripts={transcripts}
            nextChapterStart={getNextChapterStart(selectedChapter)}
          />
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-gray-800 p-2 text-center text-xs text-gray-500">
        Despolariza Transcriber v0.3.0 | Transcrição por capítulos usando Whisper
      </footer>

      {/* Modal de cronologia */}
      <CronologiaModal
        isOpen={showCronologiaModal}
        onClose={() => setShowCronologiaModal(false)}
        onSubmit={handleSetCronologia}
        initialValue=""
      />
    </div>
  )
}
