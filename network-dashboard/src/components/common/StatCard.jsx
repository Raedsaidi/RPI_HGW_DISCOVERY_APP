import React from 'react'
import './StatCard.css'

const StatCard = ({
  title,
  value,
  icon: Icon,
  color = '#1890ff',
  bg = '#e6f7ff',
  trend,
  trendLabel,
  loading = false,
}) => {
  return (
    <div className="stat-card" style={{ borderTop: `3px solid ${color}` }}>
      <div className="stat-card__body">
        <div className="stat-card__content">
          <span className="stat-card__title">{title}</span>
          {loading ? (
            <div className="stat-card__skeleton" />
          ) : (
            <span className="stat-card__value">{value ?? '—'}</span>
          )}
          {trend !== undefined && !loading && (
            <span
              className={`stat-card__trend ${
                trend >= 0 ? 'stat-card__trend--up' : 'stat-card__trend--down'
              }`}
            >
              {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}%
              {trendLabel && (
                <span className="stat-card__trend-label"> {trendLabel}</span>
              )}
            </span>
          )}
        </div>
        <div
          className="stat-card__icon-wrap"
          style={{ background: bg, color: color }}
        >
          {Icon && <Icon size={22} strokeWidth={2} />}
        </div>
      </div>
    </div>
  )
}

export default StatCard