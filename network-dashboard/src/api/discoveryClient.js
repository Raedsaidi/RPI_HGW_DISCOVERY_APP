import axios from 'axios'

const discoveryClient = axios.create({
  baseURL: `${import.meta.env.VITE_DISCOVERY_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

discoveryClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('nd_access_token')

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

discoveryClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config

    if (error.response?.status === 401 && !original._retry) {
      original._retry = true

      const refreshToken = localStorage.getItem('nd_refresh_token')

      if (refreshToken) {
        try {
          const { data } = await axios.post(
            `${import.meta.env.VITE_AUTH_URL}/api/v1/auth/refresh`,
            { refresh_token: refreshToken }
          )

          localStorage.setItem('nd_access_token', data.access_token)
          localStorage.setItem('nd_refresh_token', data.refresh_token)

          original.headers.Authorization = `Bearer ${data.access_token}`

          return discoveryClient(original)
        } catch {
          localStorage.clear()
          window.location.href = '/login'
        }
      } else {
        localStorage.clear()
        window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  }
)

export default discoveryClient