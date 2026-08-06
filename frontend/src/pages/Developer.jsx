import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { BarChart } from '../components/Chart'

const EMPTY_KEY = { name: '', scopes: [], expires_at: '', ip_allowlist: '', rate_limit_per_minute: 0 }

export default function Developer() {
  const [keys, setKeys] = useState([])
  const [hooks, setHooks] = useState([])
  const [usage, setUsage] = useState(null)
  const [meta, setMeta] = useState({ scopes: [], events: [] })
  const [form, setForm] = useState(EMPTY_KEY)
  const [showForm, setShowForm] = useState(false)
  const [revealed, setRevealed] = useState(null)   // {label, value} shown once
  const [hookForm, setHookForm] = useState({ url: '', events: [] })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    try {
      const [k, h, u, m] = await Promise.all([
        api('/developer/keys'), api('/developer/webhooks'),
        api('/developer/usage?days=7'), api('/developer/scopes'),
      ])
      setKeys(k); setHooks(h); setUsage(u); setMeta(m)
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  const createKey = async (e) => {
    e.preventDefault()
    setError(''); setNotice('')
    try {
      const body = {
        name: form.name,
        scopes: form.scopes.length ? form.scopes : null,
        rate_limit_per_minute: Number(form.rate_limit_per_minute) || 0,
      }
      if (form.expires_at) body.expires_at = new Date(form.expires_at).toISOString()
      const ips = form.ip_allowlist.split(',').map(s => s.trim()).filter(Boolean)
      if (ips.length) body.ip_allowlist = ips
      const key = await api('/developer/keys', { method: 'POST', body })
      setRevealed({ label: `API key "${key.name}"`, value: key.plain_key })
      setForm(EMPTY_KEY); setShowForm(false); load()
    } catch (err) { setError(err.message) }
  }

  const keyAction = async (k, action) => {
    setError(''); setNotice('')
    try {
      if (action === 'rename') {
        const name = window.prompt('New name:', k.name)
        if (!name) return
        await api(`/developer/keys/${k.id}`, { method: 'PATCH', body: { name } })
      } else if (action === 'toggle') {
        await api(`/developer/keys/${k.id}`, { method: 'PATCH', body: { is_active: !k.is_active } })
      } else if (action === 'regenerate') {
        if (!window.confirm(`Regenerate "${k.name}"? The current key stops working immediately.`)) return
        const res = await api(`/developer/keys/${k.id}/regenerate`, { method: 'POST' })
        setRevealed({ label: `Regenerated key "${res.name}"`, value: res.plain_key })
      } else if (action === 'delete') {
        if (!window.confirm(`Delete "${k.name}" permanently?`)) return
        await api(`/developer/keys/${k.id}`, { method: 'DELETE' })
      }
      load()
    } catch (err) { setError(err.message) }
  }

  const createHook = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const hook = await api('/developer/webhooks', {
        method: 'POST',
        body: { url: hookForm.url, events: hookForm.events.length ? hookForm.events : null },
      })
      setRevealed({ label: `Webhook signing secret for ${hook.url}`, value: hook.secret })
      setHookForm({ url: '', events: [] }); load()
    } catch (err) { setError(err.message) }
  }

  const toggleIn = (list, value) =>
    list.includes(value) ? list.filter(v => v !== value) : [...list, value]

  return (
    <div>
      <h1>API &amp; Developer Portal</h1>
      <p className="muted">
        Integrate your own websites, ERP/CRM systems and apps with the platform's REST
        API. All jobs run through the central ChatGPT session — no external AI services.
      </p>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}
      {revealed && (
        <div className="alert success">
          {revealed.label} — copy it now, it will <b>not</b> be shown again:
          <div className="log-box" style={{ marginTop: 8 }}>{revealed.value}</div>
          <button className="btn ghost sm" style={{ marginTop: 8 }}
            onClick={() => { navigator.clipboard?.writeText(revealed.value); setNotice('Copied!') }}>📋 Copy</button>
        </div>
      )}

      {usage && (
        <div className="grid cols-4" style={{ marginBottom: 20 }}>
          <div className="stat"><div className="label">Requests (7d)</div><div className="value">{usage.total_requests}</div></div>
          <div className="stat"><div className="label">Successful</div><div className="value">{usage.total_ok}</div></div>
          <div className="stat"><div className="label">Failed</div><div className="value">{usage.total_err}</div></div>
          <div className="stat"><div className="label">Active Keys</div><div className="value">{usage.active_keys}</div></div>
        </div>
      )}
      {usage?.days?.length > 0 && (
        <div className="card"><h2>API Requests per Day</h2>
          <BarChart data={usage.days.map(d => ({ ...d, total: d.ok + d.err }))} xKey="day" yKey="total" /></div>
      )}

      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>API Keys</h2>
          <button className="btn" onClick={() => setShowForm(s => !s)}>{showForm ? 'Close' : '+ New Key'}</button>
        </div>
        {showForm && (
          <form onSubmit={createKey} style={{ marginTop: 12 }}>
            <div className="grid cols-4">
              <div><label>Name</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required /></div>
              <div><label>Expires (optional)</label>
                <input type="datetime-local" value={form.expires_at}
                  onChange={e => setForm(f => ({ ...f, expires_at: e.target.value }))} /></div>
              <div><label>Rate limit /min (0 = default 60)</label>
                <input type="number" min="0" value={form.rate_limit_per_minute}
                  onChange={e => setForm(f => ({ ...f, rate_limit_per_minute: e.target.value }))} /></div>
              <div><label>IP allowlist (comma-separated, optional)</label>
                <input placeholder="203.0.113.5, 198.51.100.2" value={form.ip_allowlist}
                  onChange={e => setForm(f => ({ ...f, ip_allowlist: e.target.value }))} /></div>
            </div>
            <label>Permissions (none selected = all)</label>
            <div className="row">
              {meta.scopes.map(s => (
                <label key={s} className="row" style={{ margin: 0 }}>
                  <input type="checkbox" style={{ width: 'auto' }} checked={form.scopes.includes(s)}
                    onChange={() => setForm(f => ({ ...f, scopes: toggleIn(f.scopes, s) }))} />
                  &nbsp;{s}
                </label>
              ))}
            </div>
            <div style={{ marginTop: 12 }}><button className="btn">Create Key</button></div>
          </form>
        )}
        <div className="table-scroll">
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>Name</th><th>Key</th><th>Permissions</th><th>Limit</th><th>Requests</th><th>Last used</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {keys.map(k => (
                <tr key={k.id}>
                  <td>{k.name}</td>
                  <td><code>{k.prefix}…</code></td>
                  <td className="muted">{k.scopes.length ? k.scopes.join(', ') : 'all'}</td>
                  <td className="muted">{k.rate_limit_per_minute || 60}/min</td>
                  <td>{k.request_count}</td>
                  <td className="muted">{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'never'}</td>
                  <td><span className={`badge ${k.is_active ? 'online' : 'offline'}`}>
                    {k.is_active ? (k.expires_at && new Date(k.expires_at) < new Date() ? 'expired' : 'active') : 'disabled'}</span></td>
                  <td className="row" style={{ gap: 4 }}>
                    <button className="btn ghost sm" onClick={() => keyAction(k, 'rename')}>Rename</button>
                    <button className="btn ghost sm" onClick={() => keyAction(k, 'regenerate')}>Regenerate</button>
                    <button className="btn ghost sm" onClick={() => keyAction(k, 'toggle')}>{k.is_active ? 'Disable' : 'Enable'}</button>
                    <button className="btn danger sm" onClick={() => keyAction(k, 'delete')}>Del</button>
                  </td>
                </tr>
              ))}
              {keys.length === 0 && <tr><td colSpan={8} className="muted">No API keys yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Webhooks</h2>
        <p className="muted">Get notified at your own URL when jobs finish. Deliveries are signed
          (HMAC-SHA256, <code>X-AIAuto-Signature</code>) and retried automatically.</p>
        <form onSubmit={createHook} className="row" style={{ alignItems: 'end' }}>
          <div style={{ flex: 1, minWidth: 240 }}><label>URL</label>
            <input placeholder="https://yourapp.com/aiauto-webhook" value={hookForm.url}
              onChange={e => setHookForm(f => ({ ...f, url: e.target.value }))} required /></div>
          <button className="btn">Add Webhook</button>
        </form>
        <div className="row" style={{ marginTop: 8 }}>
          {meta.events.map(ev => (
            <label key={ev} className="row" style={{ margin: 0 }}>
              <input type="checkbox" style={{ width: 'auto' }} checked={hookForm.events.includes(ev)}
                onChange={() => setHookForm(f => ({ ...f, events: toggleIn(f.events, ev) }))} />
              &nbsp;{ev}
            </label>
          ))}
          <span className="muted">(none selected = all events)</span>
        </div>
        <table style={{ marginTop: 12 }}>
          <thead><tr><th>URL</th><th>Events</th><th>Last delivery</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {hooks.map(h => (
              <tr key={h.id}>
                <td><code>{h.url}</code></td>
                <td className="muted">{Array.isArray(h.events) ? h.events.join(', ') : 'all'}</td>
                <td className="muted">{h.last_delivery_at ? new Date(h.last_delivery_at).toLocaleString() : 'never'}</td>
                <td>{h.last_status
                  ? <span className={`badge ${h.last_status < 300 ? 'online' : 'offline'}`}>HTTP {h.last_status}</span>
                  : <span className="badge cancelled">—</span>}</td>
                <td className="row" style={{ gap: 4 }}>
                  <button className="btn ghost sm" onClick={async () => {
                    try { await api(`/developer/webhooks/${h.id}/test`, { method: 'POST' }); setNotice('Test delivery sent — check your endpoint') }
                    catch (err) { setError(err.message) }
                  }}>Test</button>
                  <button className="btn danger sm" onClick={async () => {
                    if (!window.confirm('Delete this webhook?')) return
                    try { await api(`/developer/webhooks/${h.id}`, { method: 'DELETE' }); load() }
                    catch (err) { setError(err.message) }
                  }}>Del</button>
                </td>
              </tr>
            ))}
            {hooks.length === 0 && <tr><td colSpan={5} className="muted">No webhooks yet.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Documentation &amp; Tools</h2>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          <a className="btn secondary" href="/api/docs" target="_blank" rel="noreferrer">🧪 Interactive API Explorer (Swagger)</a>
          <a className="btn secondary" href="/api/redoc" target="_blank" rel="noreferrer">📖 ReDoc Reference</a>
          <a className="btn secondary" href="/api/openapi.json" target="_blank" rel="noreferrer">⬇ OpenAPI JSON</a>
          <a className="btn secondary" href="/api/openapi.yaml">⬇ OpenAPI YAML</a>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Developer guide with authentication, error codes, pagination, webhook verification and
          SDK examples (Python, Node.js, PHP/Laravel, C#, Kotlin, Flutter, React):
          <code> docs/PUBLIC_API.md</code> and <code>docs/sdk-examples/</code> in the repository.
          In the Explorer, click <i>Authorize</i> and paste your <code>X-API-Key</code> to test live.
        </p>
      </div>
    </div>
  )
}
