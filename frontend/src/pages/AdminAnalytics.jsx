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
  // seconds → human ("45s", "2m 10s"); null when there is no sample yet
  const fmt = (seconds) => {
    if (seconds == null) return '—'
    if (seconds < 60) return `${Math.round(seconds)}s`
    const m = Math.floor(seconds / 60)
    return `${m}m ${Math.round(seconds - m * 60)}s`
  }
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

      {data.timing && (
        <div className="card">
          <h2>Processing Time &amp; Load</h2>
          <div className="grid cols-4" style={{ marginBottom: 16 }}>
            <div className="stat"><div className="label">Success rate</div>
              <div className="value">{data.timing.success_rate != null
                ? `${data.timing.success_rate}%` : '—'}</div></div>
            <div className="stat"><div className="label">Image job (median)</div>
              <div className="value">{fmt(data.timing.images.median)}</div></div>
            <div className="stat"><div className="label">Text job (median)</div>
              <div className="value">{fmt(data.timing.text.median)}</div></div>
            <div className="stat"><div className="label">Queue wait (median)</div>
              <div className="value">{fmt(data.timing.queue_wait.median)}</div></div>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Type</th><th>Jobs</th><th>Average</th><th>Median</th>
                <th>Fastest</th><th>Slowest</th></tr></thead>
              <tbody>
                {[['Image jobs', data.timing.images], ['Text jobs', data.timing.text],
                  ['Queue wait', data.timing.queue_wait]].map(([label, s]) => (
                  <tr key={label}>
                    <td>{label}</td><td>{s.count}</td><td>{fmt(s.avg)}</td>
                    <td>{fmt(s.median)}</td><td>{fmt(s.fastest)}</td><td>{fmt(s.slowest)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 style={{ marginTop: 20 }}>Busiest hours (UTC)</h3>
          <BarChart data={data.timing.by_hour.map(h => ({
            hour: `${String(h.hour).padStart(2, '0')}h`, count: h.count,
          }))} xKey="hour" yKey="count" />
          <p className="muted" style={{ marginBottom: 0 }}>
            {data.timing.completed} completed · {data.timing.failed} failed ·
            based on the {data.timing.sampled} most recent jobs in this period.
          </p>
        </div>
      )}

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
