import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { connectEvents } from '../ws'

export default function AdminHome() {
  const [dash, setDash] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setDash(await api('/dashboard/admin')) } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 15000)
    const disconnect = connectEvents((event) => {
      if (event.type?.startsWith('prompt.') || event.type === 'queue.updated') load()
    })
    return () => { clearInterval(timer); disconnect() }
  }, [])

  if (error) return <div className="alert error">{error}</div>
  if (!dash) return <div className="center-msg">Loading…</div>

  const w = dash.worker
  return (
    <div>
      <h1>Admin Dashboard</h1>

      <div className="card">
        <h2>Automation Status</h2>
        <div className="row">
          <span className={`badge ${w.worker_online ? 'online' : 'offline'}`}>
            Worker {w.worker_online ? 'online' : 'OFFLINE'}</span>
          <span className={`badge ${w.chrome_connected ? 'online' : 'offline'}`}>
            Chrome {w.chrome_connected ? 'connected' : 'disconnected'}</span>
          <span className={`badge ${w.playwright_ready ? 'online' : 'offline'}`}>
            Playwright {w.playwright_ready ? 'ready' : 'not ready'}</span>
          <span className="badge processing">Provider: {w.provider}</span>
          {w.last_heartbeat && <span className="muted">last heartbeat {new Date(w.last_heartbeat).toLocaleTimeString()}</span>}
        </div>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 20 }}>
        <div className="stat"><div className="label">Waiting</div><div className="value">{dash.queue.waiting}</div></div>
        <div className="stat"><div className="label">Running</div><div className="value">{dash.queue.processing}</div></div>
        <div className="stat"><div className="label">Completed</div><div className="value">{dash.queue.completed}</div></div>
        <div className="stat"><div className="label">Failed</div><div className="value">{dash.queue.failed}</div></div>
      </div>
      <div className="grid cols-4" style={{ marginBottom: 20 }}>
        <div className="stat"><div className="label">Today</div><div className="value">{dash.usage.today}</div></div>
        <div className="stat"><div className="label">This Week</div><div className="value">{dash.usage.week}</div></div>
        <div className="stat"><div className="label">This Month</div><div className="value">{dash.usage.month}</div></div>
        <div className="stat"><div className="label">Total Prompts</div><div className="value">{dash.total_prompts}</div></div>
      </div>
      <div className="grid cols-4">
        <div className="stat"><div className="label">Users</div><div className="value">{dash.total_users}</div></div>
        <div className="stat"><div className="label">Images</div><div className="value">{dash.image_count}</div></div>
        <div className="stat"><div className="label">Files</div><div className="value">{dash.file_count}</div></div>
        <div className="stat"><div className="label">Storage</div><div className="value">{dash.storage_used_mb} <span style={{ fontSize: 14 }}>MB</span></div></div>
      </div>
    </div>
  )
}
