// Realtime updates over WebSocket with auto-reconnect.
import { getTokens } from './api'

export function connectEvents(onEvent) {
  let ws = null
  let closed = false
  let retry = 1000

  const connect = () => {
    const tokens = getTokens()
    if (!tokens?.access_token || closed) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${window.location.host}/api/v1/ws?token=${tokens.access_token}`)
    ws.onopen = () => { retry = 1000 }
    ws.onmessage = (msg) => {
      try { onEvent(JSON.parse(msg.data)) } catch { /* ignore malformed */ }
    }
    ws.onclose = () => {
      if (closed) return
      setTimeout(connect, retry)
      retry = Math.min(retry * 2, 15000)
    }
  }
  connect()
  const keepalive = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
  }, 25000)

  return () => { closed = true; clearInterval(keepalive); ws?.close() }
}
