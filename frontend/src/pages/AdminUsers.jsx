import React, { useEffect, useState } from 'react'
import { api } from '../api'

const EMPTY = { username: '', password: '', full_name: '', department: '', email: '', role: 'staff' }

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = async () => {
    try { setUsers(await api('/users')) } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const create = async (e) => {
    e.preventDefault()
    setError(''); setNotice('')
    try {
      const body = { ...form }
      if (!body.email) delete body.email
      await api('/users', { method: 'POST', body })
      setNotice(`User ${form.username} created`)
      setForm(EMPTY)
      load()
    } catch (err) { setError(err.message) }
  }

  const toggleActive = async (u) => {
    try {
      if (u.is_active) await api(`/users/${u.id}`, { method: 'DELETE' })
      else await api(`/users/${u.id}`, { method: 'PATCH', body: { is_active: true } })
      load()
    } catch (err) { setError(err.message) }
  }

  const resetPassword = async (u) => {
    const password = window.prompt(`New password for ${u.username} (min 8 chars):`)
    if (!password) return
    try { await api(`/users/${u.id}`, { method: 'PATCH', body: { password } }); setNotice('Password updated') }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <h1>Users</h1>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}

      <div className="card">
        <h2>Add User</h2>
        <form onSubmit={create} className="grid cols-4">
          <div><label>Username</label><input value={form.username} onChange={set('username')} required /></div>
          <div><label>Password</label><input type="password" value={form.password} onChange={set('password')} required minLength={8} /></div>
          <div><label>Full name</label><input value={form.full_name} onChange={set('full_name')} /></div>
          <div><label>Department</label><input value={form.department} onChange={set('department')} /></div>
          <div><label>Email</label><input type="email" value={form.email} onChange={set('email')} /></div>
          <div><label>Role</label>
            <select value={form.role} onChange={set('role')}>
              <option value="staff">staff</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <div style={{ alignSelf: 'end' }}><button className="btn">Create</button></div>
        </form>
      </div>

      <div className="card">
        <table>
          <thead><tr><th>User</th><th>Department</th><th>Role</th><th>Status</th><th>Last login</th><th></th></tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td>{u.full_name || u.username} <span className="muted">@{u.username}</span></td>
                <td>{u.department || '—'}</td>
                <td><span className={`badge ${u.role === 'admin' ? 'processing' : 'cancelled'}`}>{u.role}</span></td>
                <td><span className={`badge ${u.is_active ? 'online' : 'offline'}`}>{u.is_active ? 'active' : 'disabled'}</span></td>
                <td className="muted">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'never'}</td>
                <td className="row">
                  <button className="btn secondary sm" onClick={() => resetPassword(u)}>Reset PW</button>
                  <button className={`btn sm ${u.is_active ? 'danger' : ''}`} onClick={() => toggleActive(u)}>
                    {u.is_active ? 'Disable' : 'Enable'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
