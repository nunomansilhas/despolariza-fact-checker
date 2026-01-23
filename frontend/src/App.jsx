import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

// WebSocket hook
function useWebSocket(url) {
  const [messages, setMessages] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectRef = useRef(0)

  const connect = useCallback(() => {
    const ws = new WebSocket(url)
    ws.onopen = () => {
      setIsConnected(true)
      reconnectRef.current = 0
    }
    ws.onmessage = (e) => setMessages(prev => [...prev, JSON.parse(e.data)])
    ws.onclose = () => {
      setIsConnected(false)
      const delay = Math.min(1000 * Math.pow(2, reconnectRef.current++), 10000)
      setTimeout(connect, delay)
    }
    wsRef.current = ws
  }, [url])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  return { messages, isConnected }
}

// Formatar tempo
const formatTime = (s) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return h > 0 ? `${h}:${m.toString().padStart(2,'0')}:${sec.toString().padStart(2,'0')}` : `${m}:${sec.toString().padStart(2,'0')}`
}

// Cores dos speakers
const SPEAKERS = {
  'SPEAKER_00': { color: 'border-blue-500', bg: 'bg-blue-500/10', name: 'Locutor A' },
  'SPEAKER_01': { color: 'border-green-500', bg: 'bg-green-500/10', name: 'Locutor B' },
  'SPEAKER_02': { color: 'border-purple-500', bg: 'bg-purple-500/10', name: 'Locutor C' },
  'SPEAKER_03': { color: 'border-orange-500', bg: 'bg-orange-500/10', name: 'Locutor D' },
}
const getSpeaker = (id) => SPEAKERS[id] || { color: 'border-gray-500', bg: 'bg-gray-500/10', name: id || 'Desconhecido' }

// Parser de cronologia
function parseCronologia(text) {
  return text.trim().split('\n').map((line, i) => {
    const match = line.trim().match(/^(\d{1,2}:\d{2}:\d{2})\s*[-–—]?\s*(.+)$/)
    if (!match) return null
    const [, ts, title] = match
    const parts = ts.split(':').map(Number)
    return { id: `ch_${i}`, title: title.trim(), start_time: parts[0]*3600 + parts[1]*60 + parts[2] }
  }).filter(Boolean)
}

// Componente principal
export default function App() {
  const [url, setUrl] = useState('')
  const [session, setSession] = useState(null)
  const [transcripts, setTranscripts] = useState([])
  const [chapters, setChapters] = useState([])
  const [progress, setProgress] = useState({ current: 0, total: 0, chunks: 0, totalChunks: 0 })
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showCronologia, setShowCronologia] = useState(false)
  const [cronologiaText, setCronologiaText] = useState('')
  const [activeTab, setActiveTab] = useState('conversa') // conversa | capitulos | factos
  const [selectedChapter, setSelectedChapter] = useState(null)

  const scrollRef = useRef(null)
  const { messages, isConnected } = useWebSocket(`ws://${window.location.hostname}:3068/ws`)

  // Carregar sessão existente
  useEffect(() => {
    fetch('/api/session/data').then(r => r.ok ? r.json() : null).then(data => {
      if (data) {
        setSession({ video_title: data.video_title, status: data.status })
        setTranscripts(data.transcripts || [])
        setChapters(data.chapters || [])
        setProgress({ current: data.current_time || 0, total: data.video_duration || 0, chunks: data.chunks_processed || 0 })
      }
    }).catch(() => {})
  }, [])

  // Processar mensagens WebSocket
  useEffect(() => {
    if (!messages.length) return
    const msg = messages[messages.length - 1]
    if (msg.type === 'transcript') setTranscripts(prev => [...prev, msg.data])
    if (msg.type === 'chapter') setChapters(prev => [...prev, msg.data])
    if (msg.type === 'progress') setProgress({
      current: msg.data.current_time,
      total: msg.data.total_duration,
      chunks: msg.data.chunks_processed,
      totalChunks: msg.data.total_chunks
    })
    if (msg.type === 'status') setStatus(msg.data)
    if (msg.type === 'complete') { setSession(s => s ? {...s, status: 'completed'} : null); setStatus(null) }
    if (msg.type === 'error') { setError(msg.message || msg.data); setStatus(null) }
  }, [messages])

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current && session?.status === 'running') {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [transcripts, session?.status])

  // Agrupar por speaker
  const conversation = useMemo(() => {
    const groups = []
    let current = null

    for (const t of transcripts) {
      const segs = t.segments?.length ? t.segments : [{ text: t.text, start: t.start_time, speaker: null }]
      for (const seg of segs) {
        if (!current || current.speaker !== seg.speaker) {
          current = { speaker: seg.speaker, texts: [], startTime: seg.start }
          groups.push(current)
        }
        current.texts.push(seg.text)
      }
    }
    return groups
  }, [transcripts])

  // Filtrar por capítulo
  const filteredConversation = useMemo(() => {
    if (!selectedChapter) return conversation
    const chIdx = chapters.findIndex(c => c.id === selectedChapter.id)
    const nextStart = chIdx < chapters.length - 1 ? chapters[chIdx + 1].start_time : Infinity
    return conversation.filter(g => g.startTime >= selectedChapter.start_time && g.startTime < nextStart)
  }, [conversation, selectedChapter, chapters])

  // Handlers
  const handleStart = async () => {
    if (!url.trim()) return
    setLoading(true)
    setError(null)
    setTranscripts([])
    setStatus({ stage: 'fetching_info', message: 'A iniciar...' })

    const customChapters = cronologiaText ? parseCronologia(cronologiaText) : null
    if (customChapters?.length) setChapters(customChapters)

    try {
      const res = await fetch('/api/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, custom_chapters: customChapters })
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Erro')
      const data = await res.json()
      setSession(data)
      setProgress({ current: 0, total: data.video_duration || 0, chunks: 0, totalChunks: 0 })
    } catch (e) {
      setError(e.message)
      setStatus(null)
    }
    setLoading(false)
  }

  const handleStop = () => fetch('/api/session/stop', { method: 'POST' }).then(() => {
    setSession(s => s ? {...s, status: 'stopped'} : null)
    setStatus(null)
  })

  const handleClear = async () => {
    if (!confirm('Limpar tudo?')) return
    await fetch('/api/session/clear', { method: 'POST' })
    setSession(null)
    setTranscripts([])
    setChapters([])
    setProgress({ current: 0, total: 0, chunks: 0, totalChunks: 0 })
    setStatus(null)
    setUrl('')
    setSelectedChapter(null)
  }

  const progressPct = progress.total > 0 ? (progress.current / progress.total) * 100 : 0

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-100">
      {/* Header compacto */}
      <header className="bg-gray-900 border-b border-gray-800 p-3">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg">🎙️ Despolariza</span>

          <input
            type="text"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleStart()}
            placeholder="URL do YouTube..."
            disabled={session?.status === 'running'}
            className="flex-1 px-3 py-1.5 bg-gray-800 rounded border border-gray-700 focus:border-blue-500 focus:outline-none text-sm"
          />

          <button
            onClick={() => setShowCronologia(!showCronologia)}
            className={`px-3 py-1.5 rounded text-sm ${cronologiaText ? 'bg-purple-600' : 'bg-gray-800 hover:bg-gray-700'}`}
            title="Definir cronologia"
          >
            📑
          </button>

          {session?.status === 'running' ? (
            <button onClick={handleStop} className="px-4 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm font-medium">
              Parar
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={loading || !url.trim()}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 rounded text-sm font-medium"
            >
              {loading ? '...' : 'Iniciar'}
            </button>
          )}

          {transcripts.length > 0 && (
            <button onClick={handleClear} className="p-1.5 text-gray-500 hover:text-red-400" title="Limpar">
              🗑️
            </button>
          )}

          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
        </div>

        {/* Cronologia input */}
        {showCronologia && (
          <div className="mt-3 p-3 bg-gray-800 rounded">
            <textarea
              value={cronologiaText}
              onChange={e => setCronologiaText(e.target.value)}
              placeholder="00:00:00 - Introdução&#10;00:10:00 - Tema 1&#10;..."
              className="w-full h-24 p-2 bg-gray-900 rounded text-sm font-mono resize-none"
            />
            <div className="text-xs text-gray-500 mt-1">
              {parseCronologia(cronologiaText).length} capítulos detectados
            </div>
          </div>
        )}

        {/* Progresso compacto */}
        {session && progress.total > 0 && (
          <div className="mt-3 flex items-center gap-3">
            <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 transition-all" style={{ width: `${progressPct}%` }} />
            </div>
            <span className="text-xs text-gray-500">
              {formatTime(progress.current)} / {formatTime(progress.total)}
              {progress.chunks > 0 && ` • ${progress.chunks} chunks`}
            </span>
          </div>
        )}

        {/* Status */}
        {status && (
          <div className="mt-2 text-sm text-gray-400 flex items-center gap-2">
            <div className="w-3 h-3 border-2 border-gray-500 border-t-white rounded-full animate-spin" />
            {status.message}
          </div>
        )}
      </header>

      {/* Error */}
      {error && (
        <div className="bg-red-900/50 text-red-300 px-4 py-2 text-sm flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Video info */}
      {session?.video_title && (
        <div className="px-4 py-2 bg-gray-900/50 border-b border-gray-800 text-sm text-gray-400 truncate">
          📺 {session.video_title}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-800 bg-gray-900/50">
        {['conversa', 'capitulos'].map(tab => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); if (tab === 'conversa') setSelectedChapter(null) }}
            className={`px-4 py-2 text-sm font-medium transition ${
              activeTab === tab ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab === 'conversa' ? '💬 Conversa' : '📑 Capítulos'}
          </button>
        ))}
        {selectedChapter && (
          <div className="ml-auto px-4 py-2 text-sm text-purple-400 flex items-center gap-2">
            Filtrado: {selectedChapter.title}
            <button onClick={() => setSelectedChapter(null)} className="hover:text-white">✕</button>
          </div>
        )}
      </div>

      {/* Main content */}
      <main ref={scrollRef} className="flex-1 overflow-y-auto">
        {activeTab === 'conversa' ? (
          <div className="max-w-4xl mx-auto p-4 space-y-3">
            {filteredConversation.length === 0 ? (
              <div className="text-center text-gray-600 py-20">
                {transcripts.length === 0 ? (
                  <>
                    <div className="text-4xl mb-3">🎙️</div>
                    <div>Cola um URL do YouTube para começar</div>
                  </>
                ) : (
                  <div>Nenhum conteúdo neste capítulo</div>
                )}
              </div>
            ) : (
              filteredConversation.map((group, i) => {
                const speaker = getSpeaker(group.speaker)
                return (
                  <div key={i} className={`border-l-2 ${speaker.color} ${speaker.bg} rounded-r-lg p-3`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm">{speaker.name}</span>
                      <span className="text-xs text-gray-500">{formatTime(group.startTime)}</span>
                    </div>
                    <p className="text-gray-200 text-sm leading-relaxed">
                      {group.texts.join(' ')}
                    </p>
                  </div>
                )
              })
            )}
          </div>
        ) : (
          <div className="max-w-4xl mx-auto p-4">
            {chapters.length === 0 ? (
              <div className="text-center text-gray-600 py-20">
                <div className="text-4xl mb-3">📑</div>
                <div>Sem capítulos definidos</div>
                <button
                  onClick={() => setShowCronologia(true)}
                  className="mt-3 text-purple-400 hover:text-purple-300 underline text-sm"
                >
                  Adicionar cronologia
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {chapters.map((ch, i) => {
                  const nextStart = i < chapters.length - 1 ? chapters[i + 1].start_time : progress.total
                  const chunkCount = transcripts.filter(t =>
                    t.start_time >= ch.start_time && t.start_time < nextStart
                  ).length
                  const isActive = selectedChapter?.id === ch.id

                  return (
                    <div
                      key={ch.id}
                      onClick={() => { setSelectedChapter(ch); setActiveTab('conversa') }}
                      className={`p-3 rounded-lg cursor-pointer transition flex items-center gap-3 ${
                        isActive ? 'bg-blue-600' : 'bg-gray-800/50 hover:bg-gray-800'
                      }`}
                    >
                      <span className="text-xs font-mono text-gray-500 w-16">
                        {formatTime(ch.start_time)}
                      </span>
                      <span className="flex-1 font-medium">{ch.title}</span>
                      {chunkCount > 0 && (
                        <span className="text-xs text-gray-500">{chunkCount} seg.</span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer stats */}
      {transcripts.length > 0 && (
        <footer className="bg-gray-900 border-t border-gray-800 px-4 py-2 text-xs text-gray-500 flex justify-between">
          <span>{transcripts.length} segmentos • {transcripts.reduce((a, t) => a + t.text.length, 0).toLocaleString()} caracteres</span>
          <span>{conversation.filter(g => g.speaker).length > 0 ? `${new Set(conversation.map(g => g.speaker)).size} locutores` : 'Sem diarização'}</span>
        </footer>
      )}
    </div>
  )
}
