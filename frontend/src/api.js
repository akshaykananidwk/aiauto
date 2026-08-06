// Thin fetch wrapper with JWT auth + automatic token refresh.
const BASE = '/api/v1'

export function getTokens() {
  try { return JSON.parse(localStorage.getItem('aiauto_tokens')) || null } catch { return null }
}
export function setTokens(tokens) {
  if (tokens) localStorage.setItem('aiauto_tokens', JSON.stringify(tokens))
  else localStorage.removeItem('aiauto_tokens')
}

async function refreshTokens() {
  const tokens = getTokens()
  if (!tokens?.refresh_token) return null
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  })
  if (!res.ok) { setTokens(null); return null }
  const fresh = await res.json()
  setTokens(fresh)
  return fresh
}

export async function api(path, { method = 'GET', body, formData, raw = false } = {}) {
  const doFetch = async (accessToken) => {
    const headers = {}
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`
    if (body) headers['Content-Type'] = 'application/json'
    return fetch(`${BASE}${path}`, {
      method,
      headers,
      body: formData ? formData : body ? JSON.stringify(body) : undefined,
    })
  }

  let res = await doFetch(getTokens()?.access_token)
  if (res.status === 401) {
    const fresh = await refreshTokens()
    if (!fresh) { window.location.hash = '#/login'; throw new Error('Session expired') }
    res = await doFetch(fresh.access_token)
  }
  if (raw) return res
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try { detail = (await res.json()).detail || detail } catch { /* keep default */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return null
  return res.json()
}

export async function downloadFile(fileId, filename) {
  const res = await api(`/files/${fileId}/download`, { raw: true })
  if (!res.ok) throw new Error('Download failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function thumbnailUrl(fileId) {
  const res = await api(`/files/${fileId}/thumbnail`, { raw: true })
  if (!res.ok) return null
  return URL.createObjectURL(await res.blob())
}
