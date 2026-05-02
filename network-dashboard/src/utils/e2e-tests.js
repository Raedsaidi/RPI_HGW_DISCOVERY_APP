/* ─────────────────────────────────────────
   E2E Tests for Notification System
──────────────────────────────────────── */

/* ── Test Configuration ── */
const TEST_CONFIG = {
  timeout: 5000,
  retryAttempts: 3,
  testUser: {
    username: 'testuser@example.com',
    password: 'TestPassword123!'
  }
}

/* ── Test Helpers ── */
const waitForElement = (selector, timeout = TEST_CONFIG.timeout) => {
  return new Promise((resolve, reject) => {
    const element = document.querySelector(selector)
    if (element) {
      resolve(element)
      return
    }
    
    const observer = new MutationObserver(() => {
      const element = document.querySelector(selector)
      if (element) {
        observer.disconnect()
        resolve(element)
      }
    })
    
    observer.observe(document.body, {
      childList: true,
      subtree: true
    })
    
    setTimeout(() => {
      observer.disconnect()
      reject(new Error(`Element ${selector} not found within ${timeout}ms`))
    }, timeout)
  })
}

const simulateClick = (element) => {
  element.click()
  return new Promise(resolve => {
    setTimeout(resolve, 100)
  })
}

const simulateInput = (element, value) => {
  element.value = value
  element.dispatchEvent(new Event('input', { bubbles: true }))
  return new Promise(resolve => {
    setTimeout(resolve, 100)
  })
}

const checkToastExists = (message, type = 'success') => {
  const toastSelector = `.toast--${type}`
  const toasts = document.querySelectorAll(toastSelector)
  return Array.from(toasts).some(toast => 
    toast.textContent.includes(message) || 
    toast.querySelector('.toast__message')?.textContent.includes(message)
  )
}

const checkLoadingState = (element) => {
  return element.hasAttribute('disabled') || 
         element.classList.contains('loading') ||
         element.querySelector('.spinner') !== null
}

/* ── Test Suite ── */
class E2ETestSuite {
  constructor() {
    this.tests = []
    this.results = []
  }

  addTest(name, testFn) {
    this.tests.push({ name, testFn })
  }

  async runTests() {
    console.log('🧪 Starting E2E Test Suite...')
    
    for (const test of this.tests) {
      try {
        console.log(`⚡ Running: ${test.name}`)
        const startTime = performance.now()
        
        await test.testFn()
        
        const endTime = performance.now()
        const duration = endTime - startTime
        
        this.results.push({
          name: test.name,
          status: 'passed',
          duration: duration.toFixed(2)
        })
        
        console.log(`✅ Passed: ${test.name} (${duration.toFixed(2)}ms)`)
      } catch (error) {
        this.results.push({
          name: test.name,
          status: 'failed',
          error: error.message,
          duration: 0
        })
        
        console.error(`❌ Failed: ${test.name} - ${error.message}`)
      }
    }
    
    this.printResults()
  }

  printResults() {
    const passed = this.results.filter(r => r.status === 'passed').length
    const failed = this.results.filter(r => r.status === 'failed').length
    const total = this.results.length
    
    console.log('\n📊 Test Results:')
    console.log(`Total: ${total}`)
    console.log(`Passed: ${passed}`)
    console.log(`Failed: ${failed}`)
    console.log(`Success Rate: ${((passed / total) * 100).toFixed(1)}%`)
    
    if (failed > 0) {
      console.log('\n❌ Failed Tests:')
      this.results
        .filter(r => r.status === 'failed')
        .forEach(r => console.log(`  • ${r.name}: ${r.error}`))
    }
    
    return { passed, failed, total, successRate: (passed / total) * 100 }
  }
}

/* ── Notification Tests ── */
const testNotificationDisplay = async () => {
  console.log('🔔 Testing notification display...')
  
  // Trigger a success notification
  window.dispatchEvent(new CustomEvent('showNotification', {
    detail: { type: 'success', message: 'Test success notification' }
  }))
  
  // Wait for notification to appear
  await waitForElement('.toast--success', 2000)
  
  // Check if notification exists
  const exists = checkToastExists('Test success notification', 'success')
  if (!exists) {
    throw new Error('Success notification not displayed')
  }
  
  console.log('✅ Success notification displayed correctly')
}

const testNotificationAutoDismiss = async () => {
  console.log('⏰ Testing notification auto-dismiss...')
  
  // Trigger notification
  window.dispatchEvent(new CustomEvent('showNotification', {
    detail: { type: 'info', message: 'Test auto-dismiss' }
  }))
  
  // Wait for notification to appear
  await waitForElement('.toast--info', 2000)
  
  // Wait for auto-dismiss (should disappear after 5 seconds)
  await new Promise(resolve => setTimeout(resolve, 6000))
  
  // Check if notification is gone
  const exists = checkToastExists('Test auto-dismiss', 'info')
  if (exists) {
    throw new Error('Notification did not auto-dismiss')
  }
  
  console.log('✅ Notification auto-dismissed correctly')
}

const testNotificationManualDismiss = async () => {
  console.log('👆 Testing notification manual dismiss...')
  
  // Trigger notification
  window.dispatchEvent(new CustomEvent('showNotification', {
    detail: { type: 'warning', message: 'Test manual dismiss' }
  }))
  
  // Wait for notification to appear
  const toast = await waitForElement('.toast--warning', 2000)
  
  // Find and click close button
  const closeButton = toast.querySelector('.toast__close')
  if (!closeButton) {
    throw new Error('Close button not found')
  }
  
  await simulateClick(closeButton)
  
  // Wait for animation to complete
  await new Promise(resolve => setTimeout(resolve, 300))
  
  // Check if notification is gone
  const exists = checkToastExists('Test manual dismiss', 'warning')
  if (exists) {
    throw new Error('Notification did not dismiss when clicked')
  }
  
  console.log('✅ Notification dismissed manually correctly')
}

/* ── Loading State Tests ── */
const testLoadingStates = async () => {
  console.log('⏳ Testing loading states...')
  
  // Test login button loading
  const loginButton = await waitForElement('button[type="submit"]', 2000)
  
  // Simulate form submission
  await simulateInput('input[name="username"]', TEST_CONFIG.testUser.username)
  await simulateInput('input[name="password"]', TEST_CONFIG.testUser.password)
  await simulateClick(loginButton)
  
  // Check if button shows loading state
  const isLoading = checkLoadingState(loginButton)
  if (!isLoading) {
    throw new Error('Login button did not show loading state')
  }
  
  console.log('✅ Loading state displayed correctly')
}

/* ── Error Handling Tests ── */
const testErrorHandling = async () => {
  console.log('🚨 Testing error handling...')
  
  // Trigger an error notification
  window.dispatchEvent(new CustomEvent('showNotification', {
    detail: { type: 'error', message: 'Test error message' }
  }))
  
  // Wait for error notification
  await waitForElement('.toast--error', 2000)
  
  // Check if error notification exists
  const exists = checkToastExists('Test error message', 'error')
  if (!exists) {
    throw new Error('Error notification not displayed')
  }
  
  console.log('✅ Error handling works correctly')
}

/* ── Performance Tests ── */
const testPerformance = async () => {
  console.log('⚡ Testing performance...')
  
  const startTime = performance.now()
  
  // Trigger multiple notifications rapidly
  for (let i = 0; i < 10; i++) {
    window.dispatchEvent(new CustomEvent('showNotification', {
      detail: { type: 'info', message: `Performance test ${i}` }
    }))
    await new Promise(resolve => setTimeout(resolve, 50))
  }
  
  const endTime = performance.now()
  const duration = endTime - startTime
  
  // Check if performance is acceptable (should be under 1000ms for 10 notifications)
  if (duration > 1000) {
    throw new Error(`Performance issue: ${duration.toFixed(2)}ms for 10 notifications`)
  }
  
  console.log(`✅ Performance test passed (${duration.toFixed(2)}ms)`)
}

/* ── Accessibility Tests ── */
const testAccessibility = async () => {
  console.log('♿ Testing accessibility...')
  
  // Trigger notification
  window.dispatchEvent(new CustomEvent('showNotification', {
    detail: { type: 'success', message: 'Accessibility test' }
  }))
  
  // Wait for notification
  const toast = await waitForElement('.toast', 2000)
  
  // Check for ARIA attributes
  const hasAriaLive = toast.hasAttribute('aria-live')
  const hasAriaAtomic = toast.hasAttribute('aria-atomic')
  const hasRole = toast.hasAttribute('role')
  
  if (!hasAriaLive || !hasAriaAtomic || !hasRole) {
    throw new Error('Missing ARIA attributes for accessibility')
  }
  
  console.log('✅ Accessibility test passed')
}

/* ── Integration Test ── */
const testFullIntegration = async () => {
  console.log('🔗 Testing full integration...')
  
  // Test complete user flow
  await testLoadingStates()
  await new Promise(resolve => setTimeout(resolve, 1000))
  await testNotificationDisplay()
  await new Promise(resolve => setTimeout(resolve, 1000))
  await testNotificationManualDismiss()
  
  console.log('✅ Full integration test passed')
}

/* ── Run Tests ── */
export const runE2ETests = async () => {
  const suite = new E2ETestSuite()
  
  // Add all tests
  suite.addTest('Notification Display', testNotificationDisplay)
  suite.addTest('Notification Auto-Dismiss', testNotificationAutoDismiss)
  suite.addTest('Notification Manual Dismiss', testNotificationManualDismiss)
  suite.addTest('Loading States', testLoadingStates)
  suite.addTest('Error Handling', testErrorHandling)
  suite.addTest('Performance', testPerformance)
  suite.addTest('Accessibility', testAccessibility)
  suite.addTest('Full Integration', testFullIntegration)
  
  // Run all tests
  await suite.runTests()
  
  return suite.results
}

/* ── Test Runner (for development) ── */
if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
  // Auto-run tests in development
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      console.log('🧪 Auto-running E2E tests in development...')
      runE2ETests()
    }, 2000)
  })
}

export { runE2ETests, E2ETestSuite }
