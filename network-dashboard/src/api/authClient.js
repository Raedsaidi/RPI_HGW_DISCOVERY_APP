import axios from 'axios'

const authClient = axios.create({
  baseURL: `${import.meta.env.VITE_AUTH_URL}/api/v1/auth/`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 10000,
})

authClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('nd_access_token')

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

authClient.interceptors.response.use(
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

          return authClient(original)
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

export default authClient