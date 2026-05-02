import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  Network,
  Cpu,
  Wifi,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
} from 'lucide-react'
import Modal from '@/components/common/Modal'
import Spinner from '@/components/common/Spinner'
import SearchBar from '@/components/common/SearchBar'
import { discoveryApi } from '@/api/endpoints'
import dayjs from 'dayjs'
import './RunErrorsModal.css'

const DEVICE_ICONS = {
  switch: <Network size={14} color="var(--primary-6)" />,
  piserver: <Cpu size={14} color="var(--purple-main)" />,
  rpi: <Cpu size={14} color="var(--purple-main)" />,
  hgw: <Wifi size={14} color="var(--cyan-main)" />,
}

const STAGE_COLORS = {
  ssh: { bg: 'var(--purple-light)', color: 'var(--purple-main)' },
  telnet: { bg: 'var(--primary-1)', color: 'var(--primary-7)' },
  collect: { bg: 'var(--warning-light)', color: 'var(--warning-dark)' },
}

const RunErrorsModal = ({ open, onClose, run }) => {
  const [errors, setErrors] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterStage, setFilterStage] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10

  useEffect(() => {
    if (!open || !run) return
    setSearch('')
    setFilterType('')
    setFilterStage('')
    setPage(1)
  }, [open, run])

  useEffect(() => {
    if (!open || !run) return
    setLoading(true)
    const params = {}
    if (filterType) params.device_type = filterType
    if (filterStage) params.stage = filterStage
    if (search.trim()) params.device_ip = search.trim()

    discoveryApi
      .getRunErrors(run.id, params)
      .then((r) => {
        const errorsData = r.data || []
        const errors = Array.isArray(errorsData) ? errorsData : (errorsData.data || [])
        setErrors(errors)
      })
      .catch(() => setErrors([]))
      .finally(() => setLoading(false))
  }, [open, run, filterType, filterStage, search])

  if (!run) return null

  /* client-side pagination */
  const paginated = errors.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.max(Math.ceil(errors.length / PAGE_SIZE), 1)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Errors — Run #${run.id}`}
      width={640}
    >
      {/* ── Run summary ── */}
      <div className="rerr-modal__run-summary">
        <div className="rerr-modal__run-info">
          <span className="rerr-modal__run-time">
            {dayjs(run.started_at).format('MMM D, YYYY HH:mm')}
          </span>
          <span className="rerr-modal__run-by">
            by {run.triggered_by || 'system'}
          </span>
        </div>
        <div className="rerr-modal__run-count">
          <AlertCircle size={14} />
          <span>{errors.length} error{errors.length !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className="rerr-modal__filters">
        <SearchBar
          value={search}
          onChange={(v) => { setSearch(v); setPage(1) }}
          placeholder="Filter by IP..."
          width={200}
        />
        <select
          className="rerr-modal__select"
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(1) }}
        >
          <option value="">All types</option>
          <option value="switch">Switch</option>
          <option value="rpi">RPi</option>
          <option value="hgw">HGW</option>
          <option value="piserver">Pi Server</option>
        </select>
        <select
          className="rerr-modal__select"
          value={filterStage}
          onChange={(e) => { setFilterStage(e.target.value); setPage(1) }}
        >
          <option value="">All stages</option>
          <option value="ssh">SSH</option>
          <option value="telnet">Telnet</option>
          <option value="collect">Collect</option>
        </select>
      </div>

      {/* ── Errors list ── */}
      {loading ? (
        <Spinner centered text="Loading errors..." />
      ) : errors.length === 0 ? (
        <div className="rerr-modal__empty">
          <CheckCircle size={28} color="var(--success-main)" />
          <p>No errors found for this run.</p>
        </div>
      ) : (
        <>
          <div className="rerr-modal__list">
            {paginated.map((err) => {
              const stageStyle =
                STAGE_COLORS[err.stage] || STAGE_COLORS.collect
              return (
                <div key={err.id} className="rerr-modal__item">
                  <div className="rerr-modal__item-header">
                    <div className="rerr-modal__item-left">
                      {DEVICE_ICONS[err.device_type] || (
                        <AlertCircle size={14} />
                      )}
                      <span className="rerr-modal__device-ip mono">
                        {err.device_ip}
                      </span>
                      <span className="rerr-modal__device-type">
                        {err.device_type}
                      </span>
                    </div>
                    <div className="rerr-modal__item-right">
                      <span
                        className="rerr-modal__stage"
                        style={{
                          background: stageStyle.bg,
                          color: stageStyle.color,
                        }}
                      >
                        {err.stage}
                      </span>
                      <span className="rerr-modal__time">
                        {dayjs(err.created_at).format('HH:mm:ss')}
                      </span>
                    </div>
                  </div>
                  <div className="rerr-modal__item-body">
                    <code className="rerr-modal__error-msg">
                      {err.error}
                    </code>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="rerr-modal__pagination">
              <button
                className="rerr-modal__page-btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft size={15} />
              </button>
              <span className="rerr-modal__page-info">
                {page} / {totalPages}
                <span className="rerr-modal__page-total">
                  ({errors.length} total)
                </span>
              </span>
              <button
                className="rerr-modal__page-btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight size={15} />
              </button>
            </div>
          )}
        </>
      )}
    </Modal>
  )
}

export default RunErrorsModal