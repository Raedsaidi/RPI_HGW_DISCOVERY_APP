/* ─────────────────────────────────────────
   Performance Optimizations
──────────────────────────────────────── */

/* ── Memoization Helpers ── */
export const memoize = (fn) => {
  const cache = new Map()
  return (...args) => {
    const key = JSON.stringify(args)
    if (cache.has(key)) {
      return cache.get(key)
    }
    const result = fn(...args)
    cache.set(key, result)
    return result
  }
}

/* ── Debounce Helper ── */
export const debounce = (func, wait) => {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

/* ── Throttle Helper ── */
export const throttle = (func, limit) => {
  let inThrottle
  return function (...args) {
    if (!inThrottle) {
      func.apply(this, args)
      inThrottle = true
      setTimeout(() => (inThrottle = false), limit)
    }
  }
}

/* ── Virtual Scroll Helper ── */
export const createVirtualScroll = (items, itemHeight, containerHeight, scrollTop = 0) => {
  const visibleCount = Math.ceil(containerHeight / itemHeight) + 1
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - 5)
  const endIndex = Math.min(items.length, startIndex + visibleCount + 10)
  
  return {
    visibleItems: items.slice(startIndex, endIndex),
    startIndex,
    endIndex,
    totalHeight: items.length * itemHeight
  }
}

/* ── Image Lazy Loading ── */
export const lazyLoadImage = (src) => {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

/* ── Intersection Observer Helper ── */
export const createIntersectionObserver = (callback, options = {}) => {
  return new IntersectionObserver(callback, {
    root: null,
    rootMargin: '50px',
    threshold: 0.1,
    ...options
  })
}

/* ── Performance Monitoring ── */
export const measurePerformance = (name, fn) => {
  return async (...args) => {
    const start = performance.now()
    try {
      const result = await fn(...args)
      const end = performance.now()
      console.log(`⚡ ${name}: ${(end - start).toFixed(2)}ms`)
      return result
    } catch (error) {
      const end = performance.now()
      console.error(`❌ ${name}: ${(end - start).toFixed(2)}ms (error)`)
      throw error
    }
  }
}

/* ── Memory Management ── */
export const clearMemoryCache = () => {
  if (window.gc) {
    window.gc()
  }
}

/* ── Bundle Size Optimization ── */
export const preloadCriticalResources = (resources) => {
  resources.forEach(resource => {
    const link = document.createElement('link')
    link.rel = 'preload'
    link.href = resource
    if (resource.endsWith('.js')) {
      link.as = 'script'
    } else if (resource.endsWith('.css')) {
      link.as = 'style'
    }
    document.head.appendChild(link)
  })
}

/* ── Network Optimization ── */
export const optimizeNetworkRequests = () => {
  // Enable HTTP/2 server push simulation
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
  }
}

/* ── Render Optimization ── */
export const batchDOMUpdates = (updates) => {
  return new Promise(resolve => {
    requestAnimationFrame(() => {
      updates.forEach(update => update())
      resolve()
    })
  })
}

/* ── Cache Management ── */
const cache = new Map()

export const cacheResponse = (key, data, ttl = 300000) => { // 5 minutes default
  cache.set(key, {
    data,
    timestamp: Date.now(),
    ttl
  })
}

export const getCachedResponse = (key) => {
  const cached = cache.get(key)
  if (!cached) return null
  
  const now = Date.now()
  if (now - cached.timestamp > cached.ttl) {
    cache.delete(key)
    return null
  }
  
  return cached.data
}

export const clearExpiredCache = () => {
  const now = Date.now()
  for (const [key, value] of cache.entries()) {
    if (now - value.timestamp > value.ttl) {
      cache.delete(key)
    }
  }
}

/* ── Performance Metrics ── */
export const getPerformanceMetrics = () => {
  if (!performance.memory) {
    return null
  }
  
  return {
    usedJSHeapSize: performance.memory.usedJSHeapSize,
    totalJSHeapSize: performance.memory.totalJSHeapSize,
    jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
    memoryUsagePercent: (performance.memory.usedJSHeapSize / performance.memory.jsHeapSizeLimit) * 100
  }
}

/* ── Critical Resource Loading ── */
export const loadCriticalResources = async () => {
  const criticalResources = [
    '/src/components/common/Button.css',
    '/src/components/common/Spinner.css',
    '/src/components/common/Table.css'
  ]
  
  const promises = criticalResources.map(resource => {
    return new Promise((resolve) => {
      const link = document.createElement('link')
      link.rel = 'preload'
      link.href = resource
      link.as = 'style'
      link.onload = resolve
      document.head.appendChild(link)
    })
  })
  
  return Promise.all(promises)
}
