import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setTokens } from '../api'
import { useAuth } from '../App'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, computer_name: navigator.userAgent.slice(0, 120) }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Login failed')
      setTokens(await res.json())
      setUser(await api('/auth/me'))
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand">⚡ AIAuto</div>
        {error && <div className="alert error">{error}</div>}
        <label>Username</label>
        <input value={username} onChange={e => setUsername(e.target.value)} autoFocus required />
        <label>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        <div style={{ marginTop: 20 }}>
          <button className="btn" style={{ width: '100%' }} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      </form>
    </div>
  )
}
