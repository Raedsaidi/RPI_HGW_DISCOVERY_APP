import React, { useState, useMemo } from 'react'
import {
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
  Eye,
  KeyRound,
  Link2,
  RefreshCw,
  Trash2,
  Router,
  Cpu,
  PowerOff,
} from 'lucide-react'
import { StatusBadge } from '@/components/common/Badge'
import dayjs from 'dayjs'
import './SwitchExpanderView.css'

const RpiCard = ({
  row,
  reconnectingIp,
  rebootingIp,
  onDetail,
  onCred,
  onReconnect,
  onReboot,
  onDeleteCreds,
  onTerminal,
}) => {
  const reconnecting = reconnectingIp === row.ip_mgmt
  const rebooting    = rebootingIp    === row.ip_mgmt
  const busy         = reconnecting || rebooting

  const sshOk   = row.last_ssh_success === true
  const sshFail = row.last_ssh_success === false

  return (
    <div className={`rpi-card ${busy ? 'rpi-card--busy' : ''}`}>
      {/* Port badge */}
      {row.switch_port && (
        <div className="rpi-card__port-badge">
          {row.switch_port}
        </div>
      )}

      {/* SSH status dot */}
      <div
        className={`rpi-card__ssh-dot ${
          sshOk   ? 'rpi-card__ssh-dot--ok' :
          sshFail ? 'rpi-card__ssh-dot--fail' :
                    'rpi-card__ssh-dot--unknown'
        }`}
      />

      {/* Main info */}
      <div className="rpi-card__body">
        <div
          className="rpi-card__ip rpi-card__ip--clickable"
          title="Open terminal"
          onClick={() => !busy && onTerminal?.(row)}
        >
          {row.ip_mgmt || '—'}
        </div>

        {row.label && (
          <div className="rpi-card__label">{row.label}</div>
        )}

        <div className="rpi-card__meta">
          {row.mac && (
            <span className="rpi-card__meta-item">{row.mac}</span>
          )}
          {row.hgw_ip && (
            <span className="rpi-card__meta-item rpi-card__meta-item--cyan">
              HGW: {row.hgw_ip}
            </span>
          )}
          {row.last_seen && (
            <span className="rpi-card__meta-item rpi-card__meta-item--time">
              {dayjs(row.last_seen).format('MMM D, HH:mm')}
            </span>
          )}
        </div>

        <div className="rpi-card__badges">
          {sshOk && (
            <span className="rpi-card__ssh-badge rpi-card__ssh-badge--ok">
              <CheckCircle size={11} /> SSH OK
            </span>
          )}
          {sshFail && (
            <span className="rpi-card__ssh-badge rpi-card__ssh-badge--fail">
              <XCircle size={11} /> SSH Failed
            </span>
          )}
          {row.has_custom_credentials && (
            <StatusBadge status="active" />
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="rpi-card__actions">
        {/* View details */}
        <button
          className="rpi-card__action rpi-card__action--view"
          title="View details"
          onClick={() => onDetail(row)}
          disabled={busy}
        >
          <Eye size={13} />
        </button>

        {/* Manage credentials */}
        <button
          className="rpi-card__action rpi-card__action--cred"
          title="Manage credentials"
          onClick={() => onCred(row)}
          disabled={busy}
        >
          <KeyRound size={13} />
        </button>

        {/* Reconnect */}
        <button
          className="rpi-card__action rpi-card__action--reconnect"
          title={reconnecting ? 'Reconnecting...' : 'Reconnect'}
          onClick={() => onReconnect(row)}
          disabled={busy}
        >
          {reconnecting
            ? <RefreshCw size={13} className="spin" />
            : <Link2 size={13} />
          }
        </button>

        {/* Reboot via PoE cycle */}
        <button
          className="rpi-card__action rpi-card__action--reboot"
          title={rebooting ? 'Rebooting...' : 'Reboot via PoE cycle'}
          onClick={() => onReboot(row)}
          disabled={busy}
        >
          {rebooting
            ? <RefreshCw size={13} className="spin" />
            : <PowerOff size={13} />
          }
        </button>

        {/* Delete custom credentials */}
        {row.has_custom_credentials && (
          <button
            className="rpi-card__action rpi-card__action--delete"
            title="Remove credentials"
            onClick={() => onDeleteCreds(row.ip_mgmt)}
            disabled={busy}
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  )
}

const SwitchGroup = ({
  switchIp,
  rpis,
  reconnectingIp,
  rebootingIp,
  onDetail,
  onCred,
  onReconnect,
  onReboot,
  onDeleteCreds,
  onTerminal,
}) => {
  const [open, setOpen] = useState(true)

  const sshOkCount   = rpis.filter(r => r.last_ssh_success === true).length
  const sshFailCount = rpis.filter(r => r.last_ssh_success === false).length

  return (
    <div className="switch-group">
      {/* Header */}
      <button className="switch-group__header" onClick={() => setOpen(o => !o)}>
        <div className="switch-group__header-left">
          <span className="switch-group__chevron">
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
          <Router size={16} className="switch-group__icon" />
          <span className="switch-group__ip">
            {switchIp || 'No Switch'}
          </span>
        </div>

        <div className="switch-group__header-right">
          <span className="switch-group__stat">
            <Cpu size={13} />
            {rpis.length} RPi{rpis.length !== 1 ? 's' : ''}
          </span>
          {sshOkCount > 0 && (
            <span className="switch-group__stat switch-group__stat--ok">
              <CheckCircle size={13} />
              {sshOkCount}
            </span>
          )}
          {sshFailCount > 0 && (
            <span className="switch-group__stat switch-group__stat--fail">
              <XCircle size={13} />
              {sshFailCount}
            </span>
          )}
        </div>
      </button>

      {/* Cards grid */}
      {open && (
        <div className="switch-group__body">
          <div className="switch-group__grid">
            {rpis.map(row => (
              <RpiCard
                key={row.id || row.ip_mgmt}
                row={row}
                reconnectingIp={reconnectingIp}
                rebootingIp={rebootingIp}
                onDetail={onDetail}
                onCred={onCred}
                onReconnect={onReconnect}
                onReboot={onReboot}
                onDeleteCreds={onDeleteCreds}
                onTerminal={onTerminal}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const SwitchExpanderView = ({
  data,
  reconnectingIp,
  rebootingIp,
  onDetail,
  onCred,
  onReconnect,
  onReboot,
  onDeleteCreds,
  onTerminal,
}) => {
  const groups = useMemo(() => {
    const map = {}
    data.forEach(rpi => {
      const key = rpi.switch_ip || '__no_switch__'
      if (!map[key]) map[key] = []
      map[key].push(rpi)
    })

    return Object.entries(map).sort(([a], [b]) => {
      if (a === '__no_switch__') return 1
      if (b === '__no_switch__') return -1
      return a.localeCompare(b)
    })
  }, [data])

  return (
    <div className="switch-expander">
      {groups.map(([switchIp, rpis]) => (
        <SwitchGroup
          key={switchIp}
          switchIp={switchIp === '__no_switch__' ? null : switchIp}
          rpis={rpis}
          reconnectingIp={reconnectingIp}
          rebootingIp={rebootingIp}
          onDetail={onDetail}
          onCred={onCred}
          onReconnect={onReconnect}
          onReboot={onReboot}
          onDeleteCreds={onDeleteCreds}
          onTerminal={onTerminal}
        />
      ))}
    </div>
  )
}

export default SwitchExpanderView