import React from 'react'
import './Button.css'

const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  icon: Icon,
  iconPosition = 'left',
  loading = false,
  disabled = false,
  onClick,
  type = 'button',
  className = '',
  danger = false,
  fullWidth = false,
}) => {
  const cls = [
    'btn',
    `btn--${variant}`,
    `btn--${size}`,
    danger ? 'btn--danger' : '',
    fullWidth ? 'btn--full' : '',
    loading ? 'btn--loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type={type}
      className={cls}
      disabled={disabled || loading}
      onClick={onClick}
    >
      {loading && <span className="btn__spinner" />}
      {!loading && Icon && iconPosition === 'left' && (
        <Icon size={15} strokeWidth={2} />
      )}
      {children && <span>{children}</span>}
      {!loading && Icon && iconPosition === 'right' && (
        <Icon size={15} strokeWidth={2} />
      )}
    </button>
  )
}

export default Button