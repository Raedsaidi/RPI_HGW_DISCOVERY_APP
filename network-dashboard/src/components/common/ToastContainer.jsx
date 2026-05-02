import React from 'react'
import { useNotifications } from '@/context/NotificationContext'
import Toast from './Toast'
import './Toast.css'

const ToastContainer = () => {
  const { notifications } = useNotifications()

  return (
    <div className="toast-container">
      {notifications.map((notification) => (
        <Toast 
          key={notification.id} 
          notification={notification} 
        />
      ))}
    </div>
  )
}

export default ToastContainer
