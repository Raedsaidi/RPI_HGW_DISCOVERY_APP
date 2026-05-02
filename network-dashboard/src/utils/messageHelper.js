/**
 * Utility to translate technical messages into user-friendly messages
 */

// Translation of technical error messages to user-friendly messages
export const translateError = (technicalMessage) => {
  const errorMap = {
    // Connection errors
    'Connection timeout': 'Unable to connect to server',
    'SSH failed': 'SSH connection failed',
    'Authentication failed': 'Invalid credentials',
    'Permission denied': 'Access denied',
    'Network unreachable': 'Network unreachable',
    'Invalid credentials': 'Invalid credentials',
    'Login failed': 'Login failed',
    'Server error': 'Server error, please try again',
    'Connection refused': 'Connection refused by server',
    'Host key verification failed': 'Host key verification failed',
    
    // HTTP errors
    '401 Unauthorized': 'Unauthorized - check your credentials',
    '403 Forbidden': 'Access forbidden',
    '404 Not Found': 'Resource not found',
    '500 Internal Server Error': 'Internal server error',
    '502 Bad Gateway': 'Server unavailable',
    '503 Service Unavailable': 'Service temporarily unavailable',
    '504 Gateway Timeout': 'Gateway timeout',
    
    // Database errors
    'Database connection failed': 'Database connection failed',
    'Duplicate entry': 'Duplicate entry detected',
    'Foreign key constraint': 'Foreign key constraint violated',
    'Table doesn\'t exist': 'Table does not exist',
    
    // Domain-specific errors
    'Switch not responding': 'Switch is not responding',
    'RPi unreachable': 'Raspberry Pi is unreachable',
    'HGW connection failed': 'Gateway connection failed',
    'Discovery timeout': 'Network discovery timeout',
    'MAC address not found': 'MAC address not found',
    'DHCP lease expired': 'DHCP lease expired',
  }
  
  // Exact match then partial match
  if (errorMap[technicalMessage]) {
    return errorMap[technicalMessage]
  }
  
  // Search in messages (case insensitive)
  for (const [key, value] of Object.entries(errorMap)) {
    if (technicalMessage.toLowerCase().includes(key.toLowerCase())) {
      return value
    }
  }
  
  // Default message if no translation found
  return technicalMessage
}

// Translation of technical success messages to user-friendly messages
export const translateSuccess = (technicalMessage) => {
  const successMap = {
    'Created': 'Created successfully',
    'Updated': 'Updated successfully',
    'Deleted': 'Deleted successfully',
    'Login successful': 'Login successful',
    'Discovery started': 'Discovery started',
    'Credentials updated': 'Credentials updated',
    'Switch added': 'Switch added successfully',
    'Switch updated': 'Switch updated successfully',
    'Switch deleted': 'Switch deleted successfully',
    'User created': 'User created successfully',
    'User updated': 'User updated successfully',
    'User deleted': 'User deleted successfully',
    'RPi credentials updated': 'RPi credentials updated',
    'Topology loaded': 'Topology loaded successfully',
  }
  
  return successMap[technicalMessage] || technicalMessage
}

// Function to get appropriate friendly message based on type
export const getFriendlyMessage = (type, technicalMessage) => {
  switch (type) {
    case 'error':
      return translateError(technicalMessage)
    case 'success':
      return translateSuccess(technicalMessage)
    case 'info':
    case 'warning':
      return technicalMessage
    default:
      return technicalMessage
  }
}

// Function to format durations in a user-friendly way
export const formatDuration = (milliseconds) => {
  if (!milliseconds || milliseconds < 1000) {
    return 'a few moments'
  }
  
  const seconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  } else {
    return `${seconds}s`
  }
}

// Function to format file sizes
export const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return '0 bytes'
  
  const k = 1024
  const sizes = ['bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Function to validate data formats
export const validateEmail = (email) => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailRegex.test(email)
}

export const validatePassword = (password) => {
  return password && password.length >= 8
}

export const validateRequired = (value) => {
  return value !== null && value !== undefined && value.toString().trim() !== ''
}

// Function to generate unique IDs
export const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

export default {
  translateError,
  translateSuccess,
  getFriendlyMessage,
  formatDuration,
  formatFileSize,
  validateEmail,
  validatePassword,
  validateRequired,
  generateId,
}
