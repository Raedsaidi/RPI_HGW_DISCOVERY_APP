// Navbar.jsx
import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, LogOut } from 'lucide-react'
import dayjs from 'dayjs'
import { useAuth } from '@/context/AuthContext'
import { authApi } from '@/api/endpoints'
import './Navbar.css'

const ROLE_LABELS = {
  SUPER_ADMIN: { label: 'Super Admin', color: '#f5222d' },
  ADMIN: { label: 'Admin', color: '#722ed1' },
  PROJECT_MANAGER: { label: 'Project Manager', color: '#1890ff' },
  USER: { label: 'User', color: '#52c41a' },
}

const Navbar = ({ collapsed }) => {
  const { user, logout, getRefreshToken } = useAuth()
  const navigate = useNavigate()

  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef(null)

  const roleInfo = ROLE_LABELS[user?.role] || ROLE_LABELS.USER

  // ── Close dropdown on outside click ──
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleLogout = async () => {
    try {
      const rt = getRefreshToken()
      if (rt) await authApi.logout(rt)
    } catch {
      // silent
    } finally {
      logout()
      navigate('/login')
    }
  }

  const initials = user?.full_name
    ? user.full_name
        .split(' ')
        .map((w) => w[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : user?.username?.slice(0, 2).toUpperCase() || 'U'

  // ── Extra user info ──
  const lastLoginAt = user?.last_login_at || null
  const createdAt = user?.created_at || null
  const isActive = user?.is_active

  // “connecté depuis” (timestamp local, à set dans AuthContext lors du login)
  const loginAtRaw = localStorage.getItem('nd_login_at')
  const connectedSince = loginAtRaw ? dayjs(Number(loginAtRaw)) : null

  return (
    <header
      className="navbar"
      style={{
        left: collapsed
          ? 'var(--sidebar-collapsed-width)'
          : 'var(--sidebar-width)',
      }}
    >
      {/* ── Left ── */}
      <div className="navbar__left">
        <div className="navbar__breadcrumb">
          <span className="navbar__breadcrumb-app">Network Dashboard</span>
        </div>
      </div>

      {/* ── Right ── */}
      <div className="navbar__right">
        <div className="navbar__separator" />

        {/* User dropdown */}
        <div className="navbar__user" ref={dropdownRef}>
          <button
            className="navbar__user-btn"
            onClick={() => setDropdownOpen((o) => !o)}
          >
            <div className="navbar__avatar">{initials}</div>

            <div className="navbar__user-info">
              <span className="navbar__user-name">
                {user?.full_name || user?.username}
              </span>
              <span
                className="navbar__user-role"
                style={{ color: roleInfo.color }}
              >
                {roleInfo.label}
              </span>
            </div>

            <ChevronDown
              size={14}
              className={`navbar__chevron ${
                dropdownOpen ? 'navbar__chevron--open' : ''
              }`}
            />
          </button>

          {dropdownOpen && (
            <div className="navbar__dropdown">
              <div className="navbar__dropdown-header">
                <div className="navbar__avatar navbar__avatar--lg">
                  {initials}
                </div>
                <div>
                  <div className="navbar__dropdown-name">
                    {user?.full_name || user?.username}
                  </div>
                  <div className="navbar__dropdown-email">{user?.email}</div>
                </div>
              </div>

              <div className="navbar__dropdown-divider" />

              {/* ── Added: User info section ── */}
              <div className="navbar__dropdown-section">
                <div className="navbar__dropdown-section-title">User info</div>

                <div className="navbar__dropdown-row">
                  <span>Username</span>
                  <span>{user?.username || '—'}</span>
                </div>

                <div className="navbar__dropdown-row">
                  <span>Account</span>
                  <span
                    className={`navbar__status ${
                      isActive ? 'navbar__status--online' : 'navbar__status--offline'
                    }`}
                  >
                    {isActive ? 'Active' : 'Disabled'}
                  </span>
                </div>

                <div className="navbar__dropdown-row">
                  <span>Created</span>
                  <span>
                    {createdAt ? dayjs(createdAt).format('MMM D, YYYY HH:mm') : '—'}
                  </span>
                </div>

                <div className="navbar__dropdown-row">
                  <span>Last login</span>
                  <span>
                    {lastLoginAt
                      ? dayjs(lastLoginAt).format('MMM D, YYYY HH:mm')
                      : '—'}
                  </span>
                </div>

                <div className="navbar__dropdown-row">
                  <span>Connected since</span>
                  <span>
                    {connectedSince
                      ? connectedSince.format('MMM D, YYYY HH:mm')
                      : '—'}
                  </span>
                </div>
              </div>

              <div className="navbar__dropdown-divider" />

              <button
                className="navbar__dropdown-item navbar__dropdown-item--danger"
                onClick={handleLogout}
              >
                <LogOut size={15} />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

export default Navbar