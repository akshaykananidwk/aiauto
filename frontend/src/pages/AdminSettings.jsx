import React, { useEffect, useState } from 'react'
import { api } from '../api'

const FIELDS = [
  ['max_concurrent_jobs', 'Max concurrent jobs', 'number'],
  ['max_queue_size', 'Max queue size', 'number'],
  ['job_retry_count', 'Retry count', 'number'],
  ['job_timeout_seconds', 'Job timeout (s)', 'number'],
  ['response_timeout_seconds', 'AI response timeout (s)', 'number'],
  ['storage_limit_gb', 'Storage limit (GB)', 'number'],
  ['download_dir', 'Download directory', 'text'],
  ['browser_profile_path', 'Browser profile path', 'text'],
  ['backup_keep_count', 'Backups to keep', 'number'],
]

export default function AdminSettings() {
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    api('/admin/settings').then(setSettings).catch(err => setError(err.message))
  }, [])

  const save = async (e) => {
    e.preventDefault()
    setError(''); setNotice('')
    try {
      setSettings(await api('/admin/settings', { method: 'PUT', body: settings }))
      setNotice('Settings saved')
    } catch (err) { setError(err.message) }
  }

  if (!settings) return <div className="center-msg">Loading…</div>

  return (
    <div>
      <h1>Admin Settings</h1>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}
      <form className="card" onSubmit={save}>
        <div className="grid cols-2">
          {FIELDS.map(([key, label, type]) => (
            <div key={key}>
              <label>{label}</label>
              <input type={type} value={settings[key] ?? ''}
                onChange={e => setSettings(s => ({
                  ...s, [key]: type === 'number' ? Number(e.target.value) : e.target.value,
                }))} />
            </div>
          ))}
          <div>
            <label>Delete ChatGPT conversations after each run</label>
            <select value={String(settings.delete_conversations_after_run)}
              onChange={e => setSettings(s => ({ ...s, delete_conversations_after_run: e.target.value === 'true' }))}>
              <option value="true">Yes (keep account history clean)</option>
              <option value="false">No</option>
            </select>
          </div>
        </div>
        <div style={{ marginTop: 20 }}><button className="btn">Save Settings</button></div>
      </form>
    </div>
  )
}
