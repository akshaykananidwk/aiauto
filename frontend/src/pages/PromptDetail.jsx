import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api, downloadFile, fileLink, thumbnailUrl } from '../api'
import { connectEvents } from '../ws'

export default function PromptDetail() {
  const { id } = useParams()
  const [prompt, setPrompt] = useState(null)
  const [thumbs, setThumbs] = useState({})
  const [viewer, setViewer] = useState(null)   // {file, url} for the image modal
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const p = await api(`/prompts/${id}`)
      setPrompt(p)
      for (const f of p.files) {
        const isImage = f.kind === 'result_image' || f.mime_type?.startsWith('image/')
        if ((f.has_thumbnail || isImage) && !thumbs[f.id]) {
          // prefer the thumbnail; fall back to the full image so a failed
          // thumbnail never hides a generated picture
          const fetchPreview = async () => {
            if (f.has_thumbnail) {
              const url = await thumbnailUrl(f.id)
              if (url) return url
            }
            if (!isImage) return null
            const res = await api(`/files/${f.id}/download`, { raw: true })
            if (!res.ok) return null
            return URL.createObjectURL(await res.blob())
          }
          fetchPreview().then(url => url && setThumbs(t => ({ ...t, [f.id]: url })))
            .catch(() => {})
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

  // Polling fallback: WebSocket events are best-effort — while the prompt
  // is still running, refresh every 8s so results always appear even if
  // an event is lost.
  const active = prompt && ['waiting', 'processing'].includes(prompt.status)
  useEffect(() => {
    if (!active) return undefined
    const timer = setInterval(load, 8000)
    return () => clearInterval(timer)
  }, [active, id])

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
        </div>
      )}

      {results.length > 0 && (
        <div className="card">
          <h2>Generated Files &amp; Images</h2>
          <div className="thumb-grid">
            {results.map(f => {
              const isImage = f.kind === 'result_image' || f.mime_type?.startsWith('image/')
              return (
                <div key={f.id} className="thumb"
                  onClick={async () => {
                    try {
                      if (isImage) setViewer({ file: f, ...(await fileLink(f.id)) })
                      else await downloadFile(f.id, f.filename)
                    } catch (err) { setError(err.message) }
                  }}
                  title={isImage ? 'Click to view & save' : 'Click to download'}>
                  {thumbs[f.id]
                    ? <img src={thumbs[f.id]} alt={f.filename} />
                    : <div style={{ height: 100, display: 'grid', placeItems: 'center', fontSize: 32 }}>📄</div>}
                  <div className="name">{f.filename}<br />
                    <span className="muted">{(f.size_bytes / 1024).toFixed(0)} KB</span></div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {viewer && (
        <div className="viewer-overlay" onClick={() => setViewer(null)}>
          <div className="viewer" onClick={e => e.stopPropagation()}>
            <img src={viewer.url} alt={viewer.file.filename} />
            <div className="row between" style={{ marginTop: 12 }}>
              <span className="muted">{viewer.file.filename}</span>
              <span className="row" style={{ gap: 8 }}>
                {/* native link: works on desktop AND saves to mobile gallery */}
                <a className="btn" href={viewer.url} download={viewer.file.filename}>⬇ Download</a>
                <a className="btn secondary" href={viewer.url} target="_blank" rel="noreferrer">Open in tab</a>
                <button className="btn ghost" onClick={() => setViewer(null)}>Close</button>
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
