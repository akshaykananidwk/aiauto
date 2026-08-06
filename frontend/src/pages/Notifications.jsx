import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { connectEvents } from '../ws'

const ICONS = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' }

export default function Notifications() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    try { setData(await api('/notifications?page_size=50')) } catch (err) { setError(err.message) }
  }
  useEffect(() => {
    load()
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
    const disconnect = connectEvents((event) => {
      if (event.type === 'notification.new') load()
    })
    return disconnect
  }, [])

  const markRead = async (n) => {
    try { await api(`/notifications/${n.id}/read`, { method: 'POST' }); load() }
    catch (err) { setError(err.message) }
  }
  const markAll = async () => {
    try { await api('/notifications/read-all', { method: 'POST' }); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="row between">
        <h1>Notifications {data?.unread > 0 && <span className="badge processing">{data.unread} unread</span>}</h1>
        <button className="btn secondary sm" onClick={markAll} disabled={!data?.unread}>Mark all read</button>
      </div>
      {error && <div className="alert error">{error}</div>}
      <div className="card">
        {(data?.items || []).map(n => (
          <div key={n.id} className={`notif ${n.is_read ? '' : 'unread'}`}>
            <span className="notif-icon">{ICONS[n.type] || 'ℹ️'}</span>
            <div className="notif-body">
              <b>{n.title}</b>
              {n.body && <div className="muted">{n.body}</div>}
              <div className="muted">{new Date(n.created_at).toLocaleString()}
                {n.meta?.prompt_id && <> · <Link to={`/prompt/${n.meta.prompt_id}`}>view prompt</Link></>}
              </div>
            </div>
            {!n.is_read && <button className="btn ghost sm" onClick={() => markRead(n)}>Mark read</button>}
          </div>
        ))}
        {(!data || data.items.length === 0) && <div className="muted">No notifications.</div>}
      </div>
    </div>
  )
}
