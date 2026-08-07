import React, { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api, downloadFile, fileLink, thumbnailUrl } from '../api'
import Markdown, { toHtml } from '../Markdown'
import { connectEvents } from '../ws'

export default function PromptDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState(null)
  const [thumbs, setThumbs] = useState({})
  const [viewer, setViewer] = useState(null)   // {file, url, view_url} for the image modal
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [stage, setStage] = useState('')       // live sub-state while processing
  const [rawText, setRawText] = useState(false)
  const [audioBusy, setAudioBusy] = useState(false)
  const [thread, setThread] = useState([])
  const [followUp, setFollowUp] = useState('')
  const [followUpImage, setFollowUpImage] = useState(false)
  const [sendingFollowUp, setSendingFollowUp] = useState(false)

  // Copy WITH formatting so it pastes into Word/email as real bold,
  // lists and tables; plain text is included for editors that want it.
  const copyAnswer = async () => {
    setError(''); setNotice('')
    try {
      const html = toHtml(prompt.response_text)
      if (navigator.clipboard && window.ClipboardItem) {
        await navigator.clipboard.write([new window.ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([prompt.response_text], { type: 'text/plain' }),
        })])
        setNotice('✅ Copied with formatting — paste into Word, email, docs…')
        return
      }
      await navigator.clipboard.writeText(prompt.response_text)
      setNotice('✅ Copied as plain text.')
    } catch {
      try {
        await navigator.clipboard.writeText(prompt.response_text)
        setNotice('✅ Copied as plain text.')
      } catch { setError('Could not copy — select the text and press Ctrl+C.') }
    }
  }

  const downloadAudio = async () => {
    setAudioBusy(true); setError(''); setNotice('🎵 Generating the audio…')
    try {
      const res = await api(`/prompts/${id}/audio`, { raw: true })
      if (!res.ok) {
        let detail = `Audio failed (${res.status})`
        try { detail = (await res.json()).detail || detail } catch { /* keep */ }
        throw new Error(detail)
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `answer_${id.slice(0, 8)}.${blob.type.includes('mpeg') ? 'mp3' : 'wav'}`
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
      setNotice('🎵 Audio downloaded — check your Downloads folder.')
    } catch (err) { setNotice(''); setError(err.message) }
    finally { setAudioBusy(false) }
  }

  const sendFollowUp = async () => {
    setSendingFollowUp(true); setError('')
    try {
      const created = await api(`/prompts/${id}/follow-up`, {
        method: 'POST',
        body: { prompt_text: followUp, wants_image: followUpImage,
                image_size: prompt.image_size || 'auto' },
      })
      setFollowUp(''); setFollowUpImage(false)
      navigate(`/prompt/${created.id}`)
    } catch (err) { setError(err.message) }
    finally { setSendingFollowUp(false) }
  }

  // Copy the image itself to the clipboard so it pastes into Paint, Word,
  // WhatsApp, Photoshop… Clipboard API needs HTTPS/localhost; on plain
  // http we fall back to guiding the native right-click copy.
  const copyImage = async () => {
    setError(''); setNotice('')
    try {
      if (!navigator.clipboard || !window.ClipboardItem) throw new Error('clipboard-unavailable')
      const resp = await fetch(viewer.view_url)
      let blob = await resp.blob()
      if (blob.type !== 'image/png') {
        const bmp = await createImageBitmap(blob)
        const canvas = document.createElement('canvas')
        canvas.width = bmp.width
        canvas.height = bmp.height
        canvas.getContext('2d').drawImage(bmp, 0, 0)
        blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
      }
      await navigator.clipboard.write([new window.ClipboardItem({ 'image/png': blob })])
      setNotice('✅ Image copied — paste it into Paint, Word, WhatsApp, Photoshop…')
    } catch {
      setNotice('ℹ️ Right-click (or long-press) the image and choose "Copy image" — '
        + 'the one-click Copy button needs the site to run on HTTPS.')
    }
  }

  const load = async () => {
    try {
      const p = await api(`/prompts/${id}`)
      setPrompt(p)
      if (p.status === 'completed') {
        api(`/prompts/${id}/thread`).then(setThread).catch(() => {})
      }
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

  const STAGES = {
    'prompt.processing': '🤖 The AI is working on your prompt…',
    'prompt.generating_image': '🎨 Generating the image… (this can take a few minutes)',
    'prompt.downloading': '⬇ Image ready — downloading it to the server…',
  }

  useEffect(() => {
    load()
    const disconnect = connectEvents((event) => {
      if (event.data?.prompt_id !== id) return
      if (STAGES[event.type]) setStage(STAGES[event.type])
      if (['prompt.completed', 'prompt.failed', 'prompt.cancelled'].includes(event.type)) setStage('')
      load()
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

  if (error && !prompt) return <div className="alert error">{error}</div>
  if (!prompt) return <div className="center-msg">Loading…</div>

  const results = prompt.files.filter(f => f.kind !== 'upload')
  const uploads = prompt.files.filter(f => f.kind === 'upload')
  const cancelable = ['waiting', 'processing'].includes(prompt.status)
  const retryable = ['failed', 'cancelled'].includes(prompt.status)

  const action = async (verb) => {
    try { setPrompt(await api(`/prompts/${id}/${verb}`, { method: 'POST' })) }
    catch (err) { setError(err.message) }
  }

  // Run the same request again as a NEW job — the current result is kept
  const regenerate = async () => {
    try {
      const fresh = await api(`/prompts/${id}/regenerate`, { method: 'POST' })
      navigate(`/prompt/${fresh.id}`)
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="row between">
        <h1>Prompt <span className="muted">{prompt.id.slice(0, 8)}</span></h1>
        <div className="row">
          {cancelable && <button className="btn danger sm" onClick={() => action('cancel')}>Cancel</button>}
          {retryable && <button className="btn sm" onClick={() => action('retry')}>Retry</button>}
          {!cancelable && (
            <button className="btn secondary sm" onClick={regenerate}
              title="Run the same request again — this result is kept">
              🔄 Regenerate
            </button>
          )}
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
        {active && stage && <div className="alert info" style={{ marginTop: 12 }}>{stage}</div>}
        {prompt.error && <div className="alert error" style={{ marginTop: 12 }}>{prompt.error}</div>}
        <h2 style={{ marginTop: 16 }}>Prompt</h2>
        <div className="response-box">{prompt.prompt_text}</div>
        {prompt.parent_id && (
          <p className="muted">
            Regenerated from <Link to={`/prompt/${prompt.parent_id}`}>
              {prompt.parent_id.slice(0, 8)}</Link>
          </p>
        )}
        {prompt.follow_up_to && (
          <p className="muted">
            💬 Follow-up to <Link to={`/prompt/${prompt.follow_up_to}`}>
              {prompt.follow_up_to.slice(0, 8)}</Link>
          </p>
        )}
        {uploads.length > 0 && (
          <p className="muted">Attached: {uploads.map(f => f.filename).join(', ')}</p>
        )}
      </div>

      {prompt.response_text && (
        <div className="card">
          <div className="row between">
            <h2>AI Response</h2>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <button className="btn ghost sm" title="Read aloud in this browser" onClick={() => {
                if (!window.speechSynthesis) return
                if (window.speechSynthesis.speaking) { window.speechSynthesis.cancel(); return }
                window.speechSynthesis.speak(new SpeechSynthesisUtterance(prompt.response_text.slice(0, 3000)))
              }}>🔊 Listen</button>
              <button className="btn ghost sm" title="Download the answer as an audio file"
                disabled={audioBusy} onClick={downloadAudio}>
                {audioBusy ? '🎵 Preparing…' : '🎵 Audio'}
              </button>
              <button className="btn ghost sm" title="Copy with formatting (Word, email…)"
                onClick={copyAnswer}>📋 Copy</button>
              <button className="btn ghost sm" title="Show the raw text"
                onClick={() => setRawText(r => !r)}>{rawText ? '📄 Formatted' : '</> Raw'}</button>
            </div>
          </div>
          {rawText
            ? <div className="response-box">{prompt.response_text}</div>
            : <div className="response-box"><Markdown text={prompt.response_text} /></div>}
        </div>
      )}

      {prompt.status === 'completed' && (
        <div className="card">
          <div className="row between">
            <h2 style={{ margin: 0 }}>💬 Ask a follow-up</h2>
            {thread.length > 0 && <span className="muted">{thread.length} so far</span>}
          </div>
          <p className="muted" style={{ marginTop: 4 }}>
            Continue this conversation — the AI remembers what was asked and
            answered above, so "make it shorter" or "same but in blue" works.
          </p>
          <textarea value={followUp} onChange={e => setFollowUp(e.target.value)}
            placeholder="e.g. Make it shorter · Same image but at sunset · Explain point 3" />
          <div className="row between" style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
            <label className="row" style={{ margin: 0 }}>
              <input type="checkbox" style={{ width: 'auto' }} checked={followUpImage}
                onChange={e => setFollowUpImage(e.target.checked)} />
              &nbsp;Generate image
            </label>
            <button className="btn" disabled={!followUp.trim() || sendingFollowUp}
              onClick={sendFollowUp}>
              {sendingFollowUp ? 'Sending…' : 'Send follow-up →'}
            </button>
          </div>
          {thread.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h3>Follow-ups</h3>
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Question</th><th>Status</th><th>When</th></tr></thead>
                  <tbody>
                    {thread.map(t => (
                      <tr key={t.id}>
                        <td><Link to={`/prompt/${t.id}`}>{t.prompt_text.slice(0, 70)}
                          {t.prompt_text.length > 70 ? '…' : ''}</Link></td>
                        <td><span className={`badge ${t.status}`}>{t.status}</span></td>
                        <td className="muted">{new Date(t.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
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
            {notice && <div className="alert info" style={{ marginBottom: 10 }}>{notice}</div>}
            {error && <div className="alert error" style={{ marginBottom: 10 }}>{error}</div>}
            {/* inline URL: right-click / long-press → Copy image, Save image */}
            <img src={viewer.view_url || viewer.url} alt={viewer.file.filename} />
            <div className="row between" style={{ marginTop: 12, flexWrap: 'wrap', gap: 8 }}>
              <span className="muted">{viewer.file.filename}</span>
              <span className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button className="btn" onClick={copyImage}>📋 Copy Image</button>
                <a className="btn secondary" href={viewer.url} download={viewer.file.filename}
                  onClick={() => setNotice('⬇ Download started — check the browser\'s '
                    + 'Downloads (folder icon, top-right) / your Downloads folder.')}>
                  ⬇ Download
                </a>
                <a className="btn secondary" href={viewer.view_url || viewer.url}
                  target="_blank" rel="noreferrer">Open in tab</a>
                <button className="btn ghost" onClick={() => { setViewer(null); setNotice(''); setError('') }}>Close</button>
              </span>
            </div>
            <p className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
              Save to phone gallery: <b>Open in tab</b> → long-press the image → <i>Save image</i>.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
