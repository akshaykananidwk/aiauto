import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { BarChart, HBarList } from '../components/Chart'

export default function AdminAnalytics() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/admin/analytics?days=${days}`).then(setData).catch(err => setError(err.message))
  }, [days])

  if (error) return <div className="alert error">{error}</div>
  if (!data) return <div className="center-msg">Loading analytics…</div>

  const t = data.totals
  return (
    <div>
      <div className="row between">
        <h1>Usage Analytics</h1>
        <select style={{ width: 160 }} value={days} onChange={e => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 20 }}>
        <div className="stat"><div className="label">Prompts</div><div className="value">{t.prompts}</div></div>
        <div className="stat"><div className="label">Images Generated</div><div className="value">{t.images}</div></div>
        <div className="stat"><div className="label">Avg. Processing</div>
          <div className="value">{t.avg_processing_seconds ? `${t.avg_processing_seconds}s` : '—'}</div></div>
      </div>

      <div className="card">
        <h2>Prompts per Day</h2>
        <BarChart data={data.daily} xKey="day" yKey="count" />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Top Users</h2>
          <HBarList data={data.top_users.map(u => ({ ...u, label: u.full_name || u.username }))}
            labelKey="label" valueKey="prompts" />
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>User</th><th>Department</th><th>Prompts</th></tr></thead>
            <tbody>
              {data.top_users.map(u => (
                <tr key={u.username}>
                  <td>{u.full_name || u.username}</td>
                  <td className="muted">{u.department || '—'}</td>
                  <td>{u.prompts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>By Department</h2>
          <HBarList data={data.by_department} labelKey="department" valueKey="prompts" />
        </div>
      </div>

      <div className="card row between">
        <span className="muted">Full audit trail export for compliance reviews.</span>
        <a className="btn secondary" href="#" onClick={async (e) => {
          e.preventDefault()
          const res = await api('/admin/analytics/audit-report', { raw: true })
          const blob = await res.blob()
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url; a.download = 'audit_report.csv'; a.click()
          URL.revokeObjectURL(url)
        }}>⬇ Download Audit Report (CSV)</a>
      </div>
    </div>
  )
}
