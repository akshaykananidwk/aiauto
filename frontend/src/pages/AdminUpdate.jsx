import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { connectEvents } from '../ws'

export default function AdminUpdate() {
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState({ repo: '', branch: 'main', token: '' })
  const [check, setCheck] = useState(null)
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')

  const loadConfig = async () => {
    try {
      const cfg = await api('/admin/update/config')
      setConfig(cfg)
      setForm(f => ({ ...f, repo: cfg.repo || '', branch: cfg.branch || 'main' }))
    } catch (err) { setError(err.message) }
  }
  const loadHistory = async () => {
    try { setHistory(await api('/admin/update/history')) } catch { /* non-fatal */ }
  }
  const loadStatus = async () => {
    try { setStatus(await api('/admin/update/status')) } catch { /* non-fatal */ }
  }

  useEffect(() => {
    loadConfig(); loadHistory(); loadStatus()
    const disconnect = connectEvents((event) => {
      if (event.type === 'update.progress') loadStatus()
    })
    const poll = setInterval(() => loadStatus(), 3000)
    return () => { disconnect(); clearInterval(poll) }
  }, [])

  const saveConfig = async (e) => {
    e.preventDefault()
    setError(''); setNotice(''); setBusy('save')
    try {
      const cfg = await api('/admin/update/config', { method: 'PUT', body: form })
      setConfig(cfg)
      setForm(f => ({ ...f, token: '' }))
      setNotice('Configuration saved — the token is stored encrypted. You never need to upload files again.')
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  const doCheck = async () => {
    setError(''); setNotice(''); setBusy('check'); setCheck(null)
    try { setCheck(await api('/admin/update/check', { method: 'POST' })) }
    catch (err) { setError(err.message) } finally { setBusy('') }
  }

  const doUpdate = async () => {
    if (!window.confirm(
      'Run the one-click update now?\n\nAn automatic backup is taken first; ' +
      'protected files (.env, uploads, storage…) are never touched; on any ' +
      'error everything rolls back automatically.')) return
    setError(''); setNotice(''); setBusy('update')
    try {
      await api('/admin/update/run', { method: 'POST' })
      setNotice('Update started — progress is shown below. The server may restart at the end.')
    } catch (err) { setError(err.message) } finally { setBusy(''); loadStatus() }
  }

  return (
    <div>
      <h1>System Update</h1>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      <div className="card">
        <h2>GitHub Configuration <span className="muted">(one-time setup)</span></h2>
        <form onSubmit={saveConfig} className="grid cols-2">
          <div><label>Repository (owner/repo)</label>
            <input value={form.repo} onChange={e => setForm(f => ({ ...f, repo: e.target.value }))}
              placeholder="yourname/aiauto" required pattern="[\w.-]+/[\w.-]+" /></div>
          <div><label>Branch</label>
            <input value={form.branch} onChange={e => setForm(f => ({ ...f, branch: e.target.value }))} required /></div>
          <div><label>GitHub Token {config?.token_set && <span className="muted">(already saved — leave blank to keep)</span>}</label>
            <input type="password" value={form.token}
              onChange={e => setForm(f => ({ ...f, token: e.target.value }))}
              placeholder={config?.token_set ? '••••••••••••' : 'ghp_…'} /></div>
          <div style={{ alignSelf: 'end' }}>
            <button className="btn" disabled={busy === 'save'}>{busy === 'save' ? 'Saving…' : 'Save Configuration'}</button>
          </div>
        </form>
        {config && (
          <p className="muted" style={{ marginTop: 12 }}>
            Current version <b>{config.current_version || '?'}</b>
            {config.current_commit && <> · commit <code>{config.current_commit.slice(0, 10)}</code></>}
            <br />Protected (never overwritten): {config.protected_paths.join(', ')}
          </p>
        )}
      </div>

      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Update</h2>
          <div className="row">
            <button className="btn secondary" onClick={doCheck} disabled={busy === 'check' || status?.running}>
              {busy === 'check' ? 'Checking…' : '🔍 Check for Update'}
            </button>
            <button className="btn" onClick={doUpdate}
              disabled={!check?.update_available || status?.running || busy === 'update'}>
              ⬆ Update Now
            </button>
          </div>
        </div>

        {check && !check.update_available && (
          <div className="alert success" style={{ marginTop: 16 }}>✔ You are up to date
            (version {check.current_version || check.latest_version || '—'}).</div>
        )}
        {check?.update_available && (
          <div style={{ marginTop: 16 }}>
            <div className="alert info">
              New update available: version <b>{check.latest_version || '—'}</b> ·
              commit <code>{check.latest_commit.slice(0, 10)}</code> ·
              {check.commits_behind} new commit{check.commits_behind === 1 ? '' : 's'}
            </div>
            <ul className="commit-list">
              {check.commits.map(c => (
                <li key={c.sha}>
                  <span className="sha">{c.sha}</span>{c.message}
                  <div className="muted">{c.author} · {new Date(c.date).toLocaleString()}</div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {status?.running && (
          <div style={{ marginTop: 16 }}>
            <div className="row between">
              <b>Updating: {status.step}</b><span>{status.progress}%</span>
            </div>
            <div className="progress-track"><div className="progress-fill" style={{ width: `${status.progress}%` }} /></div>
          </div>
        )}
        {status?.log_tail?.length > 0 && (
          <div className="log-box" style={{ marginTop: 12 }}>{status.log_tail.join('\n')}</div>
        )}
      </div>

      <div className="card">
        <h2>Update History</h2>
        <table>
          <thead><tr><th>Date</th><th>From → To</th><th>Version</th><th>Status</th><th>Backup</th></tr></thead>
          <tbody>
            {history.map(h => (
              <tr key={h.id}>
                <td className="muted">{new Date(h.created_at).toLocaleString()}</td>
                <td><code>{(h.from_commit || '—').slice(0, 8)} → {(h.to_commit || '—').slice(0, 8)}</code></td>
                <td>{h.version || '—'}</td>
                <td><span className={`badge ${h.status === 'success' ? 'completed' : h.status === 'running' ? 'processing' : 'failed'}`}>{h.status}</span></td>
                <td className="muted">{h.backup_path ? h.backup_path.split(/[\\/]/).pop() : '—'}</td>
              </tr>
            ))}
            {history.length === 0 && <tr><td colSpan={5} className="muted">No updates run yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
