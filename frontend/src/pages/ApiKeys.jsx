import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function ApiKeys() {
  const [keys, setKeys] = useState([])
  const [name, setName] = useState('')
  const [created, setCreated] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setKeys(await api('/api-keys')) } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    setError(''); setCreated(null)
    try {
      const key = await api('/api-keys', { method: 'POST', body: { name } })
      setCreated(key)
      setName('')
      load()
    } catch (err) { setError(err.message) }
  }

  const revoke = async (key) => {
    if (!window.confirm(`Revoke API key "${key.name}"? Applications using it will stop working.`)) return
    try { await api(`/api-keys/${key.id}`, { method: 'DELETE' }); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <h1>API Keys</h1>
      <p className="muted">
        Use API keys for scripts and integrations: send prompts with an
        <code> X-API-Key</code> header instead of logging in. See the API docs at <code>/api/docs</code>.
      </p>
      {error && <div className="alert error">{error}</div>}
      {created && (
        <div className="alert success">
          Key created — copy it now, it will <b>not</b> be shown again:
          <div className="log-box" style={{ marginTop: 8 }}>{created.plain_key}</div>
        </div>
      )}

      <form className="card row" onSubmit={create}>
        <input style={{ maxWidth: 300 }} placeholder="Key name (e.g. reporting-script)"
          value={name} onChange={e => setName(e.target.value)} required />
        <button className="btn">Create Key</button>
      </form>

      <div className="card">
        <table>
          <thead><tr><th>Name</th><th>Key</th><th>Status</th><th>Last used</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id}>
                <td>{k.name}</td>
                <td><code>{k.prefix}…</code></td>
                <td><span className={`badge ${k.is_active ? 'online' : 'offline'}`}>{k.is_active ? 'active' : 'revoked'}</span></td>
                <td className="muted">{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'never'}</td>
                <td className="muted">{new Date(k.created_at).toLocaleDateString()}</td>
                <td>{k.is_active && <button className="btn danger sm" onClick={() => revoke(k)}>Revoke</button>}</td>
              </tr>
            ))}
            {keys.length === 0 && <tr><td colSpan={6} className="muted">No API keys yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
