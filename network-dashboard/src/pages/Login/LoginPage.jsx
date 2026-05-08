import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Eye,
  EyeOff,
  Activity,
  AlertCircle,
  Search,
  BarChart3,
  GitBranch,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import {
  useNotifications,
  NOTIFICATION_MESSAGES,
} from '@/context/NotificationContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import { authApi } from '@/api/endpoints'
import './LoginPage.css'

const FEATURES = [
  {
    Icon: Search,
    label: 'Auto Discovery',
    desc: 'Scan and detect devices automatically',
  },
  {
    Icon: BarChart3,
    label: 'Real-time Monitoring',
    desc: 'Live metrics and status updates',
  },
  {
    Icon: GitBranch,
    label: 'Topology Mapping',
    desc: 'Visual network architecture',
  },
]

const LoginPage = () => {
  const navigate = useNavigate()
  const { login } = useAuth()
  const { notify } = useNotifications()

  const [form, setForm] = useState({ username: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    if (error) setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const username = form.username.trim()
    const password = form.password

    if (!username || !password) {
      setError('Please enter your username and password.')
      return
    }

    setLoading(true)
    setError('')

    try {
      // 1) login -> tokens
      const res = await authApi.login(username, password)
      const tokens = res.data

      if (!tokens?.access_token) {
        throw new Error('Login failed: missing access token')
      }

      // 2) me -> userData (contains project_hgws)
      const meResponse = await fetch('/api/v1/auth/me', {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${tokens.access_token}`,
          'Content-Type': 'application/json',
        },
      })

      if (!meResponse.ok) {
        throw new Error(`Get user failed: ${meResponse.status}`)
      }

      const userData = await meResponse.json()

      // 3) store everything via AuthContext (localStorage included there)
      login(tokens, userData)

      notify('success', NOTIFICATION_MESSAGES.SUCCESS.LOGIN_SUCCESS)
      navigate('/')
    } catch (err) {
      const technicalMessage =
        err?.response?.data?.detail || err?.message || 'Login failed'
      const friendlyMessage = getFriendlyMessage('error', technicalMessage)

      setError(friendlyMessage)
      notify('error', friendlyMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      {/* ── Left Panel ── */}
      <div className="login-page__left">
        <div className="login-page__left-content">
          <div className="login-page__brand">
            <div className="login-page__brand-icon">
              <Activity size={28} color="#1890ff" strokeWidth={2.5} />
            </div>
            <span className="login-page__brand-name">
              RPI & HGW Discovery APP
            </span>
          </div>

          <div className="login-page__hero">
            <h1 className="login-page__hero-title">
              Network Infrastructure
              <br />
              Management Platform
            </h1>
            <p className="login-page__hero-sub">
              Monitor, discover and manage your entire network infrastructure
              from a single unified dashboard.
            </p>
          </div>

          <div className="login-page__features">
            {FEATURES.map((f) => {
              const Icon = f.Icon
              return (
                <div key={f.label} className="login-page__feature">
                  <span className="login-page__feature-icon">
                    <Icon size={18} />
                  </span>
                  <div>
                    <div className="login-page__feature-label">{f.label}</div>
                    <div className="login-page__feature-desc">{f.desc}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Right Panel ── */}
      <div className="login-page__right">
        <div className="login-page__form-wrap">
          <div className="login-page__form-header">
            <h2 className="login-page__form-title">Welcome back</h2>
            <p className="login-page__form-sub">
              Sign in to your account to continue
            </p>
          </div>

          {error && (
            <div className="login-page__error">
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          <form className="login-page__form" onSubmit={handleSubmit}>
            <div className="login-page__field">
              <label className="login-page__label">Username</label>
              <input
                className="login-page__input"
                type="text"
                name="username"
                value={form.username}
                onChange={handleChange}
                placeholder="Enter your username"
                autoComplete="username"
                autoFocus
                disabled={loading}
              />
            </div>

            <div className="login-page__field">
              <label className="login-page__label">Password</label>
              <div className="login-page__input-wrap">
                <input
                  className="login-page__input login-page__input--password"
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  disabled={loading}
                />
                <button
                  type="button"
                  className="login-page__eye"
                  onClick={() => setShowPassword((v) => !v)}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="login-page__submit"
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="login-page__submit-spinner" />
                  Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          <p className="login-page__footer">
            RPI & HGW Discovery , Monitoring and testing dashboard &copy;{' '}
            {new Date().getFullYear()}
          </p>
        </div>
      </div>
    </div>
  )
}

export default LoginPage