import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { Wifi, RefreshCw, Eye, History, Router, Link2 } from 'lucide-react'
import Card from '@/components/common/Card'
import Button from '@/components/common/Button'
import Table from '@/components/common/Table'
import SearchBar from '@/components/common/SearchBar'
import Pagination from '@/components/common/Pagination'
import Spinner from '@/components/common/Spinner'
import HgwDetailModal from './HgwDetailModal'
import HgwHistoryModal from './HgwHistoryModal'
import TerminalModal from '@/components/terminal/TerminalModal'
import { hgwsApi } from '@/api/endpoints'
import { useNotification } from '@/context/NotificationContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import dayjs from 'dayjs'
import '@/styles/animations.css'
import './HGWsPage.css'

/* Fallback si le backend ne renvoie pas h.network */
const fallbackNetworkPrefix = (ip) => {
  if (!ip) return null
  const parts = ip.split('.')
  if (parts.length !== 4) return null
  return `${parts[0]}.${parts[1]}.${parts[2]}.x`
}

const HGWsPage = () => {
  const { notify } = useNotification()

  const [data, setData] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)

  /* filters */
  const [search, setSearch] = useState('')
  const [filterNetwork, setFilterNetwork] = useState('')
  const [filterManufacturer, setFilterManufacturer] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  /**
   * NEW:
   * Prefer stable identity for UI actions. If backend exposes instance_key, use it.
   * Otherwise fallback to ip|via_rpi_ip.
   */
  const getHgwRowKey = (row) =>
    row?.serial_number
      ? `serial:${row.serial_number}`
      : row?.instance_key
        ? `inst:${row.instance_key}`
        : row?.via_rpi_ip
          ? `${row.ip}|${row.via_rpi_ip}`
          : row?.ip

  /* reconnect */
  const [reconnectingKey, setReconnectingKey] = useState(null)

  /* modals */
  const [detailTarget, setDetailTarget] = useState(null)
  const [historyTarget, setHistoryTarget] = useState(null)

  /* terminal */
  const [terminalTarget, setTerminalTarget] = useState(null)

  /* ── fetch ── */
  const fetchHgws = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (search.trim()) params.search = search.trim()
      if (filterManufacturer) params.manufacturer = filterManufacturer
      if (filterNetwork) params.network = filterNetwork

      const res = await hgwsApi.list(params)
      setData(res.data.data || [])
      setTotal(res.data.total || 0)
      setTotalPages(res.data.total_pages || 1)
    } catch (e) {
      console.error(e)
      notify('error', getFriendlyMessage('error', e?.response?.data?.detail || 'Failed to load gateways'))
    } finally {
      setLoading(false)
    }
  }, [page, search, filterManufacturer, filterNetwork, notify])

  useEffect(() => {
    fetchHgws()
  }, [fetchHgws])

  const handleSearch = (val) => { setSearch(val); setPage(1) }
  const handleNetworkFilter = (val) => { setFilterNetwork(val); setPage(1) }
  const handleManufFilter = (val) => { setFilterManufacturer(val); setPage(1) }

  /* ── derive unique manufacturers & networks ── */
  const manufacturers = useMemo(
    () => [...new Set(data.map((h) => h.manufacturer).filter(Boolean))],
    [data]
  )

  const networks = useMemo(() => {
    const values = data.map((h) => h.network || fallbackNetworkPrefix(h.ip)).filter(Boolean)
    return [...new Set(values)].sort()
  }, [data])

  /* ── reconnect ── */
  const handleReconnect = async (row) => {
    if (!row?.ip) return

    const ip = row.ip
    const params = row.via_rpi_ip ? { via_rpi_ip: row.via_rpi_ip } : undefined
    const targetKey = getHgwRowKey(row)

    setReconnectingKey(targetKey)
    notify('info', `Reconnecting HGW ${ip}...`)

    try {
      const res = await hgwsApi.reconnect(ip, params)
      const ok = res?.data?.success !== false
      const msg = res?.data?.message || (ok ? 'Reconnect succeeded' : 'Reconnect failed')
      notify(ok ? 'success' : 'error', msg)
      fetchHgws()
    } catch (e) {
      console.error(e)
      notify('error', getFriendlyMessage('error', e?.response?.data?.detail || 'Reconnect failed'))
    } finally {
      setReconnectingKey(null)
    }
  }

  /* ── columns ── */
  const columns = [
    {
      key: 'ip',
      title: 'Gateway IP',
      width: 160,
      render: (val, row) => {
        const busy = reconnectingKey === getHgwRowKey(row)
        return (
          <button
            type="button"
            className="hgw-table__ip hgw-table__ip--clickable"
            onClick={() => setTerminalTarget(row)}
            disabled={busy}
            title="Open terminal"
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
      key: 'manufacturer',
      title: 'Manufacturer',
      render: (val) => val || <span className="hgw-table__null">—</span>,
    },
    {
      key: 'model_name',
      title: 'Model',
      render: (val) => val || <span className="hgw-table__null">—</span>,
    },
    {
      key: 'serial_number',
      title: 'Serial',
      render: (val) =>
        val ? <span className="hgw-table__mono">{val}</span> : <span className="hgw-table__null">—</span>,
    },

    // OPTIONAL BUT USEFUL: shows instance_key if backend returns it
    {
      key: 'instance_key',
      title: 'Instance',
      width: 160,
      render: (val) =>
        val ? <span className="hgw-table__mono">{val}</span> : <span className="hgw-table__null">—</span>,
    },

    {
      key: 'software_version',
      title: 'SW Version',
      render: (val) => val || <span className="hgw-table__null">—</span>,
    },
    {
      key: 'external_ip',
      title: 'External IP',
      render: (val) =>
        val ? <span className="hgw-table__mono hgw-table__mono--ext">{val}</span> : <span className="hgw-table__null">—</span>,
    },
    {
      key: 'via_rpi_ip',
      title: 'Via RPi',
      render: (val) =>
        val ? <span className="hgw-table__mono hgw-table__mono--rpi">{val}</span> : <span className="hgw-table__null">—</span>,
    },
    {
      key: 'last_seen',
      title: 'Last Seen',
      render: (val) =>
        val ? <span className="hgw-table__time">{dayjs(val).format('MMM D, HH:mm')}</span> : <span className="hgw-table__null">—</span>,
    },
    {
      key: 'actions',
      title: '',
      width: 120,
      align: 'right',
      render: (_, row) => {
        const busy = reconnectingKey === getHgwRowKey(row)
        return (
          <div className="hgw-table__actions">
            <button
              className="hgw-table__action-btn hgw-table__action-btn--view"
              title="View details"
              onClick={() => setDetailTarget(row)}
              disabled={busy}
              type="button"
            >
              <Eye size={15} />
            </button>

            <button
              className="hgw-table__action-btn hgw-table__action-btn--history"
              title="View history"
              onClick={() => setHistoryTarget(row)}
              disabled={busy}
              type="button"
            >
              <History size={15} />
            </button>

            <button
              className="hgw-table__action-btn hgw-table__action-btn--reconnect"
              title={busy ? 'Reconnecting...' : 'Reconnect'}
              onClick={() => handleReconnect(row)}
              disabled={busy}
              type="button"
            >
              {busy ? <RefreshCw size={15} className="spin" /> : <Link2 size={15} />}
            </button>
          </div>
        )
      },
    },
  ]

  return (
    <div className="hgws-page">
      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Home Gateways</h2>
          <p className="page-subtitle">
            {total} gateway{total !== 1 ? 's' : ''} discovered
          </p>
        </div>
        <Button variant="secondary" icon={RefreshCw} size="md" onClick={fetchHgws}>
          Refresh
        </Button>
      </div>

      {/* ── Summary strip ── */}
      <div className="hgws-page__summary">
        <div className="hgws-page__summary-item hgws-page__summary-item--total">
          <Wifi size={16} />
          <span className="hgws-page__summary-val">{total}</span>
          <span className="hgws-page__summary-label">Total</span>
        </div>

        {filterNetwork && (
          <>
            <div className="hgws-page__summary-sep" />
            <div
              className="hgws-page__summary-item hgws-page__summary-item--clickable hgws-page__summary-item--active"
              title="Clear network filter"
              onClick={() => handleNetworkFilter('')}
            >
              <Router size={13} />
              <span className="hgws-page__summary-val">{total}</span>
              <span className="hgws-page__summary-label">{filterNetwork}</span>
            </div>
          </>
        )}
      </div>

      {/* ── Table card ── */}
      <Card padding={false}>
        <div className="hgws-page__filters">
          <SearchBar
            value={search}
            onChange={handleSearch}
            placeholder="Search by IP, model, serial..."
            width={300}
          />

          <div className="hgws-page__filter-row">
            <div className="hgws-page__filter-group">
              <label className="hgws-page__filter-label">Network</label>
              <select
                className="hgws-page__select"
                value={filterNetwork}
                onChange={(e) => handleNetworkFilter(e.target.value)}
              >
                <option value="">All networks</option>
                {networks.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <div className="hgws-page__filter-group">
              <label className="hgws-page__filter-label">Manufacturer</label>
              <select
                className="hgws-page__select"
                value={filterManufacturer}
                onChange={(e) => handleManufFilter(e.target.value)}
              >
                <option value="">All</option>
                {manufacturers.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>

            {filterNetwork && (
              <button
                className="hgws-page__filter-clear"
                onClick={() => handleNetworkFilter('')}
                title="Clear network filter"
              >
                {filterNetwork} ✕
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <Spinner centered text="Loading gateways..." />
        ) : (
          <>
            <Table columns={columns} data={data} rowKey="id" emptyText="No gateways found" />
            {total > 0 && (
              <Pagination
                page={page}
                totalPages={totalPages}
                total={total}
                pageSize={PAGE_SIZE}
                onChange={setPage}
              />
            )}
          </>
        )}
      </Card>

      {/* ── Modals ── */}
      <HgwDetailModal
        open={!!detailTarget}
        onClose={() => setDetailTarget(null)}
        hgwData={detailTarget}
      />
      <HgwHistoryModal
        open={!!historyTarget}
        onClose={() => setHistoryTarget(null)}
        hgwData={historyTarget}
      />

      {/* ── Terminal (autoStart: session ouverte immédiatement) ── */}
      <TerminalModal
        open={!!terminalTarget}
        onClose={() => setTerminalTarget(null)}
        title={`Terminal — HGW ${terminalTarget?.ip || ''}`}
        deviceType="hgw"
        targetLabel={terminalTarget?.ip || ''}
        targetKey={terminalTarget ? getHgwRowKey(terminalTarget) : ''}
        apiOpen={() => hgwsApi.terminalOpen(
          terminalTarget.ip,
          terminalTarget?.via_rpi_ip ? { via_rpi_ip: terminalTarget.via_rpi_ip } : undefined
        )}
        apiList={() => hgwsApi.terminalList(terminalTarget.ip)}
        apiClose={(sid) => hgwsApi.terminalClose(sid)}
        wsPathForSession={(sid) => `/api/v1/hgws/terminal/${sid}/ws`}
        autoStart={true}
      />
    </div>
  )
}

export default HGWsPage