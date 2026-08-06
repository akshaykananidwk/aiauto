import React, { useEffect, useState } from 'react'
import { api } from '../api'

function Meter({ label, percent, warn = 80 }) {
  const color = percent == null ? 'var(--muted)'
    : percent >= warn ? 'var(--red)' : percent >= warn - 20 ? 'var(--yellow)' : 'var(--green)'
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{percent == null ? '—' : `${percent}%`}</div>
      <div className="progress-track"><div className="progress-fill"
        style={{ width: `${percent || 0}%`, background: color }} /></div>
    </div>
  )
}

export default function AdminSystem() {
  const [health, setHealth] = useState(null)
  const [backups, setBackups] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const [diag, setDiag] = useState(null)
  const [logTail, setLogTail] = useState(null)

  const load = async () => {
    try {
      const [h, b, d] = await Promise.all([
        api('/admin/system/health'), api('/admin/system/backups'),
        api('/admin/system/diagnostics'),
      ])
      setHealth(h); setBackups(b); setDiag(d)
    } catch (err) { setError(err.message) }
  }

  // diagnostics files need the JWT, so fetch as a blob and open that
  const openDiagFile = async (name) => {
    try {
      const res = await api(`/admin/system/diagnostics/file?name=${encodeURIComponent(name)}`, { raw: true })
      if (!res.ok) throw new Error(`Could not open ${name} (${res.status})`)
      window.open(URL.createObjectURL(await res.blob()), '_blank')
    } catch (err) { setError(err.message) }
  }

  const showTail = async (name) => {
    try {
      setLogTail(await api(`/admin/system/diagnostics/tail?name=${encodeURIComponent(name)}&lines=200`))
    } catch (err) { setError(err.message) }
  }
  useEffect(() => {
    load()
    const timer = setInterval(load, 10000)
    return () => clearInterval(timer)
  }, [])

  const createBackup = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api('/admin/system/backups', { method: 'POST' })
      setNotice(`Backup created: ${result.backup}${result.db_dump ? ` + ${result.db_dump}` : ''}`)
      load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const restore = async (backup) => {
    if (!window.confirm(
      `Restore "${backup.name}"?\n\nThis overwrites current code files with the backup contents ` +
      '(protected files like .env, storage and uploads are not touched). Restart the service afterwards.')) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api('/admin/system/backups/restore', {
        method: 'POST', body: { name: backup.name, confirm: true },
      })
      setNotice(`Restored ${result.restored_files} files from ${backup.name}. Restart the service to apply.`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  if (!health) return <div className="center-msg">Loading system health…</div>

  return (
    <div>
      <h1>System Health</h1>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      <div className="card">
        <div className="row" style={{ marginBottom: 16 }}>
          <span className={`badge ${health.database_ok ? 'online' : 'offline'}`}>Database {health.database_ok ? 'OK' : 'DOWN'}</span>
          <span className={`badge ${health.redis_ok ? 'online' : 'offline'}`}>Redis {health.redis_ok ? 'OK' : 'DOWN'}</span>
          <span className="muted">Disk free: {health.disk_free_gb} GB of {health.disk_total_gb} GB</span>
        </div>
        <div className="grid cols-4">
          <Meter label="CPU" percent={health.cpu_percent} />
          <Meter label="Memory" percent={health.memory_percent} />
          <Meter label="Disk" percent={health.disk_used_percent} warn={90} />
        </div>
      </div>

      <div className="card">
        <h2>Workers</h2>
        <table>
          <thead><tr><th>Worker</th><th>Chrome</th><th>Current job</th><th>Heartbeat</th></tr></thead>
          <tbody>
            {health.workers.map(w => (
              <tr key={w.id}>
                <td><b>{w.id}</b></td>
                <td><span className={`badge ${w.chrome === 'connected' ? 'online' : 'offline'}`}>{w.chrome}</span></td>
                <td className="muted">{w.current_job || 'idle'}</td>
                <td className="muted">{w.heartbeat ? new Date(w.heartbeat).toLocaleTimeString() : '—'}</td>
              </tr>
            ))}
            {health.workers.length === 0 && (
              <tr><td colSpan={4} className="muted">No workers online — start the worker on the master computer.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Image-Capture Diagnostics</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          When the worker cannot capture a generated image it saves a screenshot of
          exactly what the ChatGPT page showed. Open a dump below to see the real cause.
        </p>
        {diag && diag.debug_dumps.length > 0 ? (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Dump</th><th>Size</th><th>When</th><th></th></tr></thead>
              <tbody>
                {diag.debug_dumps.map(f => (
                  <tr key={f.name}>
                    <td><code>{f.name}</code></td>
                    <td>{(f.size_bytes / 1024).toFixed(0)} KB</td>
                    <td className="muted">{new Date(f.modified).toLocaleString()}</td>
                    <td><button className="btn sm" onClick={() => openDiagFile(f.name)}>Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">No capture-failure dumps — good sign.</p>}
        <div className="row" style={{ marginTop: 10, gap: 8, flexWrap: 'wrap' }}>
          {diag?.logs.map(l => (
            <button key={l.name} className="btn secondary sm" onClick={() => showTail(l.name)}>
              📜 View {l.name} (last 200 lines)
            </button>
          ))}
        </div>
        {logTail && (
          <div style={{ marginTop: 10 }}>
            <div className="row between">
              <b>{logTail.name}</b>
              <button className="btn ghost sm" onClick={() => setLogTail(null)}>Close</button>
            </div>
            <pre className="response-box" style={{ maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
              {logTail.lines.join('\n')}
            </pre>
          </div>
        )}
      </div>

      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Backups</h2>
          <button className="btn" onClick={createBackup} disabled={busy}>
            {busy ? 'Working…' : '💾 Backup Now'}
          </button>
        </div>
        <table style={{ marginTop: 12 }}>
          <thead><tr><th>File</th><th>Size</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {backups.map(b => (
              <tr key={b.name}>
                <td><code>{b.name}</code></td>
                <td>{b.size_mb} MB</td>
                <td className="muted">{new Date(b.created_at).toLocaleString()}</td>
                <td>{b.name.endsWith('.zip') &&
                  <button className="btn danger sm" onClick={() => restore(b)} disabled={busy}>Restore</button>}</td>
              </tr>
            ))}
            {backups.length === 0 && <tr><td colSpan={4} className="muted">No backups yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
