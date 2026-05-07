import React from 'react'
import { Wifi, Globe, Cpu, Clock } from 'lucide-react'
import Modal from '@/components/common/Modal'
import dayjs from 'dayjs'
import './HgwDetailModal.css'

const Row = ({ label, value, mono }) => (
  <div className="hgw-detail__row">
    <span className="hgw-detail__label">{label}</span>
    <span className={`hgw-detail__value ${mono ? 'mono' : ''}`}>
      {value ?? <span className="hgw-detail__null">—</span>}
    </span>
  </div>
)

const formatUptime = (seconds) => {
  if (!seconds) return null
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${d}d ${h}h ${m}m`
}

const formatMem = (kb) => {
  if (!kb) return null
  return `${Math.round(kb / 1024)} MB`
}

/**
 * Extraire le préfixe réseau depuis l'IP de la gateway.
 * Ex: "192.168.1.1" → "192.168.1.x"
 */
const getNetworkPrefix = (ip) => {
  if (!ip) return null
  const parts = ip.split('.')
  if (parts.length !== 4) return null
  return `${parts[0]}.${parts[1]}.${parts[2]}.x`
}

const HgwDetailModal = ({ open, onClose, hgwData }) => {
  if (!hgwData) return null

  const memPct =
    hgwData.mem_total_kb && hgwData.mem_free_kb
      ? Math.round(
          ((hgwData.mem_total_kb - hgwData.mem_free_kb) /
            hgwData.mem_total_kb) *
            100
        )
      : null

  const networkPrefix = hgwData.network || getNetworkPrefix(hgwData.ip)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Gateway — ${hgwData.ip}`}
      width={560}
    >
      <div className="hgw-detail__content">

        {/* ── Identity ── */}
        <div className="hgw-detail__section">
          <div className="hgw-detail__section-title">
            <Wifi size={14} /> Device Identity
          </div>

          <Row label="IP Address" value={hgwData.ip} mono />

          <Row
            label="Network"
            value={
              networkPrefix
                ? <span className="hgw-detail__network-badge">{networkPrefix}</span>
                : null
            }
          />

          <Row label="Manufacturer" value={hgwData.manufacturer} />
          <Row label="Model" value={hgwData.model_name} />
          <Row label="Serial Number" value={hgwData.serial_number} mono />

          {/* NEW: instance_key (important when multiple HGWs share same IP) */}
          <Row label="Instance Key" value={hgwData.instance_key} mono />

          <Row label="SW Version" value={hgwData.software_version} />
          <Row label="HW Version" value={hgwData.hardware_version} />
          <Row label="Via RPi" value={hgwData.via_rpi_ip} mono />
        </div>

        {/* ── Network ── */}
        <div className="hgw-detail__section">
          <div className="hgw-detail__section-title">
            <Globe size={14} /> Network
          </div>
          <Row label="External IP" value={hgwData.external_ip} mono />
        </div>

        {/* ── Hardware ── */}
        <div className="hgw-detail__section">
          <div className="hgw-detail__section-title">
            <Cpu size={14} /> Hardware
          </div>
          <Row label="Uptime" value={formatUptime(hgwData.uptime_seconds)} />
          <Row label="Memory Free" value={formatMem(hgwData.mem_free_kb)} />
          <Row label="Memory Total" value={formatMem(hgwData.mem_total_kb)} />

          {memPct !== null && (
            <div className="hgw-detail__row">
              <span className="hgw-detail__label">Memory Used</span>
              <div className="hgw-detail__mem-wrap">
                <div className="hgw-detail__mem-bar">
                  <div
                    className="hgw-detail__mem-fill"
                    style={{ width: `${memPct}%` }}
                  />
                </div>
                <span className="hgw-detail__mem-pct">{memPct}%</span>
              </div>
            </div>
          )}
        </div>

        {/* ── Timestamp ── */}
        <div className="hgw-detail__section">
          <div className="hgw-detail__section-title">
            <Clock size={14} /> Timestamps
          </div>
          <Row
            label="Last Seen"
            value={
              hgwData.last_seen
                ? dayjs(hgwData.last_seen).format('MMM D, YYYY HH:mm:ss')
                : null
            }
          />
        </div>

      </div>
    </Modal>
  )
}

export default HgwDetailModal