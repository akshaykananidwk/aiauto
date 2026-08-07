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

  const load = async () => {
    try {
      const [list, dash, q] = await Promise.all([
        api('/prompts?page_size=15'),
        api('/dashboard/staff'),
        api('/prompts/quota'),
      ])
      setPrompts(list.items)
      setStats(dash)
      setQuota(q)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    api('/prompts/image-instruction')
      .then(r => setImageInstruction(r.instruction || ''))
      .catch(() => {})
  }, [])

  useEffect(() => {
    load()
    const disconnect = connectEvents((event) => {
      const label = STATUS_LABELS[event.type]
      if (label) setNotice(`${label} (${event.data?.prompt_id?.slice(0, 8) || ''})`)
      if (event.type?.startsWith('prompt.')) load()
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
      for (const f of files) fd.append('files', f)
      await api('/prompts', { method: 'POST', formData: fd })
      setText(''); setFiles([]); setWantsImage(false)
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
