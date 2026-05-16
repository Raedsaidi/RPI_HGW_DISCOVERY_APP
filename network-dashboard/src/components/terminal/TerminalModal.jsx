import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const toWsBase = (httpUrl) =>
  httpUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')

const nowTime = () => new Date().toISOString().slice(11, 19)

const chunkString = (str, size) => {
  if (!str) return []
  if (str.length <= size) return [str]
  const out = []
  for (let i = 0; i < str.length; i += size) out.push(str.slice(i, i + size))
  return out
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const TerminalModal = ({
  open,
  onClose,
  title,

  deviceType,
  targetLabel,
  targetKey,

  apiOpen,
  apiList,
  apiClose,
  wsPathForSession,

  autoStart = true,

  // ✅ plus robuste contre proxy/NAT agressif
  pingIntervalMs = 5000,

  inputChunkSize = 1500,

  // reconnect
  autoReconnect = true,
  reconnectDelayMs = 1200,
  reconnectMaxAttempts = 5,
}) => {
  const termDivRef = useRef(null)
  const xtermRef = useRef(null)
  const fitRef = useRef(null)

  const wsRef = useRef(null)
  const pingTimerRef = useRef(null)
  const onDataDisposableRef = useRef(null)
  const resizeHandlerRef = useRef(null)
  const openedOnceRef = useRef(false)

  const lastListedSessionsRef = useRef([])
  const [activeSessionId, setActiveSessionId] = useState(null)

  const reconnectAttemptsRef = useRef(0)
  const wantReconnectRef = useRef(false)

  const wsBase = useMemo(() => toWsBase(import.meta.env.VITE_DISCOVERY_URL), [])

  const termPrint = useCallback((line = '') => {
    if (!xtermRef.current) return
    xtermRef.current.writeln(`[${nowTime()}] ${line}`)
  }, [])

  const initXterm = useCallback(() => {
    if (xtermRef.current) return

    xtermRef.current = new XTerm({
      cursorBlink: true,
      fontSize: 12,
      fontFamily: 'Consolas, Menlo, Monaco, "Courier New", monospace',
      theme: { background: '#0b1020' },
      scrollback: 8000,
    })

    fitRef.current = new FitAddon()
    xtermRef.current.loadAddon(fitRef.current)

    xtermRef.current.open(termDivRef.current)
    fitRef.current.fit()

    xtermRef.current.attachCustomKeyEventHandler((ev) => {
      if (ev.key === 'Escape') {
        ev.preventDefault()
        onClose?.()
        return false
      }

      if (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyN') {
        ev.preventDefault()
        handleNewSession()
        return false
      }

      if (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyS') {
        ev.preventDefault()
        handleListSessions()
        return false
      }

      if (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyK') {
        ev.preventDefault()
        handleCloseSession()
        return false
      }

      if (ev.altKey && !ev.ctrlKey && !ev.shiftKey) {
        const key = ev.key
        if (key >= '1' && key <= '9') {
          ev.preventDefault()
          const idx = Number(key) - 1
          const list = lastListedSessionsRef.current || []
          const target = list[idx]
          if (target?.session_id) {
            termPrint(`ATTACH -> ${target.session_id}`)
            attach(target.session_id)
          } else {
            termPrint(`No session at index ${key}. Press Ctrl+Shift+S to list sessions.`)
          }
          return false
        }
      }

      return true
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const cleanupWsAndHandlers = useCallback((opts = { disposeXterm: false }) => {
    wantReconnectRef.current = false

    try { clearInterval(pingTimerRef.current) } catch {}
    pingTimerRef.current = null

    try { wsRef.current?.close() } catch {}
    wsRef.current = null

    try { onDataDisposableRef.current?.dispose?.() } catch {}
    onDataDisposableRef.current = null

    if (resizeHandlerRef.current) {
      window.removeEventListener('resize', resizeHandlerRef.current)
      resizeHandlerRef.current = null
    }

    if (opts.disposeXterm) {
      try { xtermRef.current?.dispose?.() } catch {}
      xtermRef.current = null
      fitRef.current = null
    }
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      const res = await apiList()
      return res.data?.data || []
    } catch {
      return []
    }
  }, [apiList])

  const attach = useCallback(async (sessionId) => {
    if (!sessionId) return

    initXterm()
    cleanupWsAndHandlers({ disposeXterm: false })

    reconnectAttemptsRef.current = 0
    wantReconnectRef.current = true

    setActiveSessionId(sessionId)
    xtermRef.current.clear()
    termPrint(`Connecting (session=${sessionId}) ...`)

    const wsUrl = `${wsBase}${wsPathForSession(sessionId)}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    const sendPing = () => {
      try { wsRef.current?.send(JSON.stringify({ type: 'ping' })) } catch {}
    }

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0

      const token = localStorage.getItem('nd_access_token')
      if (!token) {
        termPrint('ERROR: missing token (nd_access_token)')
        try { ws.close() } catch {}
        return
      }

      ws.send(JSON.stringify({ type: 'auth', token }))

      termPrint(title || `TERMINAL — ${deviceType.toUpperCase()} ${targetLabel}`)
      termPrint(`Key=${String(targetKey)}`)
      termPrint('Hotkeys: Esc(close overlay) Ctrl+Shift+N(new) Ctrl+Shift+S(list) Alt+1..9(attach) Ctrl+Shift+K(close session)')

      try {
        const cols = xtermRef.current.cols
        const rows = xtermRef.current.rows
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      } catch {}

      // ✅ ping immédiat + interval
      sendPing()
      pingTimerRef.current = setInterval(sendPing, pingIntervalMs)
    }

    ws.onmessage = (ev) => {
      let msg
      try { msg = JSON.parse(ev.data) } catch { return }

      if (msg.type === 'buffer') {
        if (msg.data) xtermRef.current.write(msg.data)
      } else if (msg.type === 'output') {
        if (msg.data) xtermRef.current.write(msg.data)
      } else if (msg.type === 'status') {
        if (msg.status === 'error') {
          termPrint(`ERROR: ${msg.error || 'terminal error'}`)
        } else if (msg.status === 'closed') {
          termPrint('SESSION CLOSED by server.')
          cleanupWsAndHandlers({ disposeXterm: false })
        }
      }
    }

    ws.onerror = () => termPrint('WS ERROR')

    ws.onclose = async () => {
      try { clearInterval(pingTimerRef.current) } catch {}
      pingTimerRef.current = null

      termPrint('WS CLOSED')

      if (!open) return
      if (!autoReconnect) return
      if (!wantReconnectRef.current) return
      if (!activeSessionId) return

      reconnectAttemptsRef.current += 1
      if (reconnectAttemptsRef.current > reconnectMaxAttempts) {
        termPrint(`Reconnect failed after ${reconnectMaxAttempts} attempts.`)
        return
      }

      termPrint(`Reconnecting... attempt ${reconnectAttemptsRef.current}/${reconnectMaxAttempts}`)
      await sleep(reconnectDelayMs)

      // Reattach if session still exists, else open new
      const list = await loadSessions()
      const stillThere = list.find((s) => s.session_id === activeSessionId)
      if (stillThere) {
        await attach(activeSessionId)
      } else {
        termPrint('Session not found on server anymore. Creating a new session...')
        await handleNewSession()
      }
    }

    onDataDisposableRef.current = xtermRef.current.onData((data) => {
      const parts = chunkString(data, inputChunkSize)
      for (const p of parts) {
        try { wsRef.current?.send(JSON.stringify({ type: 'input', data: p })) } catch {}
      }
    })

    const onResize = () => {
      try {
        fitRef.current?.fit()
        const cols = xtermRef.current.cols
        const rows = xtermRef.current.rows
        wsRef.current?.send(JSON.stringify({ type: 'resize', cols, rows }))
      } catch {}
    }
    resizeHandlerRef.current = onResize
    window.addEventListener('resize', onResize)
  }, [
    activeSessionId,
    autoReconnect,
    cleanupWsAndHandlers,
    deviceType,
    initXterm,
    inputChunkSize,
    loadSessions,
    pingIntervalMs,
    reconnectDelayMs,
    reconnectMaxAttempts,
    targetKey,
    targetLabel,
    title,
    termPrint,
    wsBase,
    wsPathForSession,
  ])

  const handleNewSession = useCallback(async () => {
    initXterm()
    termPrint(`NEW SESSION for ${deviceType.toUpperCase()} ${targetLabel} ...`)

    try {
      const res = await apiOpen()
      const sessionId = res.data?.session_id
      if (!sessionId) {
        termPrint('ERROR: backend did not return session_id')
        return
      }
      termPrint(`NEW SESSION: ${sessionId}`)
      await attach(sessionId)
    } catch (e) {
      termPrint(`ERROR: ${e?.response?.data?.detail || e.message || 'open failed'}`)
    }
  }, [apiOpen, attach, deviceType, initXterm, targetLabel, termPrint])

  const handleListSessions = useCallback(async () => {
    initXterm()
    termPrint('Listing active sessions...')
    const list = await loadSessions()
    lastListedSessionsRef.current = list

    if (!list.length) {
      termPrint('No active sessions. Press Ctrl+Shift+N to create a new one.')
      return
    }

    termPrint('Sessions (Alt+1..9 to attach):')
    list.slice(0, 9).forEach((s, idx) => {
      const via = s.via_rpi_ip ? ` via=${s.via_rpi_ip}` : ''
      termPrint(`${idx + 1}) ${s.session_id} status=${s.status} attached=${s.attached}${via}`)
    })
  }, [initXterm, loadSessions, termPrint])

  const handleCloseSession = useCallback(async () => {
    if (!activeSessionId) {
      termPrint('No active session to close.')
      return
    }
    termPrint(`Closing session ${activeSessionId} ...`)
    try {
      await apiClose(activeSessionId)
      cleanupWsAndHandlers({ disposeXterm: false })
      setActiveSessionId(null)
      termPrint('Session closed.')
    } catch (e) {
      termPrint(`ERROR: ${e?.response?.data?.detail || e.message || 'close failed'}`)
    }
  }, [activeSessionId, apiClose, cleanupWsAndHandlers, termPrint])

  const openWithResumeOrNew = useCallback(async () => {
    initXterm()
    termPrint('========================================')
    termPrint(title || `DISCOVERY TERMINAL — ${deviceType.toUpperCase()} ${targetLabel}`)
    termPrint('Trying to resume last session...')

    const list = await loadSessions()
    if (list.length > 0) {
      const sid = list[0].session_id
      termPrint(`Resuming session: ${sid}`)
      await attach(sid)
      return
    }

    termPrint('No session to resume. Creating a new one...')
    await handleNewSession()
  }, [attach, deviceType, handleNewSession, initXterm, loadSessions, targetLabel, title, termPrint])

  useEffect(() => {
    if (!open) {
      openedOnceRef.current = false
      cleanupWsAndHandlers({ disposeXterm: true })
      return
    }

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    if (!openedOnceRef.current) {
      openedOnceRef.current = true
      if (autoStart) openWithResumeOrNew()
      else handleListSessions()
    }

    return () => {
      document.body.style.overflow = prevOverflow
      cleanupWsAndHandlers({ disposeXterm: true })
    }
  }, [open, autoStart, cleanupWsAndHandlers, openWithResumeOrNew, handleListSessions])

  if (!open) return null

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: '#0b1020' }}>
      <div ref={termDivRef} style={{ width: '100vw', height: '100vh', background: '#0b1020' }} />
    </div>
  )
}

export default TerminalModal