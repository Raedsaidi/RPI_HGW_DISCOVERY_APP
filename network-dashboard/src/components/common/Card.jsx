import React from 'react'
import './Card.css'

const Card = ({
  children,
  title,
  subtitle,
  extra,
  padding = true,
  className = '',
  accentColor,
  hoverable = false,
  style = {},
}) => {
  return (
    <div
      className={`card ${hoverable ? 'card--hoverable' : ''} ${className}`}
      style={{
        borderTop: accentColor ? `3px solid ${accentColor}` : undefined,
        ...style,
      }}
    >
      {(title || extra) && (
        <div className="card__header">
          <div className="card__header-left">
            {title && <h3 className="card__title">{title}</h3>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {extra && <div className="card__extra">{extra}</div>}
        </div>
      )}
      <div className={`card__body ${!padding ? 'card__body--no-padding' : ''}`}>
        {children}
      </div>
    </div>
  )
}

export default Card