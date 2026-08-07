import React, { useState } from 'react'
import { api } from './api'

// First-run guided tour. Shown once per user account (the server stores
// the flag, so it does not reappear on another computer) and replayable
// any time from the "?" button in the header.

const STAFF_STEPS = [
  {
    icon: '👋',
    title: 'Welcome to AIAuto',
    body: 'This is your team\'s shared AI assistant. You write what you need, '
      + 'the central computer does the work, and the result comes back here. '
      + 'It takes about a minute to learn everything.',
  },
  {
    icon: '✍️',
    title: 'Write your request',
    body: 'Type what you want in the big box — in Gujarati, Hindi or English, '
      + 'whatever you prefer. Not sure how to word it? Press ✨ Improve prompt '
      + 'and the AI rewrites it properly for you (↩ Undo brings your words back).',
  },
  {
    icon: '🎨',
    title: 'Want a picture?',
    body: 'Tick "Generate image" and pick an output size (square, story, '
      + 'landscape, A4 print…). You can also attach a photo — it will be used '
      + 'as a reference: "make one like this".',
  },
  {
    icon: '⏳',
    title: 'Results take a little time',
    body: 'Jobs run one after another on the central computer, so an image '
      + 'usually takes a few minutes. You do not have to wait on the page — '
      + 'the status updates itself and your history keeps everything.',
  },
  {
    icon: '💾',
    title: 'Use your result',
    body: 'Open a job to see the answer with proper formatting. Copy it (keeps '
      + 'bold and tables), download the audio, click an image to view, copy or '
      + 'download it — and use 💬 Ask a follow-up for "make it shorter" or '
      + '"same image at sunset".',
  },
  {
    icon: '📚',
    title: 'Save time with templates',
    body: 'The Prompt Library stores requests you use often. Put {{blanks}} in '
      + 'them and you will be asked to fill those in each time — one template, '
      + 'many uses.',
  },
]

const ADMIN_STEPS = [
  {
    icon: '🛠️',
    title: 'You are an administrator',
    body: 'Besides everything staff can do, you control the platform: Users, '
      + 'Queue, Analytics, System health, Settings and one-click Updates.',
  },
  {
    icon: '🖥️',
    title: 'Keep an eye on System',
    body: 'System health shows workers, Chrome, disk and — when an image fails '
      + 'to capture — a screenshot of exactly what the AI page showed. '
      + 'Analytics shows how long jobs take and the busiest hours.',
  },
  {
    icon: '⚙️',
    title: 'Settings worth knowing',
    body: 'Timeouts and retries, the English image instruction added to image '
      + 'prompts, automatic cleanup of old files, and the audio engine all live '
      + 'in Settings. Updates install new versions with an automatic backup.',
  },
]

export default function Onboarding({ user, onFinish }) {
  const steps = [...STAFF_STEPS, ...(user?.role === 'admin' ? ADMIN_STEPS : [])]
  const [index, setIndex] = useState(0)
  const [saving, setSaving] = useState(false)
  const step = steps[index]
  const last = index === steps.length - 1

  const finish = async () => {
    setSaving(true)
    try { await api('/auth/onboarded', { method: 'POST', body: { done: true } }) }
    catch { /* the tour must close even if the flag cannot be saved */ }
    finally { setSaving(false); onFinish() }
  }

  return (
    <div className="viewer-overlay" role="dialog" aria-modal="true">
      <div className="viewer" style={{ maxWidth: 560 }} onClick={e => e.stopPropagation()}>
        <div style={{ fontSize: 44, textAlign: 'center' }}>{step.icon}</div>
        <h2 style={{ textAlign: 'center', marginTop: 8 }}>{step.title}</h2>
        <p style={{ lineHeight: 1.6 }}>{step.body}</p>

        <div className="row" style={{ gap: 6, justifyContent: 'center', margin: '18px 0' }}>
          {steps.map((_, x) => (
            <span key={x} aria-hidden="true" style={{
              width: x === index ? 22 : 8, height: 8, borderRadius: 4,
              background: x === index ? 'var(--accent, #4f7cff)' : 'var(--muted, #9aa)',
              opacity: x === index ? 1 : 0.4, transition: 'width .2s',
            }} />
          ))}
        </div>

        <div className="row between" style={{ flexWrap: 'wrap', gap: 8 }}>
          <button className="btn ghost sm" onClick={finish} disabled={saving}>
            Skip the tour
          </button>
          <span className="row" style={{ gap: 8 }}>
            {index > 0 && (
              <button className="btn secondary" onClick={() => setIndex(i => i - 1)}>
                ← Back
              </button>
            )}
            {last
              ? <button className="btn" onClick={finish} disabled={saving}>
                  {saving ? 'Finishing…' : 'Start using AIAuto ✓'}
                </button>
              : <button className="btn" onClick={() => setIndex(i => i + 1)}>
                  Next → <span className="muted">({index + 1}/{steps.length})</span>
                </button>}
          </span>
        </div>
      </div>
    </div>
  )
}
