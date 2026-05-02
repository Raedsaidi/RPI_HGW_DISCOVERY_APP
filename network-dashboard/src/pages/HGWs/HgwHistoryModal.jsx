import React, { useEffect, useState } from 'react'
import { History, ChevronLeft, ChevronRight } from 'lucide-react'
import Modal from '@/components/common/Modal'
import Spinner from '@/components/common/Spinner'
import { hgwsApi } from '@/api/endpoints'
import dayjs from 'dayjs'
import './HgwHistoryModal.css'

const formatUptime = (s) => {
  if (!s) return '—'
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  return `${d}d ${h}h`
}

const formatMem = (kb) => (kb ? `${Math.round(kb / 1024)} MB` : '—')

const HgwHistoryModal = ({ open, onClose, hgwData }) => {
  const [facts, setFacts] = useState([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const PAGE_SIZE = 8

  useEffect(() => {
    if (!open || !hgwData) return
    setPage(1)
  }, [open, hgwData])

  useEffect(() => {
    if (!open || !hgwData) return
    setLoading(true)
    hgwsApi
      .getHistory(hgwData.ip, { page, page_size: PAGE_SIZE })
      .then((r) => {
        setFacts(r.data?.data || [])
        setTotal(r.data?.total || 0)
        setTotalPages(r.data?.total_pages || 1)
      })
      .catch(() => setFacts([]))
      .finally(() => setLoading(false))
  }, [open, hgwData, page])

  if (!hgwData) return null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`History — ${hgwData.ip}`}
      width={600}
    >
      <div className="hgw-history__header">
        <History size={14} />
        <span>
          {total} fact{total !== 1 ? 's' : ''} recorded
        </span>
      </div>

      {loading ? (
        <Spinner centered text="Loading history..." />
      ) : facts.length === 0 ? (
        <div className="hgw-history__empty">
          No history available for this gateway.
        </div>
      ) : (
        <>
          <div className="hgw-history__list">
            {facts.map((fact) => (
              <div key={fact.id} className="hgw-history__item">
                {/* Item header */}
                <div className="hgw-history__item-header">
                  <div className="hgw-history__item-left">
                    <span className="hgw-history__run-id">
                      Run #{fact.run_id}
                    </span>
                    <span className="hgw-history__model">
                      {fact.model_name || '—'}
                    </span>
                  </div>
                  <span className="hgw-history__time">
                    {fact.last_seen
                      ? dayjs(fact.last_seen).format('MMM D, YYYY HH:mm')
                      : '—'}
                  </span>
                </div>

                {/* Item body */}
                <div className="hgw-history__item-body">
                  <div className="hgw-history__stat">
                    <span className="hgw-history__stat-label">SW Version</span>
                    <span className="hgw-history__stat-val mono">
                      {fact.software_version || '—'}
                    </span>
                  </div>
                  <div className="hgw-history__stat">
                    <span className="hgw-history__stat-label">External IP</span>
                    <span className="hgw-history__stat-val mono">
                      {fact.external_ip || '—'}
                    </span>
                  </div>
                  <div className="hgw-history__stat">
                    <span className="hgw-history__stat-label">Uptime</span>
                    <span className="hgw-history__stat-val">
                      {formatUptime(fact.uptime_seconds)}
                    </span>
                  </div>
                  <div className="hgw-history__stat">
                    <span className="hgw-history__stat-label">Mem Free</span>
                    <span className="hgw-history__stat-val">
                      {formatMem(fact.mem_free_kb)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="hgw-history__pagination">
              <button
                className="hgw-history__page-btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft size={15} />
              </button>
              <span className="hgw-history__page-info">
                {page} / {totalPages}
              </span>
              <button
                className="hgw-history__page-btn"
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

export default HgwHistoryModal