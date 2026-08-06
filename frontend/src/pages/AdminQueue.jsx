import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { connectEvents } from '../ws'

export default function AdminQueue() {
  const [queue, setQueue] = useState([])
  const [failed, setFailed] = useState([])
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [live, failedList] = await Promise.all([
        api('/admin/queue'),
        api('/prompts?status=failed&all_users=true&page_size=20'),
      ])
      setQueue(live)
      setFailed(failedList.items)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    load()
    const disconnect = connectEvents((event) => {
      if (event.type?.startsWith('prompt.') || event.type === 'queue.updated') load()
    })
    return disconnect
  }, [])

  const action = async (id, verb) => {
    try { await api(`/prompts/${id}/${verb}`, { method: 'POST' }); load() }
    catch (err) { setError(err.message) }
  }

  const renderRow = (p, actions) => (
    <tr key={p.id}>
      <td>{p.queue_position ? `#${p.queue_position}` : (p.status === 'processing' ? '▶' : '')}</td>
      <td><Link to={`/prompt/${p.id}`}>{p.prompt_text.slice(0, 50)}…</Link></td>
      <td>{p.user_name}</td>
      <td className="muted">{p.department || '—'}</td>
      <td><span className={`badge ${p.status}`}>{p.status}</span></td>
      <td className="muted">{new Date(p.created_at).toLocaleTimeString()}</td>
      <td>{actions}</td>
    </tr>
  )

  return (
    <div>
      <h1>Live Queue</h1>
      {error && <div className="alert error">{error}</div>}
      <div className="card">
        <table>
          <thead><tr><th>Pos</th><th>Prompt</th><th>User</th><th>Dept</th><th>Status</th><th>Time</th><th></th></tr></thead>
          <tbody>
            {queue.map(p => renderRow(p,
              <button className="btn danger sm" onClick={() => action(p.id, 'cancel')}>Cancel</button>))}
            {queue.length === 0 && <tr><td colSpan={7} className="muted">Queue is empty.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Recently Failed</h2>
        <table>
          <thead><tr><th></th><th>Prompt</th><th>User</th><th>Dept</th><th>Status</th><th>Time</th><th></th></tr></thead>
          <tbody>
            {failed.map(p => renderRow(p,
              <button className="btn sm" onClick={() => action(p.id, 'retry')}>Retry</button>))}
            {failed.length === 0 && <tr><td colSpan={7} className="muted">No failed jobs 🎉</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
