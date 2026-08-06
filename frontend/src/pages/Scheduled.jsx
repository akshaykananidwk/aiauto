import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const EMPTY = {
  title: '', prompt_text: '', wants_image: false, schedule_type: 'daily',
  interval_minutes: 60, run_at_time: '09:00', weekday: 0, run_once_at: '',
}
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function Scheduled() {
  const [schedules, setSchedules] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try { setSchedules(await api('/schedules')) } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    setError('')
    const body = {
      title: form.title, prompt_text: form.prompt_text, wants_image: form.wants_image,
      schedule_type: form.schedule_type,
    }
    if (form.schedule_type === 'interval') body.interval_minutes = Number(form.interval_minutes)
    if (['daily', 'weekly'].includes(form.schedule_type)) body.run_at_time = form.run_at_time
    if (form.schedule_type === 'weekly') body.weekday = Number(form.weekday)
    if (form.schedule_type === 'once') body.run_once_at = new Date(form.run_once_at).toISOString()
    try {
      await api('/schedules', { method: 'POST', body })
      setForm(EMPTY); setShowForm(false); load()
    } catch (err) { setError(err.message) }
  }

  const toggle = async (s) => {
    try { await api(`/schedules/${s.id}`, { method: 'PATCH', body: { is_active: !s.is_active } }); load() }
    catch (err) { setError(err.message) }
  }
  const remove = async (s) => {
    if (!window.confirm(`Delete schedule "${s.title}"?`)) return
    try { await api(`/schedules/${s.id}`, { method: 'DELETE' }); load() }
    catch (err) { setError(err.message) }
  }

  const describe = (s) => {
    if (s.schedule_type === 'interval') return `every ${s.interval_minutes} min`
    if (s.schedule_type === 'daily') return `daily at ${s.run_at_time} UTC`
    if (s.schedule_type === 'weekly') return `${WEEKDAYS[s.weekday ?? 0]} at ${s.run_at_time} UTC`
    return 'one time'
  }

  return (
    <div>
      <div className="row between">
        <h1>Scheduled Prompts</h1>
        <button className="btn" onClick={() => setShowForm(s => !s)}>{showForm ? 'Close' : '+ New Schedule'}</button>
      </div>
      {error && <div className="alert error">{error}</div>}

      {showForm && (
        <form className="card" onSubmit={create}>
          <label>Title</label>
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} required />
          <label>Prompt</label>
          <textarea value={form.prompt_text} onChange={e => setForm(f => ({ ...f, prompt_text: e.target.value }))} required />
          <div className="grid cols-4">
            <div><label>Repeat</label>
              <select value={form.schedule_type} onChange={e => setForm(f => ({ ...f, schedule_type: e.target.value }))}>
                <option value="once">Once</option>
                <option value="interval">Every N minutes</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>
            {form.schedule_type === 'interval' && (
              <div><label>Interval (minutes)</label>
                <input type="number" min="5" max="10080" value={form.interval_minutes}
                  onChange={e => setForm(f => ({ ...f, interval_minutes: e.target.value }))} /></div>
            )}
            {['daily', 'weekly'].includes(form.schedule_type) && (
              <div><label>Time (UTC)</label>
                <input type="time" value={form.run_at_time}
                  onChange={e => setForm(f => ({ ...f, run_at_time: e.target.value }))} /></div>
            )}
            {form.schedule_type === 'weekly' && (
              <div><label>Weekday</label>
                <select value={form.weekday} onChange={e => setForm(f => ({ ...f, weekday: e.target.value }))}>
                  {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select></div>
            )}
            {form.schedule_type === 'once' && (
              <div><label>Run at</label>
                <input type="datetime-local" value={form.run_once_at}
                  onChange={e => setForm(f => ({ ...f, run_once_at: e.target.value }))} required /></div>
            )}
            <div style={{ alignSelf: 'end' }}>
              <label className="row" style={{ margin: 0 }}>
                <input type="checkbox" style={{ width: 'auto' }} checked={form.wants_image}
                  onChange={e => setForm(f => ({ ...f, wants_image: e.target.checked }))} />
                &nbsp;Image
              </label>
            </div>
          </div>
          <div style={{ marginTop: 16 }}><button className="btn">Create Schedule</button></div>
        </form>
      )}

      <div className="card">
        <table>
          <thead><tr><th>Title</th><th>Schedule</th><th>Next run</th><th>Last run</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {schedules.map(s => (
              <tr key={s.id}>
                <td><b>{s.title}</b><div className="muted">{s.prompt_text.slice(0, 60)}…</div></td>
                <td>{describe(s)}</td>
                <td className="muted">{s.next_run_at ? new Date(s.next_run_at).toLocaleString() : '—'}</td>
                <td className="muted">
                  {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : 'never'}
                  {s.last_prompt_id && <> · <Link to={`/prompt/${s.last_prompt_id}`}>result</Link></>}
                </td>
                <td><span className={`badge ${s.is_active ? 'online' : 'offline'}`}>{s.is_active ? 'active' : 'paused'}</span></td>
                <td className="row" style={{ gap: 6 }}>
                  <button className="btn ghost sm" onClick={() => toggle(s)}>{s.is_active ? 'Pause' : 'Resume'}</button>
                  <button className="btn ghost sm" onClick={() => remove(s)}>Delete</button>
                </td>
              </tr>
            ))}
            {schedules.length === 0 && <tr><td colSpan={6} className="muted">No scheduled prompts.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
