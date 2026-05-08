// RpiDetailModal.jsx
import React, { useEffect, useState } from 'react'
import {
  Cpu,
  Activity,
  HardDrive,
  Thermometer,
  Terminal,
  Usb,
  Network,
  Container,
} from 'lucide-react'
import Modal from '@/components/common/Modal'
import Spinner from '@/components/common/Spinner'
import { StatusBadge } from '@/components/common/Badge'
import { rpisApi } from '@/api/endpoints'
import dayjs from 'dayjs'
import './RpiDetailModal.css'

/* ─────────────────────────────────────────
   Helpers
───────────────────────────────────────── */
const Row = ({ label, value, mono }) => (
  <div className="rpi-detail__row">
    <span className="rpi-detail__label">{label}</span>
    <span className={`rpi-detail__value ${mono ? 'mono' : ''}`}>
      {value ?? <span className="rpi-detail__null">—</span>}
    </span>
  </div>
)

const parseJson = (raw) => {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

const EmptySm = ({ text = 'None' }) => (
  <div className="rpi-detail__empty-sm">{text}</div>
)

/* ── Liste générique de strings ── */
const ScriptList = ({ items }) => {
  if (!items || items.length === 0) return <EmptySm text="No items found" />
  return (
    <div className="rpi-detail__script-list">
      {items.map((item, i) => (
        <div key={i} className="rpi-detail__script-item">
          <span className="rpi-detail__script-dot" />
          <span className="mono">
            {typeof item === 'string' ? item : JSON.stringify(item)}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ── Liste spécifique pour all_ips (objets {iface, ip, mac}) ── */
const IpList = ({ items }) => {
  if (!items || items.length === 0)
    return <EmptySm text="No IP addresses found" />

  /* Si c'est un tableau de strings simple */
  if (typeof items[0] === 'string') return <ScriptList items={items} />

  /* Si c'est un tableau d'objets */
  return (
    <div className="rpi-detail__ip-list">
      {items.map((entry, i) => (
        <div key={i} className="rpi-detail__ip-item">
          {/* Interface */}
          {entry.iface && (
            <span className="rpi-detail__ip-iface">{entry.iface}</span>
          )}
          {/* IP */}
          {entry.ip && (
            <span className="rpi-detail__ip-addr mono">{entry.ip}</span>
          )}
          {/* MAC */}
          {entry.mac && (
            <span className="rpi-detail__ip-mac mono">{entry.mac}</span>
          )}
        </div>
      ))}
    </div>
  )
}

/* ── Liste USB — peut être objets ou strings ── */
const UsbList = ({ items }) => {
  if (!items || items.length === 0)
    return <EmptySm text="No USB devices detected" />

  return (
    <div className="rpi-detail__script-list">
      {items.map((item, i) => {
        /* Si string simple */
        if (typeof item === 'string') {
          return (
            <div key={i} className="rpi-detail__script-item">
              <span className="rpi-detail__script-dot" />
              <span className="mono">{item}</span>
            </div>
          )
        }
        /* Si objet */
        return (
          <div
            key={i}
            className="rpi-detail__script-item rpi-detail__script-item--col"
          >
            <span className="rpi-detail__script-dot" />
            <div className="rpi-detail__usb-detail">
              {Object.entries(item).map(([k, v]) => (
                <div key={k} className="rpi-detail__usb-row">
                  <span className="rpi-detail__usb-key">{k}</span>
                  <span className="mono rpi-detail__usb-val">{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ── NEW: Docker details viewer ── */
const DockerObjectDetails = ({ data }) => {
  if (!data) return <EmptySm text="No details" />

  const entries = Object.entries(data)

  return (
    <div className="rpi-detail__docker-details">
      <div className="rpi-detail__docker-details-grid">
        {entries.map(([k, v]) => (
          <div key={k} className="rpi-detail__docker-details-row">
            <div className="rpi-detail__docker-details-key">{k}</div>
            <div className="rpi-detail__docker-details-val mono">
              {v === null || v === undefined
                ? '—'
                : typeof v === 'string'
                ? v
                : JSON.stringify(v)}
            </div>
          </div>
        ))}
      </div>

      <div className="rpi-detail__subsection-title" style={{ marginTop: 12 }}>
        Raw JSON
      </div>
      <pre className="rpi-detail__raw-block rpi-detail__raw-block--scroll">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}

/* ─────────────────────────────────────────
   Component
───────────────────────────────────────── */
const RpiDetailModal = ({ open, onClose, rpiData }) => {
  const [facts, setFacts] = useState([])
  const [loadingFacts, setLoadingFacts] = useState(false)
  const [tab, setTab] = useState('info')

  // NEW: docker click → details modal
  const [dockerDetail, setDockerDetail] = useState(null)
  // dockerDetail = { type: 'container'|'image', data: object } | null

  useEffect(() => {
    if (!open || !rpiData) return
    setTab('info')
    setDockerDetail(null)
    setLoadingFacts(true)
    rpisApi
      .getFacts(rpiData.ip_mgmt, { page: 1, page_size: 5 })
      .then((r) => setFacts(r.data?.data || []))
      .catch(() => setFacts([]))
      .finally(() => setLoadingFacts(false))
  }, [open, rpiData])

  if (!rpiData) return null

  const latest = facts[0] || null

  /* parsed JSON fields */
  const runningScripts = parseJson(latest?.running_scripts)
  const dockerContainers = parseJson(latest?.docker_containers)
  const dockerImages = parseJson(latest?.docker_images)
  const usbDevices = parseJson(latest?.usb_devices)
  const allIps = parseJson(latest?.all_ips)

  /* memory % */
  const memPct =
    latest?.mem_total_mb && latest?.mem_used_mb
      ? Math.round((latest.mem_used_mb / latest.mem_total_mb) * 100)
      : null

  /* disk % */
  const diskPct = latest?.disk_used_pct ? parseFloat(latest.disk_used_pct) : null

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={`RPi — ${rpiData.ip_mgmt}`}
        width={620}
      >
        {/* ── Tabs ── */}
        <div className="rpi-detail__tabs">
          {['info', 'metrics', 'scripts', 'hardware', 'history'].map((t) => (
            <button
              key={t}
              className={`rpi-detail__tab ${
                tab === t ? 'rpi-detail__tab--active' : ''
              }`}
              onClick={() => setTab(t)}
            >
              {t === 'info' && 'Information'}
              {t === 'metrics' && 'Metrics'}
              {t === 'scripts' && 'Scripts & Docker'}
              {t === 'hardware' && 'USB & Network'}
              {t === 'history' && `History (${facts.length})`}
            </button>
          ))}
        </div>

        {/* ══════════════════════════════════════
            TAB — INFO
        ══════════════════════════════════════ */}
        {tab === 'info' && (
          <div className="rpi-detail__content">
            <div className="rpi-detail__section">
              <div className="rpi-detail__section-title">
                <Cpu size={14} /> Network
              </div>
              <Row label="IP Address" value={rpiData.ip_mgmt} mono />
              <Row label="MAC Address" value={rpiData.mac} mono />
              <Row label="Label" value={rpiData.label} />
              <Row label="Switch IP" value={rpiData.switch_ip} mono />
              <Row label="Switch Port" value={rpiData.switch_port} />
              <Row label="Gateway IP" value={rpiData.hgw_ip} mono />
            </div>

            <div className="rpi-detail__section">
              <div className="rpi-detail__section-title">
                <Activity size={14} /> Status
              </div>
              <Row
                label="SSH Status"
                value={
                  <StatusBadge
                    status={
                      rpiData.last_ssh_success === true
                        ? 'online'
                        : rpiData.last_ssh_success === false
                        ? 'offline'
                        : 'unknown'
                    }
                  />
                }
              />
              <Row
                label="SSH Error"
                value={
                  rpiData.last_ssh_error ? (
                    <span className="rpi-detail__error-msg">
                      {rpiData.last_ssh_error}
                    </span>
                  ) : null
                }
              />
              <Row
                label="Custom Creds"
                value={
                  <StatusBadge
                    status={rpiData.has_custom_credentials ? 'active' : 'disabled'}
                  />
                }
              />
              <Row
                label="Last Seen"
                value={
                  rpiData.last_seen
                    ? dayjs(rpiData.last_seen).format('MMM D, YYYY HH:mm:ss')
                    : null
                }
              />
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════
            TAB — METRICS
        ══════════════════════════════════════ */}
        {tab === 'metrics' && (
          <div className="rpi-detail__content">
            {loadingFacts ? (
              <Spinner centered text="Loading metrics..." />
            ) : !latest ? (
              <div className="rpi-detail__empty">
                No metrics collected yet for this device.
              </div>
            ) : (
              <>
                {/* System */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Cpu size={14} /> System
                  </div>
                  <Row label="Hostname" value={latest.hostname} />
                  <Row label="OS" value={latest.os_pretty} />
                  <Row label="OS Name" value={latest.os_name} />
                  <Row label="OS Version" value={latest.os_version} />
                  <Row label="Kernel" value={latest.kernel} mono />
                  <Row label="Model" value={latest.model} />
                  <Row label="LAN Interface" value={latest.lan_iface} />
                  <Row label="LAN IP" value={latest.lan_ip} mono />
                  <Row label="Gateway IP" value={latest.hgw_ip} mono />
                  <Row
                    label="Docker"
                    value={
                      <StatusBadge
                        status={latest.docker_available ? 'active' : 'disabled'}
                      />
                    }
                  />
                  <Row
                    label="Collected At"
                    value={
                      latest.collected_at
                        ? dayjs(latest.collected_at).format('MMM D, YYYY HH:mm:ss')
                        : null
                    }
                  />
                </div>

                {/* Hardware */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Thermometer size={14} /> Hardware
                  </div>
                  <Row
                    label="Temperature"
                    value={
                      latest.temp_celsius ? (
                        <span className="rpi-detail__temp">
                          {latest.temp_celsius}°C
                        </span>
                      ) : null
                    }
                  />
                  <Row
                    label="Memory Total"
                    value={latest.mem_total_mb ? `${latest.mem_total_mb} MB` : null}
                  />
                  <Row
                    label="Memory Used"
                    value={latest.mem_used_mb ? `${latest.mem_used_mb} MB` : null}
                  />
                  <Row
                    label="Memory Free"
                    value={latest.mem_free_mb ? `${latest.mem_free_mb} MB` : null}
                  />
                  <Row
                    label="Disk Total"
                    value={latest.disk_total_gb ? `${latest.disk_total_gb} GB` : null}
                  />
                  <Row
                    label="Disk Used"
                    value={latest.disk_used_gb ? `${latest.disk_used_gb} GB` : null}
                  />
                  <Row
                    label="Disk Used %"
                    value={latest.disk_used_pct ? `${latest.disk_used_pct}%` : null}
                  />
                </div>

                {/* Memory bar */}
                {memPct !== null && (
                  <div className="rpi-detail__bar-wrap">
                    <div className="rpi-detail__bar-header">
                      <span>Memory Usage</span>
                      <span
                        className={`rpi-detail__bar-pct rpi-detail__bar-pct--${
                          memPct > 85 ? 'danger' : memPct > 60 ? 'warn' : 'ok'
                        }`}
                      >
                        {memPct}%
                      </span>
                    </div>
                    <div className="rpi-detail__bar">
                      <div
                        className={`rpi-detail__bar-fill rpi-detail__bar-fill--${
                          memPct > 85 ? 'danger' : memPct > 60 ? 'warn' : ''
                        }`}
                        style={{ width: `${Math.min(memPct, 100)}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Disk bar */}
                {diskPct !== null && (
                  <div className="rpi-detail__bar-wrap">
                    <div className="rpi-detail__bar-header">
                      <span>Disk Usage</span>
                      <span
                        className={`rpi-detail__bar-pct rpi-detail__bar-pct--${
                          diskPct > 85 ? 'danger' : diskPct > 60 ? 'warn' : 'ok'
                        }`}
                      >
                        {diskPct}%
                      </span>
                    </div>
                    <div className="rpi-detail__bar">
                      <div
                        className={`rpi-detail__bar-fill rpi-detail__bar-fill--${
                          diskPct > 85 ? 'danger' : diskPct > 60 ? 'warn' : ''
                        }`}
                        style={{ width: `${Math.min(diskPct, 100)}%` }}
                      />
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════
            TAB — SCRIPTS & DOCKER
        ══════════════════════════════════════ */}
        {tab === 'scripts' && (
          <div className="rpi-detail__content">
            {loadingFacts ? (
              <Spinner centered text="Loading scripts..." />
            ) : !latest ? (
              <div className="rpi-detail__empty">
                No data collected yet for this device.
              </div>
            ) : (
              <>
                {/* Running Scripts */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Terminal size={14} /> Running Scripts
                  </div>
                  {runningScripts ? (
                    <ScriptList items={runningScripts} />
                  ) : (
                    <EmptySm text="No running scripts detected" />
                  )}
                </div>

                {/* Running Python */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Terminal size={14} /> Running Python Processes
                  </div>
                  {latest.running_python ? (
                    <div className="rpi-detail__raw-block">
                      {latest.running_python}
                    </div>
                  ) : (
                    <EmptySm text="No Python processes detected" />
                  )}
                </div>

                {/* Docker */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Container size={14} /> Docker
                  </div>
                  <div className="rpi-detail__row">
                    <span className="rpi-detail__label">Available</span>
                    <span className="rpi-detail__value">
                      <StatusBadge
                        status={latest.docker_available ? 'active' : 'disabled'}
                      />
                    </span>
                  </div>

                  {latest.docker_available && (
                    <>
                      {/* Containers */}
                      <div className="rpi-detail__subsection">
                        <div className="rpi-detail__subsection-title">
                          Containers ({dockerContainers?.length || 0})
                        </div>

                        {dockerContainers && dockerContainers.length > 0 ? (
                          <div className="rpi-detail__docker-list">
                            {dockerContainers.map((c, i) => (
                              <div
                                key={i}
                                className="rpi-detail__docker-item rpi-detail__docker-item--clickable"
                                role="button"
                                tabIndex={0}
                                onClick={() =>
                                  setDockerDetail({ type: 'container', data: c })
                                }
                                onKeyDown={(e) =>
                                  e.key === 'Enter' &&
                                  setDockerDetail({ type: 'container', data: c })
                                }
                                title="Click to view details"
                              >
                                <div className="rpi-detail__docker-header">
                                  <span className="rpi-detail__docker-name mono">
                                    {c.name || c.container_id?.substring(0, 12)}
                                  </span>
                                  <span
                                    className={`rpi-detail__docker-status rpi-detail__docker-status--${
                                      c.status
                                        ?.toLowerCase()
                                        .includes('up')
                                        ? 'running'
                                        : 'stopped'
                                    }`}
                                  >
                                    {c.status || 'unknown'}
                                  </span>
                                </div>
                                <div className="rpi-detail__docker-meta">
                                  <span className="rpi-detail__docker-image">
                                    {c.image}
                                  </span>
                                  {c.created && (
                                    <span className="rpi-detail__docker-created">
                                      {c.created}
                                    </span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <EmptySm text="No containers found" />
                        )}
                      </div>

                      {/* Images */}
                      <div className="rpi-detail__subsection">
                        <div className="rpi-detail__subsection-title">
                          Images ({dockerImages?.length || 0})
                        </div>

                        {dockerImages && dockerImages.length > 0 ? (
                          <div className="rpi-detail__docker-list">
                            {dockerImages.map((img, i) => (
                              <div
                                key={i}
                                className="rpi-detail__docker-item rpi-detail__docker-item--clickable"
                                role="button"
                                tabIndex={0}
                                onClick={() =>
                                  setDockerDetail({ type: 'image', data: img })
                                }
                                onKeyDown={(e) =>
                                  e.key === 'Enter' &&
                                  setDockerDetail({ type: 'image', data: img })
                                }
                                title="Click to view details"
                              >
                                <div className="rpi-detail__docker-header">
                                  <span className="rpi-detail__docker-name mono">
                                    {img.repository && img.tag
                                      ? `${img.repository}:${img.tag}`
                                      : img.repository || img.image_id?.substring(0, 12) || 'unknown'}
                                  </span>
                                  <span className="rpi-detail__docker-size">
                                    {img.size}
                                  </span>
                                </div>
                                <div className="rpi-detail__docker-meta">
                                  <span className="rpi-detail__docker-id mono">
                                    {img.image_id?.substring(0, 12)}
                                  </span>
                                  {img.created && (
                                    <span className="rpi-detail__docker-created">
                                      {img.created}
                                    </span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <EmptySm text="No images found" />
                        )}
                      </div>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════
            TAB — USB & NETWORK
        ══════════════════════════════════════ */}
        {tab === 'hardware' && (
          <div className="rpi-detail__content">
            {loadingFacts ? (
              <Spinner centered text="Loading hardware info..." />
            ) : !latest ? (
              <div className="rpi-detail__empty">
                No data collected yet for this device.
              </div>
            ) : (
              <>
                {/* USB Devices */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Usb size={14} /> USB Devices
                  </div>
                  <UsbList items={usbDevices} />
                </div>

                {/* All IPs */}
                <div className="rpi-detail__section">
                  <div className="rpi-detail__section-title">
                    <Network size={14} /> All IP Addresses
                  </div>
                  <IpList items={allIps} />
                </div>

                {/* Raw ifconfig */}
                {latest.raw_ifconfig && (
                  <div className="rpi-detail__section">
                    <div className="rpi-detail__section-title">
                      <Network size={14} /> Raw ifconfig
                    </div>
                    <div className="rpi-detail__raw-block rpi-detail__raw-block--scroll">
                      {latest.raw_ifconfig}
                    </div>
                  </div>
                )}

                {/* Raw ps */}
                {latest.raw_ps && (
                  <div className="rpi-detail__section">
                    <div className="rpi-detail__section-title">
                      <Terminal size={14} /> Raw Process List (ps)
                    </div>
                    <div className="rpi-detail__raw-block rpi-detail__raw-block--scroll">
                      {latest.raw_ps}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════
            TAB — HISTORY
        ══════════════════════════════════════ */}
        {tab === 'history' && (
          <div className="rpi-detail__content">
            {loadingFacts ? (
              <Spinner centered text="Loading history..." />
            ) : facts.length === 0 ? (
              <div className="rpi-detail__empty">No history available.</div>
            ) : (
              <div className="rpi-detail__history">
                {facts.map((fact) => {
                  const scripts = parseJson(fact.running_scripts)
                  const containers = parseJson(fact.docker_containers)
                  const images = parseJson(fact.docker_images)
                  const usb = parseJson(fact.usb_devices)
                  const pct =
                    fact.mem_total_mb && fact.mem_used_mb
                      ? Math.round((fact.mem_used_mb / fact.mem_total_mb) * 100)
                      : null

                  return (
                    <div key={fact.id} className="rpi-detail__history-item">
                      {/* Header */}
                      <div className="rpi-detail__history-header">
                        <span className="rpi-detail__history-run">
                          Run #{fact.run_id}
                        </span>
                        <span className="rpi-detail__history-time">
                          {fact.collected_at
                            ? dayjs(fact.collected_at).format('MMM D, YYYY HH:mm')
                            : '—'}
                        </span>
                      </div>

                      {/* Grid */}
                      <div className="rpi-detail__history-grid">
                        <div className="rpi-detail__history-row">
                          <span>Host</span>
                          <span className="mono">{fact.hostname || '—'}</span>
                        </div>
                        <div className="rpi-detail__history-row">
                          <span>OS</span>
                          <span>{fact.os_pretty || fact.os_name || '—'}</span>
                        </div>
                        <div className="rpi-detail__history-row">
                          <span>Temp</span>
                          <span>{fact.temp_celsius ? `${fact.temp_celsius}°C` : '—'}</span>
                        </div>
                        <div className="rpi-detail__history-row">
                          <span>Memory</span>
                          <span>
                            {fact.mem_used_mb && fact.mem_total_mb
                              ? `${fact.mem_used_mb}/${fact.mem_total_mb} MB (${pct}%)`
                              : '—'}
                          </span>
                        </div>
                        <div className="rpi-detail__history-row">
                          <span>Disk</span>
                          <span>
                            {fact.disk_used_gb && fact.disk_total_gb
                              ? `${fact.disk_used_gb}/${fact.disk_total_gb} GB`
                              : '—'}
                          </span>
                        </div>
                        <div className="rpi-detail__history-row">
                          <span>Docker</span>
                          <span className="rpi-detail__history-badge">
                            {fact.docker_available ? 'active' : 'disabled'}
                          </span>
                        </div>
                      </div>

                      {/* Scripts tags */}
                      {scripts && scripts.length > 0 && (
                        <div className="rpi-detail__history-scripts">
                          <span className="rpi-detail__history-scripts-label">
                            Scripts:
                          </span>
                          <div className="rpi-detail__history-tags">
                            {scripts.map((s, i) => (
                              <span key={i} className="rpi-detail__tag">
                                {typeof s === 'string' ? s : JSON.stringify(s)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Containers tags */}
                      {containers && containers.length > 0 && (
                        <div className="rpi-detail__history-scripts">
                          <span className="rpi-detail__history-scripts-label">
                            Containers:
                          </span>
                          <div className="rpi-detail__history-tags">
                            {containers.map((c, i) => (
                              <span
                                key={i}
                                className="rpi-detail__tag rpi-detail__tag--blue"
                              >
                                {c.name ||
                                  c.container_id?.substring(0, 12) ||
                                  JSON.stringify(c)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Images tags */}
                      {images && images.length > 0 && (
                        <div className="rpi-detail__history-scripts">
                          <span className="rpi-detail__history-scripts-label">
                            Images:
                          </span>
                          <div className="rpi-detail__history-tags">
                            {images.map((img, i) => (
                              <span
                                key={i}
                                className="rpi-detail__tag rpi-detail__tag--green"
                              >
                                {img.repository && img.tag
                                  ? `${img.repository}:${img.tag}`
                                  : JSON.stringify(img)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* USB tags */}
                      {usb && usb.length > 0 && (
                        <div className="rpi-detail__history-scripts">
                          <span className="rpi-detail__history-scripts-label">
                            USB:
                          </span>
                          <div className="rpi-detail__history-tags">
                            {usb.map((u, i) => (
                              <span
                                key={i}
                                className="rpi-detail__tag rpi-detail__tag--purple"
                              >
                                {typeof u === 'string' ? u : JSON.stringify(u)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ─────────────────────────────────────────
          NEW: Docker Details modal (on click)
      ───────────────────────────────────────── */}
      {dockerDetail && (
        <Modal
          open={true}
          onClose={() => setDockerDetail(null)}
          title={
            dockerDetail.type === 'container'
              ? `Container — ${
                  dockerDetail.data?.name ||
                  dockerDetail.data?.container_id?.substring?.(0, 12) ||
                  'details'
                }`
              : `Image — ${
                  dockerDetail.data?.repository
                    ? `${dockerDetail.data.repository}:${dockerDetail.data?.tag || ''}`
                    : dockerDetail.data?.image_id?.substring?.(0, 12) || 'details'
                }`
          }
          width={760}
        >
          <div className="rpi-detail__content">
            <DockerObjectDetails data={dockerDetail.data} />
          </div>
        </Modal>
      )}
    </>
  )
}

export default RpiDetailModal