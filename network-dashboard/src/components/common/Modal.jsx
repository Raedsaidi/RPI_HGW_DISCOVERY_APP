import React, { useEffect } from 'react'
import { X } from 'lucide-react'
import Button from './Button'
import './Modal.css'

const Modal = ({
  open,
  onClose,
  title,
  children,
  footer,
  width = 520,
  closable = true,
  loading = false,
}) => {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!open) return null

  return (
    <div className="modal-overlay" onClick={closable ? onClose : undefined}>
      <div
        className="modal"
        style={{ width }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal__header">
          <h3 className="modal__title">{title}</h3>
          {closable && (
            <button className="modal__close" onClick={onClose}>
              <X size={16} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="modal__body">{children}</div>

        {/* Footer */}
        {footer !== undefined && (
          <div className="modal__footer">{footer}</div>
        )}
      </div>
    </div>
  )
}

export default Modal