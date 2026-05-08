import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Network,
  Cpu,
  Wifi,
  Radio,
  GitBranch,
  Users,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import RpiLogo from '@/assets/raspberry-pi.svg'
import './Sidebar.css'

const NAV_ITEMS = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard, path: '/' },
  { key: 'switches', label: 'Switches', icon: Network, path: '/switches' },
  { key: 'rpis', label: 'Raspberry Pi', icon: Cpu, path: '/rpis' },
  { key: 'hgws', label: 'Gateways', icon: Wifi, path: '/hgws' },
  { key: 'discovery', label: 'Discovery', icon: Radio, path: '/discovery' },
  { key: 'topology', label: 'Topology', icon: GitBranch, path: '/topology' },
  { key: 'users', label: 'User Management', icon: Users, path: '/users' },
]

const Sidebar = ({ collapsed, onToggle }) => {
  const location = useLocation()
  const { user: currentUser } = useAuth()

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  // ✅ Hide "User Management" for USER and PROJECT_MANAGER
  const canManageUsers = ['ADMIN', 'SUPER_ADMIN'].includes(currentUser?.role)
  const navItems = canManageUsers
    ? NAV_ITEMS
    : NAV_ITEMS.filter((i) => i.key !== 'users')

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
      {/* ── Logo ── */}
      <div className="sidebar__logo">
        <div className="sidebar__logo-icon">
          <img
            src={RpiLogo}
            alt="Raspberry Pi"
            className="sidebar__logo-img"
          />
        </div>

        {!collapsed && (
          <div className="sidebar__logo-text">
            <span className="sidebar__logo-name">Discovery APP</span>
            <span className="sidebar__logo-version"></span>
          </div>
        )}
      </div>

      <div className="sidebar__divider" />

      {/* ── Navigation ── */}
      <nav className="sidebar__nav">
        {!collapsed && (
          <span className="sidebar__section-label">MAIN MENU</span>
        )}

        <ul className="sidebar__list">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = isActive(item.path)

            return (
              <li key={item.key} className="sidebar__item">
                <NavLink
                  to={item.path}
                  className={`sidebar__link ${active ? 'sidebar__link--active' : ''}`}
                  title={collapsed ? item.label : undefined}
                >
                  <span className="sidebar__link-icon">
                    <Icon size={18} strokeWidth={active ? 2.5 : 2} />
                  </span>

                  {!collapsed && (
                    <span className="sidebar__link-label">{item.label}</span>
                  )}

                  {active && !collapsed && (
                    <span className="sidebar__active-indicator" />
                  )}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="sidebar__divider" />

      {/* ── Collapse Toggle ── */}
      <button
        className="sidebar__collapse-btn"
        onClick={onToggle}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? (
          <ChevronRight size={16} />
        ) : (
          <>
            <ChevronLeft size={16} />
            <span>Collapse</span>
          </>
        )}
      </button>
    </aside>
  )
}

export default Sidebar