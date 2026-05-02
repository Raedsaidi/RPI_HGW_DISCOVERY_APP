import React, { useState, useEffect, useCallback } from 'react'
import { Plus, Pencil, Trash2, Eye, RefreshCw, Link2 } from 'lucide-react'
import Card from '@/components/common/Card'
import Button from '@/components/common/Button'
import Table from '@/components/common/Table'
import SearchBar from '@/components/common/SearchBar'
import Pagination from '@/components/common/Pagination'
import { StatusBadge } from '@/components/common/Badge'
import Spinner from '@/components/common/Spinner'
import SwitchModal from './SwitchModal'
import SwitchDetailModal from './SwitchDetailModal'
import DeleteConfirmModal from './DeleteConfirmModal'
import TerminalModal from '@/components/terminal/TerminalModal'
import { switchesApi } from '@/api/endpoints'
import { useNotification, NOTIFICATION_MESSAGES } from '@/context/NotificationContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import dayjs from 'dayjs'
import '@/styles/animations.css'
import './SwitchesPage.css'

const SwitchesPage = () => {
  const [data, setData] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const { notify } = useNotification()

  /* filters */
  const [search, setSearch] = useState('')
  const [filterEnabled, setFilterEnabled] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  /* reconnect */
  const [reconnectingId, setReconnectingId] = useState(null)

  /* modals */
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [detailTarget, setDetailTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  /* terminal */
  const [terminalTarget, setTerminalTarget] = useState(null)

  /* ── fetch ── */
  const fetchSwitches = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (search.trim()) params.search = search.trim()
      if (filterEnabled !== '') params.enabled = filterEnabled === 'true'

      const res = await switchesApi.list(params)
      setData(res.data.data || [])
      setTotal(res.data.total || 0)
      setTotalPages(res.data.total_pages || 1)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [page, search, filterEnabled])

  useEffect(() => {
    fetchSwitches()
  }, [fetchSwitches])

  const handleSearch = (val) => { setSearch(val); setPage(1) }
  const handleFilter = (val) => { setFilterEnabled(val); setPage(1) }

  /* ── reconnect ── */
  const handleReconnect = async (row) => {
    if (!row?.id) return
    const id = row.id

    setReconnectingId(id)
    notify('info', `Reconnecting switch ${row.ip}...`)

    try {
      const res = await switchesApi.reconnect(id)
      const ok = res?.data?.success !== false
      const msg = res?.data?.message || (ok ? 'Reconnect succeeded' : 'Reconnect failed')
      notify(ok ? 'success' : 'error', msg)
      fetchSwitches()
    } catch (e) {
      const friendlyMessage = getFriendlyMessage(
        'error',
        e.response?.data?.detail || e.message || 'Reconnect failed'
      )
      notify('error', friendlyMessage)
      console.error(e)
    } finally {
      setReconnectingId(null)
    }
  }

  /* ── delete ── */
  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleteLoading(true)
    try {
      await switchesApi.delete(deleteTarget.id)
      setDeleteTarget(null)
      notify('success', NOTIFICATION_MESSAGES.SUCCESS.DELETED)
      fetchSwitches()
    } catch (e) {
      const friendlyMessage = getFriendlyMessage('error', e.message || 'Delete failed')
      notify('error', friendlyMessage)
      console.error(e)
    } finally {
      setDeleteLoading(false)
    }
  }

  /* ── columns ── */
  const columns = [
    {
      key: 'ip',
      title: 'IP Address',
      width: 140,
      render: (val, row) => {
        const busy = reconnectingId === row.id
        return (
          <button
            type="button"
            className="sw-table__ip sw-table__ip--clickable"
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
      key: 'name',
      title: 'Name',
      render: (val) => val || <span className="sw-table__null">—</span>,
    },
    {
      key: 'model',
      title: 'Model',
      render: (val) => val || <span className="sw-table__null">—</span>,
    },
    {
      key: 'mac_address',
      title: 'MAC Address',
      render: (val) =>
        val ? <span className="sw-table__mono">{val}</span> : <span className="sw-table__null">—</span>,
    },
    {
      key: 'firmware_version',
      title: 'Firmware',
      render: (val) => val || <span className="sw-table__null">—</span>,
    },
    {
      key: 'last_seen',
      title: 'Last Seen',
      render: (val) =>
        val ? <span className="sw-table__time">{dayjs(val).format('MMM D, HH:mm')}</span> : <span className="sw-table__null">—</span>,
    },
    {
      key: 'enabled',
      title: 'Status',
      width: 100,
      align: 'center',
      render: (val) => <StatusBadge status={val ? 'active' : 'disabled'} />,
    },
    {
      key: 'actions',
      title: '',
      width: 140,
      align: 'right',
      render: (_, row) => {
        const busy = reconnectingId === row.id
        return (
          <div className="sw-table__actions">
            <button
              className="sw-table__action-btn sw-table__action-btn--view"
              title="View details"
              onClick={() => setDetailTarget(row)}
              disabled={busy}
              type="button"
            >
              <Eye size={15} />
            </button>

            <button
              className="sw-table__action-btn sw-table__action-btn--edit"
              title="Edit switch"
              onClick={() => setEditTarget(row)}
              disabled={busy}
              type="button"
            >
              <Pencil size={15} />
            </button>

            <button
              className="sw-table__action-btn sw-table__action-btn--reconnect"
              title={busy ? 'Reconnecting...' : 'Reconnect'}
              onClick={() => handleReconnect(row)}
              disabled={busy}
              type="button"
            >
              {busy ? <RefreshCw size={15} className="spin" /> : <Link2 size={15} />}
            </button>

            <button
              className="sw-table__action-btn sw-table__action-btn--delete"
              title="Delete switch"
              onClick={() => setDeleteTarget(row)}
              disabled={busy}
              type="button"
            >
              <Trash2 size={15} />
            </button>
          </div>
        )
      },
    },
  ]

  return (
    <div className="switches-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Switches</h2>
          <p className="page-subtitle">
            {total} switch{total !== 1 ? 'es' : ''} registered
          </p>
        </div>
        <div className="switches-page__header-actions">
          <Button variant="secondary" icon={RefreshCw} size="md" onClick={fetchSwitches}>
            Refresh
          </Button>
          <Button variant="primary" icon={Plus} size="md" onClick={() => setCreateOpen(true)}>
            Add Switch
          </Button>
        </div>
      </div>

      <Card padding={false}>
        <div className="switches-page__filters">
          <SearchBar
            value={search}
            onChange={handleSearch}
            placeholder="Search by IP, name, MAC..."
            width={300}
          />
          <div className="switches-page__filter-group">
            <label className="switches-page__filter-label">Status</label>
            <select
              className="switches-page__select"
              value={filterEnabled}
              onChange={(e) => handleFilter(e.target.value)}
            >
              <option value="">All</option>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
          </div>
        </div>
      </Card>

      <Card padding={false}>
        {loading ? (
          <Spinner centered text="Loading switches..." />
        ) : (
          <>
            <Table columns={columns} data={data} rowKey="id" emptyText="No switches found" />
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

      <SwitchModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={() => {
          setCreateOpen(false)
          fetchSwitches()
        }}
        mode="create"
      />

      <SwitchModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        onSuccess={() => {
          setEditTarget(null)
          fetchSwitches()
        }}
        mode="edit"
        initial={editTarget}
      />

      <SwitchDetailModal
        open={!!detailTarget}
        onClose={() => setDetailTarget(null)}
        switchData={detailTarget}
      />

      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        loading={deleteLoading}
        title="Delete Switch"
        description={
          deleteTarget
            ? `Are you sure you want to delete switch ${deleteTarget.ip}? This action cannot be undone.`
            : ''
        }
      />

      {/* Terminal (autoStart => déjà connecté) */}
      <TerminalModal
        open={!!terminalTarget}
        onClose={() => setTerminalTarget(null)}
        title={`Terminal — Switch ${terminalTarget?.ip || ''}`}
        deviceType="switch"
        targetLabel={terminalTarget?.ip || ''}
        targetKey={terminalTarget?.id || ''}
        apiOpen={() => switchesApi.terminalOpen(terminalTarget.id)}
        apiList={() => switchesApi.terminalList(terminalTarget.id)}
        apiClose={(sid) => switchesApi.terminalClose(sid)}
        wsPathForSession={(sid) => `/api/v1/switches/terminal/${sid}/ws`}
        autoStart={true}
      />
    </div>
  )
}

export default SwitchesPage