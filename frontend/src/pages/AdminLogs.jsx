import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function AdminLogs() {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [level, setLevel] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const params = new URLSearchParams({ page, page_size: 50 })
      if (level) params.set('level', level)
      const res = await api(`/admin/logs?${params}`)
      setLogs(res.items); setTotal(res.total)
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [page, level])

  return (
    <div>
      <h1>Audit Logs</h1>
      {error && <div className="alert error">{error}</div>}
      <div className="card">
        <div className="row between" style={{ marginBottom: 12 }}>
          <select style={{ width: 180 }} value={level} onChange={e => { setLevel(e.target.value); setPage(1) }}>
            <option value="">All levels</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
          <div className="row">
            <button className="btn secondary sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹ Prev</button>
            <span className="muted">page {page} / {Math.max(1, Math.ceil(total / 50))}</span>
            <button className="btn secondary sm" disabled={page * 50 >= total} onClick={() => setPage(p => p + 1)}>Next ›</button>
          </div>
        </div>
        <table>
          <thead><tr><th>Time</th><th>Event</th><th>Level</th><th>User</th><th>Message</th></tr></thead>
          <tbody>
            {logs.map(l => (
              <tr key={l.id}>
                <td className="muted">{new Date(l.created_at).toLocaleString()}</td>
                <td>{l.event}</td>
                <td><span className={`badge ${l.level === 'error' ? 'failed' : l.level === 'warning' ? 'waiting' : 'cancelled'}`}>{l.level}</span></td>
                <td className="muted">{l.user_id ?? '—'}</td>
                <td>{l.message}</td>
              </tr>
            ))}
            {logs.length === 0 && <tr><td colSpan={5} className="muted">No log entries.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
