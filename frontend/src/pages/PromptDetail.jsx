import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api, downloadFile, thumbnailUrl } from '../api'
import { connectEvents } from '../ws'

export default function PromptDetail() {
  const { id } = useParams()
  const [prompt, setPrompt] = useState(null)
  const [thumbs, setThumbs] = useState({})
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const p = await api(`/prompts/${id}`)
      setPrompt(p)
      for (const f of p.files) {
        if (f.has_thumbnail && !thumbs[f.id]) {
          thumbnailUrl(f.id).then(url => url && setThumbs(t => ({ ...t, [f.id]: url })))
        }
      }
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    load()
    const disconnect = connectEvents((event) => {
      if (event.data?.prompt_id === id) load()
    })
    return disconnect
  }, [id])

  if (error) return <div className="alert error">{error}</div>
  if (!prompt) return <div className="center-msg">Loading…</div>

  const results = prompt.files.filter(f => f.kind !== 'upload')
  const uploads = prompt.files.filter(f => f.kind === 'upload')
  const cancelable = ['waiting', 'processing'].includes(prompt.status)
  const retryable = ['failed', 'cancelled'].includes(prompt.status)

  const action = async (verb) => {
    try { setPrompt(await api(`/prompts/${id}/${verb}`, { method: 'POST' })) }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="row between">
        <h1>Prompt <span className="muted">{prompt.id.slice(0, 8)}</span></h1>
        <div className="row">
          {cancelable && <button className="btn danger sm" onClick={() => action('cancel')}>Cancel</button>}
          {retryable && <button className="btn sm" onClick={() => action('retry')}>Retry</button>}
          <Link to="/" className="btn secondary sm">Back</Link>
        </div>
      </div>

      <div className="card">
        <div className="row between">
          <span className={`badge ${prompt.status}`}>{prompt.status}</span>
          <span className="muted">
            {prompt.queue_position ? `Queue position #${prompt.queue_position} · ` : ''}
            Submitted {new Date(prompt.created_at).toLocaleString()}
          </span>
        </div>
        {prompt.error && <div className="alert error" style={{ marginTop: 12 }}>{prompt.error}</div>}
        <h2 style={{ marginTop: 16 }}>Prompt</h2>
        <div className="response-box">{prompt.prompt_text}</div>
        {uploads.length > 0 && (
          <p className="muted">Attached: {uploads.map(f => f.filename).join(', ')}</p>
        )}
      </div>

      {prompt.response_text && (
        <div className="card">
          <div className="row between">
            <h2>AI Response</h2>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn ghost sm" title="Read aloud" onClick={() => {
                if (!window.speechSynthesis) return
                if (window.speechSynthesis.speaking) { window.speechSynthesis.cancel(); return }
                window.speechSynthesis.speak(new SpeechSynthesisUtterance(prompt.response_text.slice(0, 3000)))
              }}>🔊</button>
              <button className="btn ghost sm" title="Copy" onClick={() =>
                navigator.clipboard?.writeText(prompt.response_text)}>📋 Copy</button>
            </div>
          </div>
          <div className="response-box">{prompt.response_text}</div>
          {(prompt.provider || prompt.model) && (
            <p className="muted" style={{ marginBottom: 0 }}>
              {prompt.provider && <>Provider: {prompt.provider}</>}
              {prompt.model && <> · Model: {prompt.model}</>}
              {(prompt.input_tokens > 0 || prompt.output_tokens > 0) &&
                <> · Tokens: {prompt.input_tokens}/{prompt.output_tokens}</>}
              {prompt.cost_usd > 0 && <> · Est. cost: ${prompt.cost_usd}</>}
            </p>
          )}
        </div>
      )}

      {results.length > 0 && (
        <div className="card">
          <h2>Generated Files &amp; Images</h2>
          <div className="thumb-grid">
            {results.map(f => (
              <div key={f.id} className="thumb" onClick={() => downloadFile(f.id, f.filename)}
                   title="Click to download">
                {thumbs[f.id]
                  ? <img src={thumbs[f.id]} alt={f.filename} />
                  : <div style={{ height: 100, display: 'grid', placeItems: 'center', fontSize: 32 }}>📄</div>}
                <div className="name">{f.filename}<br />
                  <span className="muted">{(f.size_bytes / 1024).toFixed(0)} KB</span></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
