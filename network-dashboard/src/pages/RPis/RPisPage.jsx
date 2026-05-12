import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Cpu,
  RefreshCw,
  KeyRound,
  Eye,
  Trash2,
  CheckCircle,
  XCircle,
  Link2,
  Table2,
  LayoutList,
  PowerOff,
} from 'lucide-react'
import Card from '@/components/common/Card'
import Button from '@/components/common/Button'
import Table from '@/components/common/Table'
import SearchBar from '@/components/common/SearchBar'
import Pagination from '@/components/common/Pagination'
import { StatusBadge } from '@/components/common/Badge'
import Spinner from '@/components/common/Spinner'
import RpiDetailModal from './RpiDetailModal'
import CredentialModal from './CredentialModal'
import TerminalModal from '@/components/terminal/TerminalModal'
import SwitchExpanderView from './SwitchExpanderView'
import RebootConfirmModal from './RebootConfirmModal'
import { rpisApi } from '@/api/endpoints'
import { useNotification, NOTIFICATION_MESSAGES } from '@/context/NotificationContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import dayjs from 'dayjs'
import '@/styles/animations.css'
import './RPisPage.css'

const RPisPage = () => {
  const [data, setData] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const { notify } = useNotification()

  /* view mode */
  const [viewMode, setViewMode] = useState('table') // 'table' | 'switch'

  /* filters */
  const [search, setSearch] = useState('')
  const [filterSsh, setFilterSsh] = useState('')
  const [filterCreds, setFilterCreds] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  const [sortBy, setSortBy] = useState('ip')

  /* reconnect */
  const [reconnectingIp, setReconnectingIp] = useState(null)

  /* reboot */
  const [rebootingIp, setRebootingIp] = useState(null)

  /* reboot confirm modal */
  const [rebootTarget, setRebootTarget] = useState(null) // row | null

  /* modals */
  const [detailTarget, setDetailTarget] = useState(null)
  const [credTarget, setCredTarget] = useState(null)

  /* terminal */
  const [terminalTarget, setTerminalTarget] = useState(null)

  /* ✅ active terminal sessions (attached>0) */
  const [activeRpiIps, setActiveRpiIps] = useState(() => new Set())

  const fetchActiveRpiSessions = useCallback(async () => {
    try {
      const res = await rpisApi.terminalSessionsAll()
      const sessions = res.data?.data || []
      const active = new Set(
        sessions
          .filter((s) => s.device_type === 'rpi' && s.status === 'ready' && (s.attached || 0) > 0)
          .map((s) => s.target) // target = ip_mgmt
      )
      setActiveRpiIps(active)
    } catch {
      setActiveRpiIps(new Set())
    }
  }, [])

  const fetchRpis = useCallback(async () => {
    setLoading(true)
    try {
      const baseParams = {}
      if (search.trim()) baseParams.search = search.trim()
      if (filterSsh !== '') baseParams.ssh_success = filterSsh === 'true'
      if (filterCreds !== '') baseParams.has_custom_creds = filterCreds === 'true'

      if (viewMode === 'switch') {
        const PAGE_SIZE_SWITCH = 100
        let all = []
        let p = 1
        let total = 0
        let totalPages = 1

        while (true) {
          const res = await rpisApi.list({ ...baseParams, page: p, page_size: PAGE_SIZE_SWITCH })
          const chunk = res.data.data || []
          all = all.concat(chunk)

          total = res.data.total || all.length
          totalPages = res.data.total_pages || 1

          if (p >= totalPages) break
          p += 1
        }

        setData(all)
        setTotal(total)
        setTotalPages(1)
        setPage(1)
      } else {
        const res = await rpisApi.list({ ...baseParams, page, page_size: PAGE_SIZE })
        setData(res.data.data || [])
        setTotal(res.data.total || 0)
        setTotalPages(res.data.total_pages || 1)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      // ✅ refresh active session markers
      fetchActiveRpiSessions()
    }
  }, [page, search, filterSsh, filterCreds, viewMode, fetchActiveRpiSessions])

  useEffect(() => {
    fetchRpis()
  }, [fetchRpis])

  // optional: refresh active markers every 20s
  useEffect(() => {
    const t = setInterval(() => fetchActiveRpiSessions(), 20000)
    return () => clearInterval(t)
  }, [fetchActiveRpiSessions])

  const handleSearch = (val) => { setSearch(val); setPage(1) }
  const handleSshFilter = (val) => { setFilterSsh(val); setPage(1) }
  const handleCredsFilter = (val) => { setFilterCreds(val); setPage(1) }

  const handleDeleteCreds = async (ip) => {
    try {
      await rpisApi.deleteCredentials(ip)
      notify('success', NOTIFICATION_MESSAGES.SUCCESS.DELETED)
      fetchRpis()
    } catch (e) {
      notify('error', getFriendlyMessage('error', e.message || 'Delete credentials failed'))
      console.error(e)
    }
  }

  const handleReconnect = async (row) => {
    const ip = row?.ip_mgmt
    if (!ip) return

    setReconnectingIp(ip)
    notify('info', `Reconnecting RPi ${ip}...`)

    try {
      const res = await rpisApi.reconnect(ip)
      const ok = res?.data?.success !== false
      const msg = res?.data?.message || (ok ? 'Reconnect succeeded' : 'Reconnect failed')
      notify(ok ? 'success' : 'error', msg)
      fetchRpis()
    } catch (e) {
      notify('error', getFriendlyMessage('error', e.response?.data?.detail || e.message || 'Reconnect failed'))
      console.error(e)
    } finally {
      setReconnectingIp(null)
    }
  }

  /* ── Step 1 : open confirm modal (with normalized port) ── */
  const handleRebootRequest = (row) => {
    const rawPort = row?.switch_port
    const normalizedPort = rawPort
      ? String(rawPort).trim().replace(/^g/i, '').replace(/[^0-9]/g, '')
      : null

    if (!normalizedPort) {
      notify('error', `Cannot reboot: missing or invalid switch port for RPi ${row?.ip_mgmt || ''}`)
      return
    }

    setRebootTarget({ ...row, _normalizedPort: normalizedPort })
  }

  /* ── Step 2 : user confirmed → execute reboot ── */
  const handleRebootConfirm = async () => {
    const row = rebootTarget
    setRebootTarget(null)

    const ip = row?.ip_mgmt
    const port = row?._normalizedPort
    if (!ip || !port) return

    setRebootingIp(ip)
    notify('info', `Rebooting RPi ${ip} via PoE cycle (port ${port})...`)

    try {
      const res = await rpisApi.reboot(ip, { port })
      const ok = res?.data?.success !== false
      const msg = res?.data?.message || (ok ? 'Reboot succeeded' : 'Reboot failed')
      notify(ok ? 'success' : 'error', msg)
      fetchRpis()
    } catch (e) {
      notify('error', getFriendlyMessage('error', e.response?.data?.detail || e.message || 'Reboot failed'))
      console.error(e)
    } finally {
      setRebootingIp(null)
    }
  }

  const handleRebootCancel = () => setRebootTarget(null)

  const displayData = useMemo(() => {
    const arr = [...data]
    const isActive = (row) => activeRpiIps.has(row.ip_mgmt)

    arr.sort((a, b) => {
      // ✅ active sessions first
      const ar = isActive(a) ? 0 : 1
      const br = isActive(b) ? 0 : 1
      if (ar !== br) return ar - br

      // then normal sort
      if (sortBy === 'ip') {
        return (a.ip_mgmt || '').localeCompare(b.ip_mgmt || '')
      } else if (sortBy === 'last_seen') {
        return new Date(b.last_seen || 0) - new Date(a.last_seen || 0)
      } else if (sortBy === 'ssh_failed_first') {
        const rank = (v) => (v === false ? 0 : v === true ? 1 : 2)
        return rank(a.last_ssh_success) - rank(b.last_ssh_success)
      }
      return 0
    })

    return arr
  }, [data, sortBy, activeRpiIps])

  const columns = [
    {
      key: 'ip_mgmt',
      title: 'IP Address',
      width: 140,
      render: (val, row) => {
        const busy = reconnectingIp === row.ip_mgmt || rebootingIp === row.ip_mgmt
        const active = activeRpiIps.has(row.ip_mgmt)

        return (
          <button
            type="button"
            className={`rpi-table__ip rpi-table__ip--clickable ${active ? 'rpi-table__ip--active' : ''}`}
            onClick={() => setTerminalTarget(row)}
            disabled={busy}
            title={active ? 'Terminal active (attached)' : 'Open terminal'}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: busy ? 'not-allowed' : 'pointer',
              textDecoration: 'underline',
            }}
          >
            {val}
          </button>
        )
      },
    },
    {
      key: 'mac',
      title: 'MAC Address',
      render: (val) =>
        val ? <span className="rpi-table__mono">{val}</span> : <span className="rpi-table__null">—</span>,
    },
    {
      key: 'label',
      title: 'Label',
      render: (val) =>
        val ? <span className="rpi-table__label">{val}</span> : <span className="rpi-table__null">—</span>,
    },
    {
      key: 'switch_ip',
      title: 'Switch',
      render: (val, row) =>
        val ? (
          <div className="rpi-table__switch">
            <span className="rpi-table__mono">{val}</span>
            {row.switch_port && <span className="rpi-table__port">:{row.switch_port}</span>}
          </div>
        ) : (
          <span className="rpi-table__null">—</span>
        ),
    },
    {
      key: 'hgw_ip',
      title: 'Home Gateway',
      render: (val) =>
        val ? <span className="rpi-table__mono rpi-table__mono--cyan">{val}</span> : <span className="rpi-table__null">—</span>,
    },
    {
      key: 'last_seen',
      title: 'Last Seen',
      render: (val) =>
        val ? <span className="rpi-table__time">{dayjs(val).format('MMM D, HH:mm')}</span> : <span className="rpi-table__null">—</span>,
    },
    {
      key: 'last_ssh_success',
      title: 'SSH',
      width: 90,
      align: 'center',
      render: (val) =>
        val === true ? (
          <div className="rpi-table__ssh rpi-table__ssh--ok">
            <CheckCircle size={14} />
            <span>OK</span>
          </div>
        ) : val === false ? (
          <div className="rpi-table__ssh rpi-table__ssh--fail">
            <XCircle size={14} />
            <span>Failed</span>
          </div>
        ) : (
          <span className="rpi-table__null">—</span>
        ),
    },
    {
      key: 'has_custom_credentials',
      title: 'Custom Creds',
      width: 110,
      align: 'center',
      render: (val) => (val ? <StatusBadge status={'active'} /> : <StatusBadge status={'disabled'} />),
    },
    {
      key: 'actions',
      title: '',
      width: 165,
      align: 'right',
      render: (_, row) => {
        const reconnecting = reconnectingIp === row.ip_mgmt
        const rebooting = rebootingIp === row.ip_mgmt
        const busy = reconnecting || rebooting

        return (
          <div className="rpi-table__actions">
            <button
              className="rpi-table__action-btn rpi-table__action-btn--view"
              title="View details"
              onClick={() => setDetailTarget(row)}
              disabled={busy}
            >
              <Eye size={15} />
            </button>

            <button
              className="rpi-table__action-btn rpi-table__action-btn--cred"
              title="Manage credentials"
              onClick={() => setCredTarget(row)}
              disabled={busy}
            >
              <KeyRound size={15} />
            </button>

            <button
              className="rpi-table__action-btn rpi-table__action-btn--reconnect"
              title={reconnecting ? 'Reconnecting...' : 'Reconnect'}
              onClick={() => handleReconnect(row)}
              disabled={busy}
            >
              {reconnecting ? <RefreshCw size={15} className="spin" /> : <Link2 size={15} />}
            </button>

            <button
              className="rpi-table__action-btn rpi-table__action-btn--reboot"
              title={rebooting ? 'Rebooting...' : 'Reboot via PoE cycle'}
              onClick={() => handleRebootRequest(row)}
              disabled={busy}
            >
              {rebooting ? <RefreshCw size={15} className="spin" /> : <PowerOff size={15} />}
            </button>

            {row.has_custom_credentials && (
              <button
                className="rpi-table__action-btn rpi-table__action-btn--delete"
                title="Remove custom credentials"
                onClick={() => handleDeleteCreds(row.ip_mgmt)}
                disabled={busy}
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        )
      },
    },
  ]

  const sshOk = data.filter((r) => r.last_ssh_success === true).length
  const sshFail = data.filter((r) => r.last_ssh_success === false).length
  const customCreds = data.filter((r) => r.has_custom_credentials).length

  return (
    <div className="rpis-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Raspberry Pi Devices</h2>
          <p className="page-subtitle">
            {total} device{total !== 1 ? 's' : ''} registered
          </p>
        </div>

        <div className="rpis-page__header-actions">
          <div className="rpis-page__view-toggle">
            <button
              className={`rpis-page__view-btn ${viewMode === 'table' ? 'rpis-page__view-btn--active' : ''}`}
              onClick={() => setViewMode('table')}
              title="Table view"
            >
              <Table2 size={16} />
            </button>
            <button
              className={`rpis-page__view-btn ${viewMode === 'switch' ? 'rpis-page__view-btn--active' : ''}`}
              onClick={() => setViewMode('switch')}
              title="Group by switch"
            >
              <LayoutList size={16} />
            </button>
          </div>

          <Button variant="secondary" icon={RefreshCw} size="md" onClick={fetchRpis}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="rpis-page__summary">
        <div className="rpis-page__summary-item rpis-page__summary-item--total">
          <Cpu size={16} />
          <span className="rpis-page__summary-val">{total}</span>
          <span className="rpis-page__summary-label">Total</span>
        </div>
        <div className="rpis-page__summary-sep" />
        <div className="rpis-page__summary-item rpis-page__summary-item--ok">
          <CheckCircle size={16} />
          <span className="rpis-page__summary-val">{sshOk}</span>
          <span className="rpis-page__summary-label">SSH OK</span>
        </div>
        <div className="rpis-page__summary-sep" />
        <div className="rpis-page__summary-item rpis-page__summary-item--fail">
          <XCircle size={16} />
          <span className="rpis-page__summary-val">{sshFail}</span>
          <span className="rpis-page__summary-label">SSH Failed</span>
        </div>
        <div className="rpis-page__summary-sep" />
        <div className="rpis-page__summary-item rpis-page__summary-item--cred">
          <KeyRound size={16} />
          <span className="rpis-page__summary-val">{customCreds}</span>
          <span className="rpis-page__summary-label">Custom Creds</span>
        </div>
      </div>

      <Card padding={false}>
        <div className="rpis-page__filters">
          <SearchBar value={search} onChange={handleSearch} placeholder="Search by IP, MAC, label..." width={300} />
          <div className="rpis-page__filter-row">
            <div className="rpis-page__filter-group">
              <label className="rpis-page__filter-label">SSH Status</label>
              <select className="rpis-page__select" value={filterSsh} onChange={(e) => handleSshFilter(e.target.value)}>
                <option value="">All</option>
                <option value="true">Success</option>
                <option value="false">Failed</option>
              </select>
            </div>

            <div className="rpis-page__filter-group">
              <label className="rpis-page__filter-label">Credentials</label>
              <select className="rpis-page__select" value={filterCreds} onChange={(e) => handleCredsFilter(e.target.value)}>
                <option value="">All</option>
                <option value="true">Custom</option>
                <option value="false">Default</option>
              </select>
            </div>

            {viewMode === 'table' && (
              <div className="rpis-page__filter-group">
                <label className="rpis-page__filter-label">Sort</label>
                <select className="rpis-page__select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                  <option value="ip">IP (A→Z)</option>
                  <option value="last_seen">Last seen (newest)</option>
                  <option value="ssh_failed_first">SSH failed first</option>
                </select>
              </div>
            )}
          </div>
        </div>

        {loading ? (
          <Spinner centered text="Loading RPis..." />
        ) : viewMode === 'table' ? (
          <>
            <Table columns={columns} data={displayData} rowKey="id" emptyText="No RPi devices found" />
            {total > 0 && (
              <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onChange={setPage} />
            )}
          </>
        ) : (
          <SwitchExpanderView
            data={displayData}
            reconnectingIp={reconnectingIp}
            rebootingIp={rebootingIp}
            onDetail={setDetailTarget}
            onCred={setCredTarget}
            onReconnect={handleReconnect}
            onReboot={handleRebootRequest}
            onDeleteCreds={handleDeleteCreds}
            onTerminal={setTerminalTarget}
          />
        )}
      </Card>

      <RpiDetailModal open={!!detailTarget} onClose={() => setDetailTarget(null)} rpiData={detailTarget} />

      <CredentialModal
        open={!!credTarget}
        onClose={() => setCredTarget(null)}
        rpiData={credTarget}
        onSuccess={() => {
          setCredTarget(null)
          fetchRpis()
        }}
      />

      <TerminalModal
        open={!!terminalTarget}
        onClose={() => setTerminalTarget(null)}
        title={`Terminal — RPi ${terminalTarget?.ip_mgmt || ''}`}
        deviceType="rpi"
        targetLabel={terminalTarget?.ip_mgmt || ''}
        targetKey={terminalTarget?.ip_mgmt || ''}
        apiOpen={() => rpisApi.terminalOpen(terminalTarget.ip_mgmt)}
        apiList={() => rpisApi.terminalList(terminalTarget.ip_mgmt)}
        apiClose={(sid) => rpisApi.terminalClose(sid)}
        wsPathForSession={(sid) => `/api/v1/rpis/terminal/${sid}/ws`}
        autoStart={true}
      />

      <RebootConfirmModal
        open={!!rebootTarget}
        ip={rebootTarget?.ip_mgmt || ''}
        onConfirm={handleRebootConfirm}
        onCancel={handleRebootCancel}
      />
    </div>
  )
}

export default RPisPage