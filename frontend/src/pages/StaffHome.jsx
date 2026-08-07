import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { connectEvents } from '../ws'

const STATUS_LABELS = {
  'prompt.submitted': 'Submitted — waiting in queue',
  'prompt.processing': 'Processing…',
  'prompt.generating_image': 'Generating image…',
  'prompt.downloading': 'Downloading results…',
  'prompt.completed': 'Completed ✔',
  'prompt.failed': 'Failed',
  'prompt.cancelled': 'Cancelled',
}

export default function StaffHome() {
  const [text, setText] = useState(() => {
    const draft = localStorage.getItem('aiauto_draft') || ''
    localStorage.removeItem('aiauto_draft')
    return draft
  })
  const [wantsImage, setWantsImage] = useState(false)
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [prompts, setPrompts] = useState([])
  const [stats, setStats] = useState(null)
  const [quota, setQuota] = useState(null)
  const [listening, setListening] = useState(false)
  const fileInput = useRef(null)
  const recognitionRef = useRef(null)

  // English image instruction that the platform appends automatically
  const [imageInstruction, setImageInstruction] = useState('')
  const [sizes, setSizes] = useState([])
  const [imageSize, setImageSize] = useState('auto')
  const [improving, setImproving] = useState(false)
  const [originalText, setOriginalText] = useState(null)  // undo after improve
  const [historySearch, setHistorySearch] = useState('')

  // Searching only needs the list — reloading stats/quota on every
  // keystroke would triple the API traffic for nothing.
  const loadPrompts = async (search = historySearch) => {
    const params = new URLSearchParams({ page_size: '15' })
    if (search.trim()) params.set('search', search.trim())
    const list = await api(`/prompts?${params}`)
    setPrompts(list.items)
  }

  const load = async (search = historySearch) => {
    try {
      const [dash, q] = await Promise.all([
        api('/dashboard/staff'),
        api('/prompts/quota'),
      ])
      setStats(dash)
      setQuota(q)
      await loadPrompts(search)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    api('/prompts/image-instruction')
      .then(r => setImageInstruction(r.instruction || ''))
      .catch(() => {})
    api('/prompts/image-sizes')
      .then(r => setSizes(r.presets || []))
      .catch(() => {})
  }, [])

  // debounce history search so typing doesn't hammer the API
  useEffect(() => {
    const timer = setTimeout(
      () => loadPrompts(historySearch).catch(err => setError(err.message)), 400)
    return () => clearTimeout(timer)
  }, [historySearch])

  // Ask the AI to rewrite the prompt properly. Runs as a short
  // high-priority job, so it usually returns within seconds.
  const improvePrompt = async () => {
    if (!text.trim() || improving) return
    setImproving(true); setError(''); setNotice('✨ Improving your prompt…')
    try {
      const job = await api('/prompts/improve', {
        method: 'POST', body: { prompt_text: text, wants_image: wantsImage },
      })
      const deadline = Date.now() + 180000
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 2500))
        const res = await api(`/prompts/improve/${job.id}`)
        if (res.status === 'completed' && res.improved_text) {
          setOriginalText(text)
          setText(res.improved_text)
          setNotice('✨ Prompt improved — check it, edit if you like, then send.')
          return
        }
        if (['failed', 'cancelled'].includes(res.status)) {
          throw new Error(res.error || 'the improver job did not finish')
        }
      }
      throw new Error('improvement is taking too long — try again in a moment')
    } catch (err) {
      setNotice(''); setError(`Could not improve the prompt: ${err.message}`)
    } finally { setImproving(false) }
  }

  useEffect(() => {
    load()
    const disconnect = connectEvents((event) => {
      const label = STATUS_LABELS[event.type]
      if (label) setNotice(`${label} (${event.data?.prompt_id?.slice(0, 8) || ''})`)
      // live events only need the list; stats/quota refresh on the timer
      if (event.type?.startsWith('prompt.')) loadPrompts().catch(() => {})
    })
    // polling safety net: WS events are best-effort, so refresh the list
    // periodically to catch any status change a lost event would hide
    const timer = setInterval(load, 20000)
    return () => { disconnect(); clearInterval(timer) }
  }, [])

  // Voice input via the browser's speech recognition (where available)
  const toggleVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { setError('Voice input is not supported in this browser'); return }
    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = false
    rec.onresult = (e) => {
      const transcript = Array.from(e.results).map(r => r[0].transcript).join(' ')
      setText(t => (t ? t + ' ' : '') + transcript)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recognitionRef.current = rec
    rec.start()
    setListening(true)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const fd = new FormData()
      fd.append('prompt_text', text)
      fd.append('wants_image', wantsImage)
      fd.append('computer_name', navigator.userAgent.slice(0, 120))
      if (wantsImage) fd.append('image_size', imageSize)
      for (const f of files) fd.append('files', f)
      await api('/prompts', { method: 'POST', formData: fd })
      setText(''); setFiles([]); setWantsImage(false); setOriginalText(null)
      if (fileInput.current) fileInput.current.value = ''
      setNotice('Prompt submitted — you will see live status updates here.')
      load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const quotaText = quota && (quota.daily_limit > 0 || quota.monthly_limit > 0)
    ? `Quota: ${quota.daily_limit ? `${quota.daily_used}/${quota.daily_limit} today` : ''}` +
      `${quota.daily_limit && quota.monthly_limit ? ' · ' : ''}` +
      `${quota.monthly_limit ? `${quota.monthly_used}/${quota.monthly_limit} this month` : ''}`
    : null

  return (
    <div>
      <h1>My Dashboard</h1>
      {stats && (
        <div className="grid cols-4" style={{ marginBottom: 20 }}>
          <div className="stat"><div className="label">Waiting</div><div className="value">{stats.my_queue.waiting}</div></div>
          <div className="stat"><div className="label">Processing</div><div className="value">{stats.my_queue.processing}</div></div>
          <div className="stat"><div className="label">Completed</div><div className="value">{stats.my_queue.completed}</div></div>
          <div className="stat"><div className="label">Today</div><div className="value">{stats.my_usage.today}</div></div>
        </div>
      )}

      <div className="card">
        <div className="row between">
          <h2>New Prompt</h2>
          {quotaText && <span className="muted">{quotaText}</span>}
        </div>
        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert info">{notice}</div>}
        <form onSubmit={submit}>
          <textarea
            placeholder="Type your prompt for the AI… (or use the 🎤 button and dictate)"
            value={text}
            onChange={e => setText(e.target.value)}
            required
          />
          {originalText !== null && (
            <div className="row" style={{ marginTop: 8, gap: 8 }}>
              <button type="button" className="btn ghost sm"
                onClick={() => { setText(originalText); setOriginalText(null); setNotice('') }}>
                ↩ Undo improve (back to my wording)
              </button>
            </div>
          )}

          {wantsImage && (
            <div className="row" style={{ marginTop: 12, gap: 10, flexWrap: 'wrap' }}>
              <div style={{ minWidth: 260 }}>
                <label style={{ marginBottom: 4 }}>Output size</label>
                <select value={imageSize} onChange={e => setImageSize(e.target.value)}>
                  {sizes.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
              </div>
              {files.length > 0 && (
                <div className="alert info" style={{ margin: 0, alignSelf: 'flex-end' }}>
                  🖼 Attached image(s) will be used as a <b>reference</b> —
                  "make one like this".
                </div>
              )}
            </div>
          )}

          {wantsImage && imageInstruction && (
            <div className="alert info" style={{ marginTop: 12 }}>
              🎨 <b>Added automatically to your prompt:</b>
              <div className="response-box" style={{ marginTop: 6, fontSize: 13 }}>
                {imageInstruction}
              </div>
              <span className="muted">
                Write your idea in any language — this English image
                instruction is appended for you when the prompt is sent.
              </span>
            </div>
          )}
          <div className="row between" style={{ marginTop: 12 }}>
            <div className="row">
              <button type="button" className="btn secondary sm" disabled={improving || !text.trim()}
                onClick={improvePrompt} title="Let the AI rewrite this into a better prompt">
                {improving ? '✨ Improving…' : '✨ Improve prompt'}
              </button>
              <button type="button" className={`btn ghost sm ${listening ? 'recording' : ''}`}
                onClick={toggleVoice} title="Voice input">
                {listening ? '⏹ Stop' : '🎤'}
              </button>
              <label style={{ margin: 0 }} className="row">
                <input type="checkbox" style={{ width: 'auto' }}
                  checked={wantsImage} onChange={e => setWantsImage(e.target.checked)} />
                &nbsp;Generate image
              </label>
              <input type="file" multiple ref={fileInput} style={{ width: 'auto' }}
                onChange={e => setFiles([...e.target.files])} />
              <Link to="/templates" className="muted">📚 Templates</Link>
            </div>
            <button className="btn" disabled={busy || !text.trim()}>
              {busy ? 'Sending…' : 'Send to AI'}
            </button>
          </div>
        </form>
      </div>

      <div className="card">
        <div className="row between">
          <h2>My Prompt History</h2>
          <input style={{ maxWidth: 280, margin: 0 }} value={historySearch}
            onChange={e => setHistorySearch(e.target.value)}
            placeholder="🔍 Search my prompts and answers…" />
          <a className="muted" href="#" onClick={async (e) => {
            e.preventDefault()
            const res = await api('/prompts/export?fmt=csv', { raw: true })
            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url; a.download = 'prompt_history.csv'; a.click()
            URL.revokeObjectURL(url)
          }}>⬇ Export history</a>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Prompt</th><th>Status</th><th>Queue</th><th>Submitted</th><th>Results</th></tr>
            </thead>
            <tbody>
              {prompts.map(p => (
                <tr key={p.id}>
                  <td><Link to={`/prompt/${p.id}`}>{p.prompt_text.slice(0, 60)}{p.prompt_text.length > 60 ? '…' : ''}</Link></td>
                  <td><span className={`badge ${p.status}`}>{p.status}</span></td>
                  <td>{p.queue_position ? `#${p.queue_position}` : '—'}</td>
                  <td className="muted">{new Date(p.created_at).toLocaleString()}</td>
                  <td>{p.files.filter(f => f.kind !== 'upload').length || '—'}</td>
                </tr>
              ))}
              {prompts.length === 0 && <tr><td colSpan={5} className="muted">No prompts yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
