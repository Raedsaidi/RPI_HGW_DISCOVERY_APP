import React from 'react'
import { X, AlertCircle, CheckCircle, AlertTriangle, Info } from 'lucide-react'
import './NotificationContainer.css'

const NotificationContainer = ({ notifications, onRemove }) => {
  const getIcon = (type) => {
    switch (type) {
      case 'error':
        return <AlertCircle size={18} />
      case 'success':
        return <CheckCircle size={18} />
      case 'warning':
        return <AlertTriangle size={18} />
      case 'info':
      default:
        return <Info size={18} />
    }
  }

  return (
    <div className="notification-container">
      {notifications.map((notif) => (
        <div
          key={notif.id}
          className={`notification notification--${notif.type}`}
        >
          <div className="notification__icon">
            {getIcon(notif.type)}
          </div>
          <div className="notification__content">
            {notif.message}
          </div>
          <button
            className="notification__close"
            onClick={() => onRemove(notif.id)}
            aria-label="Close notification"
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}

export default NotificationContainer
