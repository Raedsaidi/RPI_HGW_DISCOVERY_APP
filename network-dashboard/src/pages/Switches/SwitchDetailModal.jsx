import React, { useEffect, useState } from 'react'
import { Network, Cpu, Clock } from 'lucide-react'
import Modal from '@/components/common/Modal'
import { StatusBadge } from '@/components/common/Badge'
import Spinner from '@/components/common/Spinner'
import { switchesApi } from '@/api/endpoints'
import dayjs from 'dayjs'
import './SwitchDetailModal.css'

const Row = ({ label, value, mono }) => (
  <div className="sw-detail__row">
    <span className="sw-detail__label">{label}</span>
    <span className={`sw-detail__value ${mono ? 'mono' : ''}`}>
      {value ?? <span className="sw-detail__null">—</span>}
    </span>
  </div>
)

const SwitchDetailModal = ({ open, onClose, switchData }) => {
  const [rpis, setRpis] = useState([])
  const [macs, setMacs] = useState([])
  const [loadingRpis, setLoadingRpis] = useState(false)
  const [loadingMacs, setLoadingMacs] = useState(false)
  const [tab, setTab] = useState('info')

  useEffect(() => {
    if (!open || !switchData) return
    setTab('info')

    /* load rpis */
    setLoadingRpis(true)
    switchesApi
      .getRpis(switchData.id)
      .then((r) => setRpis(r.data || []))
      .catch(() => setRpis([]))
      .finally(() => setLoadingRpis(false))

    /* load macs */
    setLoadingMacs(true)
    switchesApi
      .getMacs(switchData.id)
      .then((r) => setMacs(r.data || []))
      .catch(() => setMacs([]))
      .finally(() => setLoadingMacs(false))
  }, [open, switchData])

  if (!switchData) return null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Switch — ${switchData.ip}`}
      width={580}
    >
      {/* ── Tabs ── */}
      <div className="sw-detail__tabs">
        {['info', 'rpis', 'macs'].map((t) => (
          <button
            key={t}
            className={`sw-detail__tab ${tab === t ? 'sw-detail__tab--active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'info' && 'Information'}
            {t === 'rpis' && `RPis (${rpis.length})`}
            {t === 'macs' && `MACs (${macs.length})`}
          </button>
        ))}
      </div>

      {/* ── Info Tab ── */}
      {tab === 'info' && (
        <div className="sw-detail__info">
          <div className="sw-detail__section">
            <div className="sw-detail__section-title">
              <Network size={14} />
              General
            </div>
            <Row label="IP Address" value={switchData.ip} mono />
            <Row label="Name" value={switchData.name} />
            <Row label="Model" value={switchData.model} />
            <Row label="MAC Address" value={switchData.mac_address} mono />
            <Row label="Firmware" value={switchData.firmware_version} />
            <Row label="Serial Number" value={switchData.serial_number} />
            <Row label="Uptime" value={switchData.uptime} />
            <Row
              label="Status"
              value={<StatusBadge status={switchData.enabled ? 'active' : 'disabled'} />}
            />
          </div>

          <div className="sw-detail__section">
            <div className="sw-detail__section-title">
              <Clock size={14} />
              Timestamps
            </div>
            <Row
              label="Last Seen"
              value={
                switchData.last_seen
                  ? dayjs(switchData.last_seen).format('MMM D, YYYY HH:mm:ss')
                  : null
              }
            />
            <Row
              label="Created"
              value={
                switchData.created_at
                  ? dayjs(switchData.created_at).format('MMM D, YYYY HH:mm')
                  : null
              }
            />
          </div>
        </div>
      )}

      {/* ── RPis Tab ── */}
      {tab === 'rpis' && (
        <div className="sw-detail__list">
          {loadingRpis ? (
            <Spinner centered text="Loading RPis..." />
          ) : rpis.length === 0 ? (
            <div className="sw-detail__empty">No RPis found on this switch</div>
          ) : (
            rpis.map((rpi) => (
              <div key={rpi.id} className="sw-detail__rpi-item">
                <div className="sw-detail__rpi-left">
                  <Cpu size={14} color="var(--purple-main)" />
                  <span className="sw-detail__rpi-ip mono">{rpi.ip_mgmt}</span>
                  {rpi.label && (
                    <span className="sw-detail__rpi-label">{rpi.label}</span>
                  )}
                </div>
                <div className="sw-detail__rpi-right">
                  <span className="sw-detail__rpi-port">
                    Port: {rpi.switch_port || '—'}
                  </span>
                  <StatusBadge
                    status={rpi.last_ssh_success ? 'online' : 'offline'}
                  />
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── MACs Tab ── */}
      {tab === 'macs' && (
        <div className="sw-detail__list">
          {loadingMacs ? (
            <Spinner centered text="Loading MACs..." />
          ) : macs.length === 0 ? (
            <div className="sw-detail__empty">No MAC entries found</div>
          ) : (
            <div className="sw-detail__mac-table">
              <div className="sw-detail__mac-header">
                <span>Port</span>
                <span>MAC Address</span>
                <span>VLAN</span>
              </div>
              {macs.map((mac, i) => (
                <div key={i} className="sw-detail__mac-row">
                  <span className="sw-detail__mac-port">{mac.port}</span>
                  <span className="mono">{mac.mac_address}</span>
                  <span>{mac.vlan ?? '—'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

export default SwitchDetailModal