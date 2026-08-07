import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, NavLink, Link } from 'react-router-dom'
import { api, getTokens, setTokens } from './api'
import { connectEvents } from './ws'
import Onboarding from './Onboarding'
import Login from './pages/Login'
import StaffHome from './pages/StaffHome'
import PromptDetail from './pages/PromptDetail'
import Templates from './pages/Templates'
import Scheduled from './pages/Scheduled'
import Notifications from './pages/Notifications'
import Developer from './pages/Developer'
import AdminHome from './pages/AdminHome'
import AdminQueue from './pages/AdminQueue'
import AdminUsers from './pages/AdminUsers'
import AdminLogs from './pages/AdminLogs'
import AdminSettings from './pages/AdminSettings'
import AdminUpdate from './pages/AdminUpdate'
import AdminAnalytics from './pages/AdminAnalytics'
import AdminSystem from './pages/AdminSystem'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem('aiauto_theme') || 'dark')
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('aiauto_theme', theme)
  }, [theme])
  return [theme, setTheme]
}

function Shell({ children }) {
  const { user, logout } = useAuth()
  const [theme, setTheme] = useTheme()
  const [unread, setUnread] = useState(0)
  const [announcement, setAnnouncement] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  // guided tour: automatic on the first login, replayable from "?"
  const [showTour, setShowTour] = useState(() => user && !user.onboarded)
  const isAdmin = user?.role === 'admin'

  const loadUnread = useCallback(async () => {
    try { setUnread((await api('/notifications?unread_only=true&page_size=1')).unread) }
    catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    loadUnread()
    api('/dashboard/announcement').then(r => setAnnouncement(r.announcement)).catch(() => {})
    const disconnect = connectEvents((event) => {
      if (event.type === 'notification.new') {
        loadUnread()
        if ('Notification' in window && Notification.permission === 'granted') {
          try { new Notification('AIAuto', { body: event.data?.title || 'Update' }) } catch { /* noop */ }
        }
      }
    })
    return disconnect
  }, [loadUnread])

  const nav = (
    <>
      <NavLink to="/" end onClick={() => setMenuOpen(false)}>Dashboard</NavLink>
      <NavLink to="/templates" onClick={() => setMenuOpen(false)}>Templates</NavLink>
      <NavLink to="/scheduled" onClick={() => setMenuOpen(false)}>Scheduled</NavLink>
      <NavLink to="/developer" onClick={() => setMenuOpen(false)}>API</NavLink>
      {isAdmin && <NavLink to="/queue" onClick={() => setMenuOpen(false)}>Queue</NavLink>}
      {isAdmin && <NavLink to="/users" onClick={() => setMenuOpen(false)}>Users</NavLink>}
      {isAdmin && <NavLink to="/analytics" onClick={() => setMenuOpen(false)}>Analytics</NavLink>}
      {isAdmin && <NavLink to="/system" onClick={() => setMenuOpen(false)}>System</NavLink>}
      {isAdmin && <NavLink to="/logs" onClick={() => setMenuOpen(false)}>Logs</NavLink>}
      {isAdmin && <NavLink to="/settings" onClick={() => setMenuOpen(false)}>Settings</NavLink>}
      {isAdmin && <NavLink to="/update" onClick={() => setMenuOpen(false)}>Update</NavLink>}
    </>
  )

  return (
    <div className="shell">
      <header className="topbar">
        <button className="btn ghost sm hamburger" onClick={() => setMenuOpen(o => !o)}>☰</button>
        <div className="brand">⚡ AIAuto</div>
        <nav className={menuOpen ? 'open' : ''}>{nav}</nav>
        <div className="userbox">
          <button className="btn ghost sm" title="Toggle theme"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? '☀' : '🌙'}
          </button>
          <button className="btn ghost sm" title="How to use AIAuto (guided tour)"
            onClick={() => setShowTour(true)}>?</button>
          <Link to="/notifications" className="bell" title="Notifications">
            🔔{unread > 0 && <span className="bell-badge">{unread > 99 ? '99+' : unread}</span>}
          </Link>
          <span className="username-label">{user?.full_name || user?.username} <em>({user?.role})</em></span>
          <button className="btn ghost sm" onClick={logout}>Logout</button>
        </div>
      </header>
      {announcement && <div className="announcement">📢 {announcement}</div>}
      <main className="content">{children}</main>
      {showTour && <Onboarding user={user} onFinish={() => setShowTour(false)} />}
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
          <Route path="/templates" element={<Protected><Templates /></Protected>} />
          <Route path="/scheduled" element={<Protected><Scheduled /></Protected>} />
          <Route path="/notifications" element={<Protected><Notifications /></Protected>} />
          <Route path="/developer" element={<Protected><Developer /></Protected>} />
          <Route path="/queue" element={<Protected admin><AdminQueue /></Protected>} />
          <Route path="/users" element={<Protected admin><AdminUsers /></Protected>} />
          <Route path="/analytics" element={<Protected admin><AdminAnalytics /></Protected>} />
          <Route path="/system" element={<Protected admin><AdminSystem /></Protected>} />
          <Route path="/logs" element={<Protected admin><AdminLogs /></Protected>} />
          <Route path="/settings" element={<Protected admin><AdminSettings /></Protected>} />
          <Route path="/update" element={<Protected admin><AdminUpdate /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </HashRouter>
    </AuthContext.Provider>
  )
}
