import React, { createContext, useContext, useReducer, useCallback } from 'react'

// Notification types
export const NOTIFICATION_TYPES = {
  SUCCESS: 'success',
  ERROR: 'error',
  WARNING: 'warning',
  INFO: 'info',
}

// Initial state
const initialState = {
  notifications: [],
}

// Actions
const ADD_NOTIFICATION = 'ADD_NOTIFICATION'
const REMOVE_NOTIFICATION = 'REMOVE_NOTIFICATION'
const CLEAR_NOTIFICATIONS = 'CLEAR_NOTIFICATIONS'

// Reducer
function notificationReducer(state, action) {
  switch (action.type) {
    case ADD_NOTIFICATION:
      return {
        ...state,
        notifications: [...state.notifications, action.payload],
      }
    
    case REMOVE_NOTIFICATION:
      return {
        ...state,
        notifications: state.notifications.filter(n => n.id !== action.payload),
      }
    
    case CLEAR_NOTIFICATIONS:
      return {
        ...state,
        notifications: [],
      }
    
    default:
      return state
  }
}

// Context
const NotificationContext = createContext({
  notifications: [],
  addNotification: () => {},
  removeNotification: () => {},
  clearNotifications: () => {},
})

// Provider
export const NotificationProvider = ({ children }) => {
  const [state, dispatch] = useReducer(notificationReducer, initialState)

  // Add notification
  const addNotification = useCallback((type, message, duration = 5000) => {
    const notification = {
      id: Date.now() + Math.random(),
      type,
      message,
      timestamp: new Date(),
    }
    
    dispatch({
      type: ADD_NOTIFICATION,
      payload: notification,
    })

    // Auto-dismiss after duration
    if (duration > 0) {
      setTimeout(() => {
        dispatch({
          type: REMOVE_NOTIFICATION,
          payload: notification.id,
        })
      }, duration)
    }
  }, [])

  // Remove notification
  const removeNotification = useCallback((id) => {
    dispatch({
      type: REMOVE_NOTIFICATION,
      payload: id,
    })
  }, [])

  // Clear all notifications
  const clearNotifications = useCallback(() => {
    dispatch({
      type: CLEAR_NOTIFICATIONS,
    })
  }, [])

const value = {
  notifications: state.notifications,
  notify: addNotification, // ✅ alias here
  addNotification,
  removeNotification,
  clearNotifications,
}

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  )
}

// Hook to use the context
export const useNotifications = () => {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider')
  }
  return context
}

// Alias for compatibility
export const useNotification = useNotifications

// Utility functions for friendly messages
export const NOTIFICATION_MESSAGES = {
  // Success messages
  SUCCESS: {
    CREATED: 'Created successfully',
    UPDATED: 'Updated successfully',
    DELETED: 'Deleted successfully',
    LOGIN_SUCCESS: 'Login successful',
    DISCOVERY_STARTED: 'Discovery started',
    CREDENTIALS_UPDATED: 'Credentials updated',
    SWITCH_ADDED: 'Switch added successfully',
    SWITCH_UPDATED: 'Switch updated successfully',
    SWITCH_DELETED: 'Switch deleted successfully',
  },
  
  // Error messages
  ERROR: {
    CONNECTION_TIMEOUT: 'Unable to connect to server',
    SSH_FAILED: 'SSH connection failed',
    AUTH_FAILED: 'Invalid credentials',
    PERMISSION_DENIED: 'Access denied',
    SERVER_ERROR: 'Server error, please try again',
    NETWORK_UNREACHABLE: 'Network unreachable',
    INVALID_CREDENTIALS: 'Invalid credentials',
    LOGIN_FAILED: 'Login failed',
    USER_NOT_FOUND: 'User not found',
    USER_ALREADY_EXISTS: 'User already exists',
    EMAIL_ALREADY_EXISTS: 'Email already exists',
    DELETE_FAILED: 'Delete failed',
    UPDATE_FAILED: 'Update failed',
    CREATE_FAILED: 'Create failed',
    DISCOVERY_FAILED: 'Discovery failed',
  },
  
  // Information messages
  INFO: {
    LOADING: 'Loading...',
    PROCESSING: 'Processing...',
    SAVING: 'Saving...',
    DELETING: 'Deleting...',
  },
}

export default NotificationContext
