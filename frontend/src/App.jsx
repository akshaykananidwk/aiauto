import React, { createContext, useContext, useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import { api, getTokens, setTokens } from './api'
import Login from './pages/Login'
import StaffHome from './pages/StaffHome'
import PromptDetail from './pages/PromptDetail'
import AdminHome from './pages/AdminHome'
import AdminQueue from './pages/AdminQueue'
import AdminUsers from './pages/AdminUsers'
import AdminLogs from './pages/AdminLogs'
import AdminSettings from './pages/AdminSettings'
import AdminUpdate from './pages/AdminUpdate'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

function Shell({ children }) {
  const { user, logout } = useAuth()
  const isAdmin = user?.role === 'admin'
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">⚡ AIAuto</div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          {isAdmin && <NavLink to="/queue">Queue</NavLink>}
          {isAdmin && <NavLink to="/users">Users</NavLink>}
          {isAdmin && <NavLink to="/logs">Logs</NavLink>}
          {isAdmin && <NavLink to="/settings">Settings</NavLink>}
          {isAdmin && <NavLink to="/update">Update</NavLink>}
        </nav>
        <div className="userbox">
          <span>{user?.full_name || user?.username} <em>({user?.role})</em></span>
          <button className="btn ghost" onClick={logout}>Logout</button>
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  )
}

function Protected({ admin = false, children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center-msg">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  return <Shell>{children}</Shell>
}

function RoleHome() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <AdminHome /> : <StaffHome />
}

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      if (getTokens()) {
        try { setUser(await api('/auth/me')) } catch { setTokens(null) }
      }
      setLoading(false)
    })()
  }, [])

  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch { /* best-effort */ }
    setTokens(null)
    setUser(null)
    window.location.hash = '#/login'
  }

  return (
    <AuthContext.Provider value={{ user, setUser, loading, logout }}>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Protected><RoleHome /></Protected>} />
          <Route path="/prompt/:id" element={<Protected><PromptDetail /></Protected>} />
          <Route path="/queue" element={<Protected admin><AdminQueue /></Protected>} />
          <Route path="/users" element={<Protected admin><AdminUsers /></Protected>} />
          <Route path="/logs" element={<Protected admin><AdminLogs /></Protected>} />
          <Route path="/settings" element={<Protected admin><AdminSettings /></Protected>} />
          <Route path="/update" element={<Protected admin><AdminUpdate /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </HashRouter>
    </AuthContext.Provider>
  )
}
