import React from 'react'
import { useNotifications } from '@/context/NotificationContext'
import { CheckCircle, XCircle, AlertCircle, Info } from 'lucide-react'
import './Toast.css'

const Toast = ({ notification }) => {
  const { removeNotification } = useNotifications()

  const getIcon = () => {
    switch (notification.type) {
      case 'success':
        return <CheckCircle size={16} />
      case 'error':
        return <XCircle size={16} />
      case 'warning':
        return <AlertCircle size={16} />
      case 'info':
      return <Info size={16} />
      default:
        return <Info size={16} />
    }
  }

  const handleClose = () => {
    removeNotification(notification.id)
  }

  return (
    <div className={`toast toast--${notification.type}`}>
      <div className="toast__icon">
        {getIcon()}
      </div>
      <div className="toast__content">
        <div className="toast__message">
          {notification.message}
        </div>
        <button 
          className="toast__close"
          onClick={handleClose}
          aria-label="Fermer"
        >
          ×
        </button>
      </div>
    </div>
  )
}

export default Toast
