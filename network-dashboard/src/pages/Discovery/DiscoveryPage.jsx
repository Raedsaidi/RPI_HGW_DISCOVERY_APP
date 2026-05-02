import React, { useState, useEffect, useCallback } from 'react'
import {
  Radio,
  Play,
  RefreshCw,
  Trash2,
  AlertCircle,
  CheckCircle,
  XCircle,
  Clock,
  Eye,
} from 'lucide-react'
import Card from '@/components/common/Card'
import Button from '@/components/common/Button'
import Table from '@/components/common/Table'
import Pagination from '@/components/common/Pagination'
import { StatusBadge } from '@/components/common/Badge'
import Spinner from '@/components/common/Spinner'
import RunErrorsModal from './RunErrorsModal'
import DeleteConfirmModal from '../Switches/DeleteConfirmModal'
import { discoveryApi } from '@/api/endpoints'
import { useNotifications, NOTIFICATION_MESSAGES } from '@/context/NotificationContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import dayjs from 'dayjs'
import duration from 'dayjs/plugin/duration'
import './DiscoveryPage.css'

dayjs.extend(duration)

const safe = (v) => (v == null ? 0 : v)

const formatDuration = (start, end) => {
  if (!start || !end) return '—'
  const ms = dayjs(end).diff(dayjs(start))
  const d = dayjs.duration(ms)
  if (d.asSeconds() < 60) return `${Math.round(d.asSeconds())}s`
  return `${Math.floor(d.asMinutes())}m ${d.seconds()}s`
}

const DiscoveryPage = () => {
  const [runs, setRuns] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const { notify } = useNotifications()

  /* filters */
  const [filterStatus, setFilterStatus] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 20

  /* modals */
  const [errorsTarget, setErrorsTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  /* ── fetch ── */
  const fetchRuns = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (filterStatus) params.status = filterStatus

      const [runsRes, statusRes] = await Promise.allSettled([
        discoveryApi.listRuns(params),
        discoveryApi.getStatus(),
      ])

      if (runsRes.status === 'fulfilled') {
        setRuns(runsRes.value.data.data || [])
        setTotal(runsRes.value.data.total || 0)
        setTotalPages(runsRes.value.data.total_pages || 1)
      }

      if (statusRes.status === 'fulfilled') {
        setIsRunning(statusRes.value.data.is_running || false)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [page, filterStatus])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  /* auto-refresh when running */
  useEffect(() => {
    if (!isRunning) return
    const interval = setInterval(fetchRuns, 5000)
    return () => clearInterval(interval)
  }, [isRunning, fetchRuns])

  const handleFilterStatus = (val) => {
    setFilterStatus(val)
    setPage(1)
  }

  /* ── trigger ── */
  const handleTrigger = async () => {
    setTriggering(true)
    try {
      await discoveryApi.trigger()
      setIsRunning(true)
      notify('success', NOTIFICATION_MESSAGES.SUCCESS.DISCOVERY_STARTED)
      setTimeout(fetchRuns, 1000)
    } catch (e) {
      const friendlyMessage = getFriendlyMessage('error', e.message || 'Discovery failed')
      notify('error', friendlyMessage)
      console.error(e)
    } finally {
      setTriggering(false)
    }
  }

  /* ── delete ── */
  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleteLoading(true)
    try {
      await discoveryApi.deleteRun(deleteTarget.id)
      setDeleteTarget(null)
      notify('success', NOTIFICATION_MESSAGES.SUCCESS.DELETED)
      fetchRuns()
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
      key: 'id',
      title: 'Run ID',
      width: 80,
      render: (val) => (
        <span className="disc-table__id">#{val}</span>
      ),
    },
    {
      key: 'status',
      title: 'Status',
      width: 110,
      render: (val) => <StatusBadge status={val} />,
    },
    {
      key: 'triggered_by',
      title: 'Triggered By',
      render: (val) => (
        <span className="disc-table__by">{val || 'system'}</span>
      ),
    },
    {
      key: 'started_at',
      title: 'Started',
      render: (val) =>
        val ? (
          <span className="disc-table__time">
            {dayjs(val).format('MMM D, YYYY HH:mm:ss')}
          </span>
        ) : (
          <span className="disc-table__null">—</span>
        ),
    },
    {
      key: 'duration',
      title: 'Duration',
      width: 90,
      render: (_, row) => (
        <span className="disc-table__duration">
          {formatDuration(row.started_at, row.finished_at)}
        </span>
      ),
    },
    {
      key: 'switches',
      title: 'Switches',
      width: 100,
      align: 'center',
      render: (_, row) => (
        <div className="disc-table__device-stat">
          <span className="disc-table__ok">
            <CheckCircle size={12} />
            {safe(row.switches_ok)}
          </span>
          <span className="disc-table__sep">/</span>
          <span className="disc-table__err">
            <XCircle size={12} />
            {safe(row.switches_err)}
          </span>
        </div>
      ),
    },
    {
      key: 'rpis',
      title: 'RPis',
      width: 100,
      align: 'center',
      render: (_, row) => (
        <div className="disc-table__device-stat">
          <span className="disc-table__ok">
            <CheckCircle size={12} />
            {safe(row.rpis_ok)}
          </span>
          <span className="disc-table__sep">/</span>
          <span className="disc-table__err">
            <XCircle size={12} />
            {safe(row.rpis_err)}
          </span>
        </div>
      ),
    },
    {
      key: 'hgws',
      title: 'HGWs',
      width: 100,
      align: 'center',
      render: (_, row) => (
        <div className="disc-table__device-stat">
          <span className="disc-table__ok">
            <CheckCircle size={12} />
            {safe(row.hgws_ok)}
          </span>
          <span className="disc-table__sep">/</span>
          <span className="disc-table__err">
            <XCircle size={12} />
            {safe(row.hgws_err)}
          </span>
        </div>
      ),
    },
    {
      key: 'message',
      title: 'Message',
      render: (val) =>
        val ? (
          <span className="disc-table__msg">{val}</span>
        ) : (
          <span className="disc-table__null">—</span>
        ),
    },
    {
      key: 'actions',
      title: '',
      width: 80,
      align: 'right',
      render: (_, row) => (
        <div className="disc-table__actions">
          <button
            className="disc-table__action-btn disc-table__action-btn--errors"
            title="View errors"
            onClick={() => setErrorsTarget(row)}
          >
            <Eye size={15} />
          </button>
          <button
            className="disc-table__action-btn disc-table__action-btn--delete"
            title="Delete run"
            onClick={() => setDeleteTarget(row)}
          >
            <Trash2 size={15} />
          </button>
        </div>
      ),
    },
  ]

  /* ── totals ── */
  const totalOk = runs.reduce(
    (acc, r) => acc + safe(r.switches_ok) + safe(r.rpis_ok) + safe(r.hgws_ok),
    0
  )
  const totalErr = runs.reduce(
    (acc, r) =>
      acc + safe(r.switches_err) + safe(r.rpis_err) + safe(r.hgws_err),
    0
  )

  return (
    <div className="discovery-page">
      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Discovery Runs</h2>
          <p className="page-subtitle">
            {total} run{total !== 1 ? 's' : ''} recorded
          </p>
        </div>
        <div className="discovery-page__header-actions">
          <Button
            variant="secondary"
            icon={RefreshCw}
            size="md"
            onClick={fetchRuns}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            icon={Play}
            size="md"
            loading={triggering}
            disabled={isRunning}
            onClick={handleTrigger}
          >
            {isRunning ? 'Running...' : 'Run Discovery'}
          </Button>
        </div>
      </div>

      {/* ── Running banner ── */}
      {isRunning && (
        <div className="discovery-page__running-banner">
          <div className="discovery-page__running-dot" />
          <span>
            A discovery run is currently in progress. Results will
            update automatically.
          </span>
          <Spinner size="sm" />
        </div>
      )}

      {/* ── Summary strip ── */}
      <div className="discovery-page__summary">
        <div className="discovery-page__summary-item discovery-page__summary-item--total">
          <Radio size={16} />
          <span className="discovery-page__summary-val">{total}</span>
          <span className="discovery-page__summary-label">Total Runs</span>
        </div>
        <div className="discovery-page__summary-sep" />
        <div className="discovery-page__summary-item discovery-page__summary-item--ok">
          <CheckCircle size={16} />
          <span className="discovery-page__summary-val">{totalOk}</span>
          <span className="discovery-page__summary-label">
            Devices OK (page)
          </span>
        </div>
        <div className="discovery-page__summary-sep" />
        <div className="discovery-page__summary-item discovery-page__summary-item--err">
          <XCircle size={16} />
          <span className="discovery-page__summary-val">{totalErr}</span>
          <span className="discovery-page__summary-label">
            Devices Err (page)
          </span>
        </div>
        <div className="discovery-page__summary-sep" />
        <div className="discovery-page__summary-item discovery-page__summary-item--running">
          <Clock size={16} />
          <span className="discovery-page__summary-val">
            {isRunning ? 'Yes' : 'No'}
          </span>
          <span className="discovery-page__summary-label">Running Now</span>
        </div>
      </div>

      {/* ── Table card ── */}
      <Card padding={false}>
        {/* Filters */}
        <div className="discovery-page__filters">
          <div className="discovery-page__filter-group">
            <label className="discovery-page__filter-label">
              Status
            </label>
            <div className="discovery-page__status-btns">
              {['', 'running', 'done', 'partial', 'error'].map(
                (s) => (
                  <button
                    key={s}
                    className={`discovery-page__status-btn ${
                      filterStatus === s
                        ? 'discovery-page__status-btn--active'
                        : ''
                    }`}
                    onClick={() => handleFilterStatus(s)}
                  >
                    {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                )
              )}
            </div>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <Spinner centered text="Loading discovery runs..." />
        ) : (
          <>
            <Table
              columns={columns}
              data={runs}
              rowKey="id"
              emptyText="No discovery runs found"
            />
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
      <RunErrorsModal
        open={!!errorsTarget}
        onClose={() => setErrorsTarget(null)}
        run={errorsTarget}
      />

      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        loading={deleteLoading}
        title="Delete Discovery Run"
        description={
          deleteTarget
            ? `Are you sure you want to delete run #${deleteTarget.id}? All associated data will be lost.`
            : ''
        }
      />
    </div>
  )
}

export default DiscoveryPage