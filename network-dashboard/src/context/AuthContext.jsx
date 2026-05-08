import React, { createContext, useContext, useState, useCallback } from 'react'

const AuthContext = createContext(null)

const TOKEN_KEY = 'nd_access_token'
const REFRESH_KEY = 'nd_refresh_token'
const USER_KEY = 'nd_user'
const LOGIN_AT_KEY = 'nd_login_at'

const normalizeUser = (u) => {
  if (!u || typeof u !== 'object') return u
  return {
    ...u,
    project_hgws: Array.isArray(u.project_hgws) ? u.project_hgws : [],
  }
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem(USER_KEY)
      const parsed = raw ? JSON.parse(raw) : null
      return normalizeUser(parsed)
    } catch {
      return null
    }
  })

  const [accessToken, setAccessToken] = useState(
    () => localStorage.getItem(TOKEN_KEY) || null
  )

  const login = useCallback((tokens, userData) => {
    const normalized = normalizeUser(userData)

    localStorage.setItem(TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
    localStorage.setItem(USER_KEY, JSON.stringify(normalized))
    localStorage.setItem(LOGIN_AT_KEY, String(Date.now()))

    setAccessToken(tokens.access_token)
    setUser(normalized)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(LOGIN_AT_KEY)

    setAccessToken(null)
    setUser(null)
  }, [])

  const getRefreshToken = useCallback(
    () => localStorage.getItem(REFRESH_KEY),
    []
  )

  const isAuthenticated = !!accessToken && !!user

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated,
        login,
        logout,
        getRefreshToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}