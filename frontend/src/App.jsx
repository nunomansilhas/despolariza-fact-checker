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

// Cores dos speakers - estilo chat (nomes configuráveis)
const DEFAULT_SPEAKERS = {
  'SPEAKER_00': { color: 'bg-blue-600', text: 'text-white', name: 'Entrevistador', side: 'left' },
  'SPEAKER_01': { color: 'bg-green-600', text: 'text-white', name: 'Convidado', side: 'right' },
  'SPEAKER_02': { color: 'bg-purple-600', text: 'text-white', name: 'Locutor C', side: 'left' },
  'SPEAKER_03': { color: 'bg-orange-600', text: 'text-white', name: 'Locutor D', side: 'right' },
}

// Componente de "a escrever..." com animação
function TypingIndicator({ speaker }) {
  return (
    <div className={`flex ${speaker.side === 'right' ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] flex flex-col ${speaker.side === 'right' ? 'items-end' : 'items-start'}`}>
        <div className={`flex items-center gap-2 mb-1 ${speaker.side === 'right' ? 'flex-row-reverse' : ''}`}>
          <span className={`text-xs font-bold ${speaker.color} ${speaker.text} px-2 py-0.5 rounded-full animate-pulse`}>
            {speaker.name}
          </span>
        </div>
        <div className={`px-4 py-3 rounded-2xl ${speaker.color} ${speaker.side === 'right' ? 'rounded-br-md' : 'rounded-bl-md'}`}>
          <div className="flex gap-1">
            <span className="w-2 h-2 bg-white/70 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-2 h-2 bg-white/70 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-2 h-2 bg-white/70 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      </div>
    </div>
  )
}

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
  const [activeTab, setActiveTab] = useState('conversa') // conversa | capitulos | analise
  const [selectedChapter, setSelectedChapter] = useState(null)
  const [analyses, setAnalyses] = useState([]) // Análises dos capítulos
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisProgress, setAnalysisProgress] = useState({ current: 0, total: 0 })
  const [claimResults, setClaimResults] = useState({}) // { "claim_text": { status, verdict, explanation } }
  const [verifyingClaim, setVerifyingClaim] = useState(null) // claim being verified
  const [speakerNames, setSpeakerNames] = useState(() => {
    // Carregar nomes guardados do localStorage
    const saved = localStorage.getItem('speakerNames')
    return saved ? JSON.parse(saved) : {
      speaker0: 'Tomás',
      speaker0_context: 'Host do podcast Despolariza-te. Faz perguntas diretas e provocadoras. Estilo informal, tuteia os convidados. Interrompe para clarificar ou desafiar pontos.',
      speaker1: 'Convidado',
      speaker1_context: 'Convidado do podcast. Dá respostas longas e elaboradas. Partilha opiniões, experiências e análises detalhadas.'
    }
  })
  const [showSpeakerConfig, setShowSpeakerConfig] = useState(false)
  const [identifiedSpeakers, setIdentifiedSpeakers] = useState([]) // Segmentos com speakers identificados por AI
  const [identifyingProgress, setIdentifyingProgress] = useState(null) // { current, total }
  const [showLocalAudio, setShowLocalAudio] = useState(false)
  const [localAudioPath, setLocalAudioPath] = useState(() => localStorage.getItem('localAudioPath') || '')
  const [localAudioTitle, setLocalAudioTitle] = useState('')

  // Polígrafo state
  const [poligrafoResult, setPoligrafoResult] = useState(null)
  const [poligrafoProgress, setPoligrafoProgress] = useState(null) // { stage, current, total }
  const [showPoligrafo, setShowPoligrafo] = useState(false)

  const scrollRef = useRef(null)
  const { messages, isConnected } = useWebSocket(`ws://${window.location.hostname}:3068/ws`)

  // Função para obter info do speaker com nomes customizados
  const getSpeaker = useCallback((id, speakerName = null) => {
    // Se temos nome direto do AI, usar esse
    if (speakerName) {
      if (speakerName === 'AMBOS') {
        return { color: 'bg-yellow-600', text: 'text-white', name: '🗣️ Ambos', side: 'center' }
      }
      if (speakerName === speakerNames.speaker0) {
        return { ...DEFAULT_SPEAKERS['SPEAKER_00'], name: speakerName }
      }
      if (speakerName === speakerNames.speaker1) {
        return { ...DEFAULT_SPEAKERS['SPEAKER_01'], name: speakerName }
      }
      return { color: 'bg-gray-600', text: 'text-white', name: speakerName, side: 'left' }
    }

    // Fallback para IDs de speaker
    if (id === 'AMBOS') {
      return { color: 'bg-yellow-600', text: 'text-white', name: '🗣️ Ambos', side: 'center' }
    }
    const base = DEFAULT_SPEAKERS[id] || { color: 'bg-gray-600', text: 'text-white', name: id || 'Desconhecido', side: 'left' }
    if (id === 'SPEAKER_00') return { ...base, name: speakerNames.speaker0 || base.name }
    if (id === 'SPEAKER_01') return { ...base, name: speakerNames.speaker1 || base.name }
    return base
  }, [speakerNames])

  // Guardar nomes no localStorage
  useEffect(() => {
    localStorage.setItem('speakerNames', JSON.stringify(speakerNames))
  }, [speakerNames])

  // Carregar sessão existente e polling para updates
  const fetchSessionData = useCallback(() => {
    fetch('/api/session/data').then(r => r.ok ? r.json() : null).then(data => {
      if (data) {
        setSession({ video_title: data.video_title, status: data.status })
        setTranscripts(data.transcripts || [])
        setChapters(data.chapters || [])
        setProgress({ current: data.current_time || 0, total: data.video_duration || 0, chunks: data.chunks_processed || 0 })
      }
    }).catch(() => {})
  }, [])

  // Carregar dados iniciais
  useEffect(() => {
    fetchSessionData()
  }, [fetchSessionData])

  // Polling como fallback quando sessão está a correr (a cada 2s)
  useEffect(() => {
    if (session?.status !== 'running') return
    const interval = setInterval(fetchSessionData, 2000)
    return () => clearInterval(interval)
  }, [session?.status, fetchSessionData])

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
    if (msg.type === 'analysis_progress') setAnalysisProgress({ current: msg.data.current, total: msg.data.total })
    if (msg.type === 'analysis_complete') { setAnalyses(msg.data.chapters); setAnalyzing(false); setActiveTab('analise') }
    if (msg.type === 'speaker_identification_progress') setIdentifyingProgress({ current: msg.data.processed, total: msg.data.total })
    if (msg.type === 'speaker_identification_complete') {
      setIdentifiedSpeakers(msg.data.chapters)
      setIdentifyingProgress(null)
    }
    if (msg.type === 'poligrafo_progress') setPoligrafoProgress(msg.data)
    if (msg.type === 'poligrafo_complete') {
      setPoligrafoResult(msg.data)
      setPoligrafoProgress(null)
      setShowPoligrafo(true)
    }
  }, [messages])

  // Auto-scroll suave
  useEffect(() => {
    if (scrollRef.current && session?.status === 'running') {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [transcripts, session?.status])

  // Agrupar por speaker - usar AI-identified se disponível, senão voice diarization
  const conversation = useMemo(() => {
    // Se temos speakers identificados por AI, usar esses
    if (identifiedSpeakers.length > 0) {
      const groups = []
      for (const chapter of identifiedSpeakers) {
        for (const seg of chapter.segments || []) {
          // Mapear nome do speaker para ID
          let speakerId = null
          if (seg.speaker === speakerNames.speaker0) speakerId = 'SPEAKER_00'
          else if (seg.speaker === speakerNames.speaker1) speakerId = 'SPEAKER_01'
          else if (seg.speaker === 'AMBOS') speakerId = 'AMBOS'

          groups.push({
            speaker: speakerId,
            speakerName: seg.speaker, // Nome direto do AI
            texts: [seg.text],
            startTime: 0, // AI não dá timestamps exatos
            chapter: chapter.chapter_title
          })
        }
      }
      return groups
    }

    // Fallback: voice diarization ou sem diarização
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
  }, [transcripts, identifiedSpeakers, speakerNames])

  // Filtrar por capítulo
  const filteredConversation = useMemo(() => {
    if (!selectedChapter) return conversation
    const chIdx = chapters.findIndex(c => c.id === selectedChapter.id)
    const nextStart = chIdx < chapters.length - 1 ? chapters[chIdx + 1].start_time : Infinity
    return conversation.filter(g => g.startTime >= selectedChapter.start_time && g.startTime < nextStart)
  }, [conversation, selectedChapter, chapters])

  // Handlers
  const handleStart = async () => {
    // Pode usar URL do YouTube OU áudio local
    if (!url.trim() && !localAudioPath.trim()) return
    setLoading(true)
    setError(null)
    setTranscripts([])
    setIdentifiedSpeakers([])
    setStatus({ stage: 'fetching_info', message: 'A iniciar...' })

    const customChapters = cronologiaText ? parseCronologia(cronologiaText) : null
    if (customChapters?.length) setChapters(customChapters)

    // Guardar path do áudio local para futuras sessões
    if (localAudioPath) {
      localStorage.setItem('localAudioPath', localAudioPath)
    }

    try {
      const res = await fetch('/api/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url || '',
          custom_chapters: customChapters,
          local_audio: localAudioPath || null,
          video_title: localAudioTitle || null
        })
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
    setAnalyses([])
    setClaimResults({})
  }

  const handleAnalyze = async () => {
    setAnalyzing(true)
    setAnalysisProgress({ current: 0, total: chapters.length || 1 })
    setError(null)

    try {
      const res = await fetch('/api/analyze', { method: 'POST' })
      if (!res.ok) throw new Error((await res.json()).detail || 'Erro na análise')
      const data = await res.json()
      setAnalyses(data.analyses || [])
      setActiveTab('analise')
    } catch (e) {
      setError(e.message)
    }
    setAnalyzing(false)
  }

  const handleIdentifySpeakers = async () => {
    setIdentifyingProgress({ current: 0, total: chapters.length || 1 })
    setError(null)

    try {
      const res = await fetch('/api/identify-speakers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          speaker_names: [speakerNames.speaker0, speakerNames.speaker1]
        })
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Erro na identificação')
      const data = await res.json()
      setIdentifiedSpeakers(data.chapters || [])
    } catch (e) {
      setError(e.message)
    }
    setIdentifyingProgress(null)
  }

  const handlePoligrafo = async () => {
    setPoligrafoProgress({ stage: 'starting', current: 0, total: 3 })
    setError(null)

    try {
      const res = await fetch('/api/poligrafo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          speakers: [
            { name: speakerNames.speaker0, context: speakerNames.speaker0_context || '' },
            { name: speakerNames.speaker1, context: speakerNames.speaker1_context || '' }
          ]
        })
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Erro no Polígrafo')
      const data = await res.json()
      setPoligrafoResult(data)
      setShowPoligrafo(true)
    } catch (e) {
      setError(e.message)
    }
    setPoligrafoProgress(null)
  }

  const handleVerifyClaim = async (claim, chapterTitle) => {
    const claimKey = `${chapterTitle}::${claim}`
    setVerifyingClaim(claimKey)
    setClaimResults(prev => ({ ...prev, [claimKey]: { status: 'verifying' } }))

    try {
      const res = await fetch('/api/fact-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim, context: chapterTitle })
      })

      if (!res.ok) throw new Error((await res.json()).detail || 'Erro na verificação')
      const data = await res.json()

      setClaimResults(prev => ({
        ...prev,
        [claimKey]: {
          status: 'done',
          verdict: data.verdict, // true, false, partial, inconclusive
          explanation: data.explanation
        }
      }))
    } catch (e) {
      setClaimResults(prev => ({
        ...prev,
        [claimKey]: { status: 'error', error: e.message }
      }))
    }
    setVerifyingClaim(null)
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

          <button
            onClick={() => setShowSpeakerConfig(!showSpeakerConfig)}
            className={`px-3 py-1.5 rounded text-sm ${showSpeakerConfig ? 'bg-green-600' : 'bg-gray-800 hover:bg-gray-700'}`}
            title="Configurar speakers"
          >
            👥
          </button>

          <button
            onClick={() => setShowLocalAudio(!showLocalAudio)}
            className={`px-3 py-1.5 rounded text-sm ${localAudioPath ? 'bg-orange-600' : 'bg-gray-800 hover:bg-gray-700'}`}
            title="Usar áudio local"
          >
            📁
          </button>

          {session?.status === 'running' ? (
            <button onClick={handleStop} className="px-4 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm font-medium">
              Parar
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={loading || (!url.trim() && !localAudioPath.trim())}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 rounded text-sm font-medium"
            >
              {loading ? '...' : (localAudioPath ? '▶️ Local' : 'Iniciar')}
            </button>
          )}

          {transcripts.length > 0 && session?.status !== 'running' && (
            <button
              onClick={handleIdentifySpeakers}
              disabled={identifyingProgress !== null}
              className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 rounded text-sm font-medium"
              title="Identificar quem fala usando AI"
            >
              {identifyingProgress ? `🔄 ${identifyingProgress.current}/${identifyingProgress.total}` : '🎙️ ID Speakers'}
            </button>
          )}

          {transcripts.length > 0 && session?.status !== 'running' && (
            <button
              onClick={handlePoligrafo}
              disabled={poligrafoProgress !== null}
              className="px-3 py-1.5 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 rounded text-sm font-medium"
              title="Análise completa: Separar speakers, extrair claims, verificar factos"
            >
              {poligrafoProgress ? `🔄 ${poligrafoProgress.stage}` : '🔍 Polígrafo'}
            </button>
          )}

          {transcripts.length > 0 && session?.status !== 'running' && (
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 rounded text-sm font-medium"
              title="Analisar capítulos"
            >
              {analyzing ? `🔄 ${analysisProgress.current}/${analysisProgress.total}` : '🧠 Analisar'}
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

        {/* Speaker config */}
        {showSpeakerConfig && (
          <div className="mt-3 p-3 bg-gray-800 rounded">
            <div className="text-sm font-medium mb-2 text-gray-300">👥 Configuração dos Speakers</div>
            <div className="grid grid-cols-2 gap-4">
              {/* Speaker 1 - Entrevistador */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-blue-600 rounded-full"></div>
                  <label className="text-xs text-gray-400 font-medium">ENTREVISTADOR</label>
                </div>
                <input
                  type="text"
                  value={speakerNames.speaker0}
                  onChange={e => setSpeakerNames(prev => ({ ...prev, speaker0: e.target.value }))}
                  placeholder="Nome (ex: Tomás)"
                  className="w-full px-3 py-1.5 bg-gray-900 rounded border border-blue-600/50 focus:border-blue-500 focus:outline-none text-sm"
                />
                <textarea
                  value={speakerNames.speaker0_context || ''}
                  onChange={e => setSpeakerNames(prev => ({ ...prev, speaker0_context: e.target.value }))}
                  placeholder="Contexto: quem é, estilo de falar, características..."
                  rows={3}
                  className="w-full px-3 py-1.5 bg-gray-900 rounded border border-gray-700 focus:border-blue-500 focus:outline-none text-xs resize-none"
                />
              </div>
              {/* Speaker 2 - Convidado */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-green-600 rounded-full"></div>
                  <label className="text-xs text-gray-400 font-medium">CONVIDADO</label>
                </div>
                <input
                  type="text"
                  value={speakerNames.speaker1}
                  onChange={e => setSpeakerNames(prev => ({ ...prev, speaker1: e.target.value }))}
                  placeholder="Nome (ex: Daniel Oliveira)"
                  className="w-full px-3 py-1.5 bg-gray-900 rounded border border-green-600/50 focus:border-green-500 focus:outline-none text-sm"
                />
                <textarea
                  value={speakerNames.speaker1_context || ''}
                  onChange={e => setSpeakerNames(prev => ({ ...prev, speaker1_context: e.target.value }))}
                  placeholder="Contexto: quem é, profissão, posições políticas, estilo..."
                  rows={3}
                  className="w-full px-3 py-1.5 bg-gray-900 rounded border border-gray-700 focus:border-green-500 focus:outline-none text-xs resize-none"
                />
              </div>
            </div>
            <div className="text-xs text-gray-500 mt-2">
              💡 O contexto ajuda o AI a identificar quem está a falar baseado no conteúdo
            </div>
          </div>
        )}

        {/* Local audio config */}
        {showLocalAudio && (
          <div className="mt-3 p-3 bg-gray-800 rounded">
            <div className="text-sm font-medium mb-2 text-gray-300">📁 Áudio Local</div>
            <div className="space-y-2">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Caminho do ficheiro (mp3, wav, etc)</label>
                <input
                  type="text"
                  value={localAudioPath}
                  onChange={e => setLocalAudioPath(e.target.value)}
                  placeholder="C:\Users\...\audio.mp3 ou /home/.../audio.wav"
                  className="w-full px-3 py-1.5 bg-gray-900 rounded border border-orange-600/50 focus:border-orange-500 focus:outline-none text-sm font-mono"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Título (opcional)</label>
                <input
                  type="text"
                  value={localAudioTitle}
                  onChange={e => setLocalAudioTitle(e.target.value)}
                  placeholder="Nome do podcast/episódio"
                  className="w-full px-3 py-1.5 bg-gray-900 rounded border border-gray-700 focus:border-orange-500 focus:outline-none text-sm"
                />
              </div>
            </div>
            <div className="text-xs text-gray-500 mt-2">
              💡 Usa isto para evitar descarregar o mesmo vídeo várias vezes. O caminho é guardado.
            </div>
            {localAudioPath && (
              <button
                onClick={() => { setLocalAudioPath(''); setLocalAudioTitle(''); localStorage.removeItem('localAudioPath') }}
                className="mt-2 text-xs text-red-400 hover:text-red-300"
              >
                ✕ Limpar áudio local
              </button>
            )}
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
        {[
          { id: 'conversa', label: '💬 Conversa' },
          { id: 'capitulos', label: '📑 Capítulos' },
          { id: 'analise', label: '🧠 Análise', badge: analyses.length }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); if (tab.id === 'conversa') setSelectedChapter(null) }}
            className={`px-4 py-2 text-sm font-medium transition flex items-center gap-1 ${
              activeTab === tab.id ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab.label}
            {tab.badge > 0 && <span className="text-xs bg-green-600 px-1.5 rounded-full">{tab.badge}</span>}
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
        {activeTab === 'conversa' && (
          <div className="max-w-4xl mx-auto p-4 space-y-4">
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
              <>
                {filteredConversation.map((group, i) => {
                  const speaker = getSpeaker(group.speaker, group.speakerName)
                  const isRight = speaker.side === 'right'
                  const isCenter = speaker.side === 'center'

                  return (
                    <div
                      key={i}
                      className={`flex ${isCenter ? 'justify-center' : isRight ? 'justify-end' : 'justify-start'} animate-fadeIn`}
                    >
                      <div className={`max-w-[75%] ${isCenter ? 'items-center' : isRight ? 'items-end' : 'items-start'} flex flex-col`}>
                        {/* Nome e tempo/capítulo */}
                        <div className={`flex items-center gap-2 mb-1 ${isRight ? 'flex-row-reverse' : ''}`}>
                          <span className={`text-xs font-bold ${speaker.color} ${speaker.text} px-2 py-0.5 rounded-full`}>
                            {speaker.name}
                          </span>
                          {group.startTime > 0 && (
                            <span className="text-xs text-gray-500">{formatTime(group.startTime)}</span>
                          )}
                          {group.chapter && (
                            <span className="text-xs text-purple-400">📑 {group.chapter}</span>
                          )}
                        </div>

                        {/* Balão de mensagem */}
                        <div
                          className={`
                            relative px-4 py-2 rounded-2xl
                            ${isCenter
                              ? `${speaker.color} ${speaker.text} rounded-lg`
                              : isRight
                                ? `${speaker.color} ${speaker.text} rounded-br-md`
                                : `${speaker.color} ${speaker.text} rounded-bl-md`
                            }
                          `}
                        >
                          <p className="text-sm leading-relaxed">
                            {group.texts.join(' ')}
                          </p>
                        </div>
                      </div>
                    </div>
                  )
                })}

                {/* Indicador "a escrever..." enquanto transcreve */}
                {session?.status === 'running' && status?.stage === 'transcribing' && (
                  <TypingIndicator speaker={
                    // Alternar lado baseado no último speaker
                    getSpeaker(
                      filteredConversation.length > 0
                        ? (filteredConversation[filteredConversation.length - 1].speaker === 'SPEAKER_00' ? 'SPEAKER_01' : 'SPEAKER_00')
                        : 'SPEAKER_00'
                    )
                  } />
                )}
              </>
            )}
          </div>
        )}

        {activeTab === 'capitulos' && (
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

        {activeTab === 'analise' && (
          <div className="max-w-4xl mx-auto p-4">
            {analyses.length === 0 ? (
              <div className="text-center text-gray-600 py-20">
                <div className="text-4xl mb-3">🧠</div>
                <div>Sem análise disponível</div>
                {transcripts.length > 0 && session?.status !== 'running' && (
                  <button
                    onClick={handleAnalyze}
                    disabled={analyzing}
                    className="mt-3 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 rounded text-sm"
                  >
                    {analyzing ? 'A analisar...' : 'Iniciar Análise'}
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {analyses.map((analysis, i) => (
                  <div key={i} className="bg-gray-800/50 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-bold text-blue-400">{analysis.chapter_title}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        analysis.sentiment === 'positive' ? 'bg-green-900 text-green-300' :
                        analysis.sentiment === 'negative' ? 'bg-red-900 text-red-300' :
                        analysis.sentiment === 'mixed' ? 'bg-yellow-900 text-yellow-300' :
                        'bg-gray-700 text-gray-300'
                      }`}>
                        {analysis.sentiment}
                      </span>
                    </div>

                    <p className="text-gray-300 text-sm">{analysis.summary}</p>

                    {analysis.key_topics?.length > 0 && (
                      <div>
                        <span className="text-xs text-gray-500">Tópicos:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {analysis.key_topics.map((topic, j) => (
                            <span key={j} className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded">
                              {topic}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {analysis.key_claims?.length > 0 && (
                      <div>
                        <span className="text-xs text-gray-500">Afirmações verificáveis:</span>
                        <ul className="mt-2 space-y-2">
                          {analysis.key_claims.map((claim, j) => {
                            const claimKey = `${analysis.chapter_title}::${claim}`
                            const result = claimResults[claimKey]
                            const isVerifying = verifyingClaim === claimKey

                            return (
                              <li key={j} className="text-sm bg-gray-900/50 rounded-lg p-2">
                                <div className="flex items-start gap-2">
                                  <span className="text-orange-500 mt-0.5">•</span>
                                  <span className="flex-1 text-orange-300">{claim}</span>

                                  {!result && (
                                    <button
                                      onClick={() => handleVerifyClaim(claim, analysis.chapter_title)}
                                      disabled={isVerifying}
                                      className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded"
                                    >
                                      {isVerifying ? '⏳' : '🔍 Verificar'}
                                    </button>
                                  )}

                                  {result?.status === 'done' && (
                                    <span className={`px-2 py-1 text-xs rounded font-bold ${
                                      result.verdict === 'true' ? 'bg-green-900 text-green-300' :
                                      result.verdict === 'false' ? 'bg-red-900 text-red-300' :
                                      result.verdict === 'partial' ? 'bg-yellow-900 text-yellow-300' :
                                      'bg-gray-700 text-gray-300'
                                    }`}>
                                      {result.verdict === 'true' ? '✓ Verdade' :
                                       result.verdict === 'false' ? '✗ Falso' :
                                       result.verdict === 'partial' ? '◐ Parcial' :
                                       '? Inconclusivo'}
                                    </span>
                                  )}

                                  {result?.status === 'error' && (
                                    <span className="px-2 py-1 text-xs bg-red-900 text-red-300 rounded">
                                      ❌ Erro
                                    </span>
                                  )}
                                </div>

                                {result?.explanation && (
                                  <p className="mt-2 text-xs text-gray-400 pl-4 border-l-2 border-gray-700">
                                    {result.explanation}
                                  </p>
                                )}
                              </li>
                            )
                          })}
                        </ul>
                      </div>
                    )}

                    {analysis.speakers_mentioned?.length > 0 && (
                      <div className="text-xs text-gray-500">
                        Pessoas mencionadas: {analysis.speakers_mentioned.join(', ')}
                      </div>
                    )}
                  </div>
                ))}
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

      {/* Polígrafo Modal */}
      {showPoligrafo && poligrafoResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="p-4 border-b border-gray-800 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold">🔍 Polígrafo - Verificação de Factos</h2>
                <p className="text-sm text-gray-500">
                  {poligrafoResult.summary?.total_claims || 0} claims analisados
                </p>
              </div>
              <button
                onClick={() => setShowPoligrafo(false)}
                className="text-gray-500 hover:text-white text-2xl"
              >
                ✕
              </button>
            </div>

            {/* Summary */}
            <div className="p-4 bg-gray-800/50 flex gap-4 justify-center">
              {Object.entries(poligrafoResult.summary?.verdicts || {}).map(([verdict, count]) => {
                const emoji = { VERDADEIRO: '✅', FALSO: '❌', PARCIALMENTE_VERDADEIRO: '⚠️', NAO_VERIFICAVEL: '❓' }[verdict] || '?'
                const color = { VERDADEIRO: 'text-green-400', FALSO: 'text-red-400', PARCIALMENTE_VERDADEIRO: 'text-yellow-400', NAO_VERIFICAVEL: 'text-gray-400' }[verdict] || 'text-gray-400'
                return (
                  <div key={verdict} className={`text-center ${color}`}>
                    <div className="text-2xl">{emoji}</div>
                    <div className="text-xl font-bold">{count}</div>
                    <div className="text-xs">{verdict.replace(/_/g, ' ')}</div>
                  </div>
                )
              })}
            </div>

            {/* Claims list */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {(poligrafoResult.verdicts || []).map((v, i) => {
                const emoji = { VERDADEIRO: '✅', FALSO: '❌', PARCIALMENTE_VERDADEIRO: '⚠️', NAO_VERIFICAVEL: '❓' }[v.verdict] || '?'
                const borderColor = { VERDADEIRO: 'border-green-600', FALSO: 'border-red-600', PARCIALMENTE_VERDADEIRO: 'border-yellow-600', NAO_VERIFICAVEL: 'border-gray-600' }[v.verdict] || 'border-gray-600'

                return (
                  <div key={i} className={`bg-gray-800 rounded-lg p-4 border-l-4 ${borderColor}`}>
                    <div className="flex items-start gap-3">
                      <span className="text-2xl">{emoji}</span>
                      <div className="flex-1">
                        <div className="font-medium text-white">{v.claim}</div>
                        <div className="text-xs text-gray-500 mt-1">
                          {v.speaker && <span className="mr-2">👤 {v.speaker}</span>}
                          {v.chapter && <span>📑 {v.chapter}</span>}
                        </div>
                        <div className="text-sm text-gray-300 mt-2">{v.explanation}</div>
                        {v.correction && (
                          <div className="text-sm text-yellow-400 mt-1">
                            ✏️ Correção: {v.correction}
                          </div>
                        )}
                        {v.sources?.length > 0 && (
                          <div className="text-xs text-gray-500 mt-1">
                            📚 {v.sources.join(', ')}
                          </div>
                        )}
                      </div>
                      {v.confidence > 0 && (
                        <div className="text-xs text-gray-500">
                          {v.confidence}%
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-gray-800 flex justify-end gap-2">
              <button
                onClick={() => {
                  const md = poligrafoResult.verdicts.map(v =>
                    `## ${v.verdict === 'VERDADEIRO' ? '✅' : v.verdict === 'FALSO' ? '❌' : v.verdict === 'PARCIALMENTE_VERDADEIRO' ? '⚠️' : '❓'} ${v.claim}\n\n**Speaker:** ${v.speaker}\n**Capítulo:** ${v.chapter}\n**Veredicto:** ${v.verdict}\n\n${v.explanation}\n${v.correction ? `\n**Correção:** ${v.correction}` : ''}\n`
                  ).join('\n---\n\n')
                  navigator.clipboard.writeText(md)
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm"
              >
                📋 Copiar Markdown
              </button>
              <button
                onClick={() => setShowPoligrafo(false)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
