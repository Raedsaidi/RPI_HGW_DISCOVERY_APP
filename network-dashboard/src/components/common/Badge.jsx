import React from 'react'
import './Badge.css'

const VARIANTS = {
  success: 'badge--success',
  warning: 'badge--warning',
  error: 'badge--error',
  info: 'badge--info',
  purple: 'badge--purple',
  cyan: 'badge--cyan',
  default: 'badge--default',
}

const Badge = ({ children, variant = 'default', dot = false, size = 'md' }) => {
  return (
    <span className={`badge badge--${size} ${VARIANTS[variant] || VARIANTS.default}`}>
      {dot && <span className="badge__dot" />}
      {children}
    </span>
  )
}

export const StatusBadge = ({ status }) => {
  const map = {
    online: { variant: 'success', label: 'Online' },
    running: { variant: 'info', label: 'Running' },
    done: { variant: 'success', label: 'Done' },
    partial: { variant: 'warning', label: 'Partial' },
    error: { variant: 'error', label: 'Error' },
    offline: { variant: 'error', label: 'Offline' },
    warning: { variant: 'warning', label: 'Warning' },
    unknown: { variant: 'default', label: 'Unknown' },
    active: { variant: 'success', label: 'Active' },
    disabled: { variant: 'default', label: 'Disabled' },
    true: { variant: 'success', label: 'Active' },
    false: { variant: 'default', label: 'Inactive' },
  }

  const key = String(status).toLowerCase()
  const config = map[key] || { variant: 'default', label: status }

  return (
    <Badge variant={config.variant} dot>
      {config.label}
    </Badge>
  )
}

export default Badge