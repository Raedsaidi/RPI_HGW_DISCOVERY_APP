import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const toWsBase = (httpUrl) =>
  httpUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')

const nowTime = () => new Date().toISOString().slice(11, 19)

const TerminalModal = ({
  open,
  onClose,

  deviceType,
  targetLabel,

  apiOpen,
  apiList,
  apiClose,
  wsPathForSession,
}) => {
  const termDivRef = useRef(null)
  const xtermRef = useRef(null)
  const fitRef = useRef(null)

  const wsRef = useRef(null)
  const onDataDisposableRef = useRef(null)
  const resizeHandlerRef = useRef(null)
  const openedOnceRef = useRef(false)

  const lastListedSessionsRef = useRef([])
  const [activeSessionId, setActiveSessionId] = useState(null)

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
      // Esc => close overlay (detach only)
      if (ev.key === 'Escape') {
        ev.preventDefault()
        onClose?.()
        return false
      }

      // Ctrl+Shift+N => new session
      if (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyN') {
        ev.preventDefault()
        handleNewSession()
        return false
      }

      // Ctrl+Shift+S => list sessions
      if (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyS') {
        ev.preventDefault()
        handleListSessions()
        return false
      }

      // Ctrl+Shift+K => close current session (server close)
      if (ev.ctrlKey && ev.shiftKey && ev.code === 'KeyK') {
        ev.preventDefault()
        handleCloseSession()
        return false
      }

      // Alt+1..9 attach last listed
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

  const cleanupWsAndHandlers = useCallback(() => {
    try { wsRef.current?.close() } catch {}
    wsRef.current = null

    try { onDataDisposableRef.current?.dispose?.() } catch {}
    onDataDisposableRef.current = null

    if (resizeHandlerRef.current) {
      window.removeEventListener('resize', resizeHandlerRef.current)
      resizeHandlerRef.current = null
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
    cleanupWsAndHandlers()

    setActiveSessionId(sessionId)
    xtermRef.current.clear()

    termPrint(`Connecting (session=${sessionId}) ...`)

    const wsUrl = `${wsBase}${wsPathForSession(sessionId)}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      const token = localStorage.getItem('nd_access_token')
      ws.send(JSON.stringify({ type: 'auth', token }))

      termPrint(`CONNECTED — ${deviceType.toUpperCase()} ${targetLabel}`)
      termPrint('Hotkeys: Esc(close overlay) Ctrl+Shift+N(new) Ctrl+Shift+S(list) Alt+1..9(attach) Ctrl+Shift+K(close session)')

      try {
        const cols = xtermRef.current.cols
        const rows = xtermRef.current.rows
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      } catch {}
    }

    ws.onmessage = (ev) => {
      let msg
      try { msg = JSON.parse(ev.data) } catch { return }

      if (msg.type === 'buffer') {
        if (msg.data) xtermRef.current.write(msg.data)
      } else if (msg.type === 'output') {
        if (msg.data) xtermRef.current.write(msg.data)
      } else if (msg.type === 'status' && msg.status === 'error') {
        termPrint(`ERROR: ${msg.error || 'terminal error'}`)
      }
    }

    ws.onerror = () => termPrint('WS ERROR')
    ws.onclose = () => termPrint('WS CLOSED (resume: Ctrl+Shift+S then Alt+<n>)')

    onDataDisposableRef.current = xtermRef.current.onData((data) => {
      try { wsRef.current?.send(JSON.stringify({ type: 'input', data })) } catch {}
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
  }, [cleanupWsAndHandlers, deviceType, initXterm, targetLabel, termPrint, wsBase, wsPathForSession])

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
      cleanupWsAndHandlers()
      setActiveSessionId(null)
      termPrint('Session closed.')
    } catch (e) {
      termPrint(`ERROR: ${e?.response?.data?.detail || e.message || 'close failed'}`)
    }
  }, [activeSessionId, apiClose, cleanupWsAndHandlers, termPrint])

  const openWithResumeOrNew = useCallback(async () => {
    initXterm()
    termPrint('========================================')
    termPrint(`DISCOVERY TERMINAL — ${deviceType.toUpperCase()} ${targetLabel}`)
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
  }, [attach, deviceType, handleNewSession, initXterm, loadSessions, targetLabel, termPrint])

  useEffect(() => {
    if (!open) {
      openedOnceRef.current = false
      cleanupWsAndHandlers()
      return
    }

    // disable body scroll (optional)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    if (!openedOnceRef.current) {
      openedOnceRef.current = true
      openWithResumeOrNew()
    }

    return () => {
      document.body.style.overflow = prevOverflow
      cleanupWsAndHandlers()
    }
  }, [open, cleanupWsAndHandlers, openWithResumeOrNew])

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: '#0b1020',
      }}
      // click outside does NOTHING (no white overlay, no border)
    >
      <div
        ref={termDivRef}
        style={{
          width: '100vw',
          height: '100vh',
          background: '#0b1020',
        }}
      />
    </div>
  )
}

export default TerminalModal