import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../App'

const EMPTY = { title: '', body: '', category: '', tags: '', is_shared: false }

export default function Templates() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState([])
  const [categories, setCategories] = useState([])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [editing, setEditing] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (category) params.set('category', category)
      if (favoritesOnly) params.set('favorites_only', 'true')
      const [list, cats] = await Promise.all([
        api(`/templates?${params}`),
        api('/templates/categories'),
      ])
      setTemplates(list)
      setCategories(cats)
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [search, category, favoritesOnly])

  const save = async (e) => {
    e.preventDefault()
    setError('')
    const body = {
      title: form.title, body: form.body, category: form.category,
      tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
      is_shared: form.is_shared,
    }
    try {
      if (editing) await api(`/templates/${editing}`, { method: 'PATCH', body })
      else await api('/templates', { method: 'POST', body })
      setForm(EMPTY); setEditing(null); setShowForm(false)
      load()
    } catch (err) { setError(err.message) }
  }

  const use = async (tpl) => {
    try { await api(`/templates/${tpl.id}/use`, { method: 'POST' }) } catch { /* count only */ }
    localStorage.setItem('aiauto_draft', tpl.body)
    navigate('/')
  }

  const favorite = async (tpl) => {
    try { await api(`/templates/${tpl.id}/favorite`, { method: 'POST' }); load() }
    catch (err) { setError(err.message) }
  }

  const edit = (tpl) => {
    setEditing(tpl.id)
    setForm({ title: tpl.title, body: tpl.body, category: tpl.category,
              tags: (tpl.tags || []).join(', '), is_shared: tpl.is_shared })
    setShowForm(true)
  }

  const remove = async (tpl) => {
    if (!window.confirm(`Delete template "${tpl.title}"?`)) return
    try { await api(`/templates/${tpl.id}`, { method: 'DELETE' }); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="row between">
        <h1>Prompt Library</h1>
        <button className="btn" onClick={() => { setShowForm(s => !s); setEditing(null); setForm(EMPTY) }}>
          {showForm ? 'Close' : '+ New Template'}
        </button>
      </div>
      {error && <div className="alert error">{error}</div>}

      {showForm && (
        <form className="card" onSubmit={save}>
          <h2>{editing ? 'Edit Template' : 'New Template'}</h2>
          <label>Title</label>
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} required />
          <label>Prompt text</label>
          <textarea value={form.body} onChange={e => setForm(f => ({ ...f, body: e.target.value }))} required />
          <div className="grid cols-2">
            <div><label>Category</label>
              <input value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                placeholder="e.g. Marketing" list="tpl-cats" />
              <datalist id="tpl-cats">{categories.map(c => <option key={c} value={c} />)}</datalist>
            </div>
            <div><label>Tags (comma-separated)</label>
              <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
                placeholder="report, weekly" /></div>
          </div>
          <label className="row" style={{ marginTop: 12 }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={form.is_shared}
              onChange={e => setForm(f => ({ ...f, is_shared: e.target.checked }))} />
            &nbsp;Share with the whole team
          </label>
          <div style={{ marginTop: 16 }}><button className="btn">{editing ? 'Save Changes' : 'Create'}</button></div>
        </form>
      )}

      <div className="card">
        <div className="row" style={{ marginBottom: 16 }}>
          <input style={{ maxWidth: 260 }} placeholder="Search templates…"
            value={search} onChange={e => setSearch(e.target.value)} />
          <select style={{ maxWidth: 180 }} value={category} onChange={e => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <label className="row" style={{ margin: 0 }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={favoritesOnly}
              onChange={e => setFavoritesOnly(e.target.checked)} />&nbsp;★ Favorites
          </label>
        </div>

        <div className="tpl-grid">
          {templates.map(tpl => (
            <div key={tpl.id} className="tpl-card">
              <div className="row between">
                <b>{tpl.title}</b>
                <button className="star" onClick={() => favorite(tpl)}
                  title="Favorite">{tpl.is_favorite ? '★' : '☆'}</button>
              </div>
              <div className="muted tpl-body">{tpl.body.slice(0, 140)}{tpl.body.length > 140 ? '…' : ''}</div>
              <div className="row" style={{ marginTop: 8, flexWrap: 'wrap', gap: 6 }}>
                {tpl.category && <span className="badge processing">{tpl.category}</span>}
                {(tpl.tags || []).map(t => <span key={t} className="badge cancelled">#{t}</span>)}
                {tpl.is_shared && <span className="badge completed">shared</span>}
              </div>
              <div className="row between" style={{ marginTop: 10 }}>
                <span className="muted">used {tpl.usage_count}× · {tpl.owner_name || 'me'}</span>
                <span className="row" style={{ gap: 6 }}>
                  {(tpl.owner_id === user.id || user.role === 'admin') && (
                    <>
                      <button className="btn ghost sm" onClick={() => edit(tpl)}>Edit</button>
                      <button className="btn ghost sm" onClick={() => remove(tpl)}>Del</button>
                    </>
                  )}
                  <button className="btn sm" onClick={() => use(tpl)}>Use →</button>
                </span>
              </div>
            </div>
          ))}
          {templates.length === 0 && <div className="muted">No templates yet — create the first one.</div>}
        </div>
      </div>
    </div>
  )
}
