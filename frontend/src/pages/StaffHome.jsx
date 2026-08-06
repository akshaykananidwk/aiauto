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
  const [text, setText] = useState('')
  const [wantsImage, setWantsImage] = useState(false)
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [prompts, setPrompts] = useState([])
  const [stats, setStats] = useState(null)
  const fileInput = useRef(null)

  const load = async () => {
    try {
      const [list, dash] = await Promise.all([
        api('/prompts?page_size=15'),
        api('/dashboard/staff'),
      ])
      setPrompts(list.items)
      setStats(dash)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    load()
    const disconnect = connectEvents((event) => {
      const label = STATUS_LABELS[event.type]
      if (label) setNotice(`${label} (${event.data?.prompt_id?.slice(0, 8) || ''})`)
      if (event.type?.startsWith('prompt.')) load()
    })
    return disconnect
  }, [])

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
        <h2>New Prompt</h2>
        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert info">{notice}</div>}
        <form onSubmit={submit}>
          <textarea
            placeholder="Type your prompt for the AI…"
            value={text}
            onChange={e => setText(e.target.value)}
            required
          />
          <div className="row between" style={{ marginTop: 12 }}>
            <div className="row">
              <label style={{ margin: 0 }} className="row">
                <input type="checkbox" style={{ width: 'auto' }}
                  checked={wantsImage} onChange={e => setWantsImage(e.target.checked)} />
                &nbsp;Generate image
              </label>
              <input type="file" multiple ref={fileInput} style={{ width: 'auto' }}
                onChange={e => setFiles([...e.target.files])} />
            </div>
            <button className="btn" disabled={busy || !text.trim()}>
              {busy ? 'Sending…' : 'Send to AI'}
            </button>
          </div>
        </form>
      </div>

      <div className="card">
        <h2>My Prompt History</h2>
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
  )
}
