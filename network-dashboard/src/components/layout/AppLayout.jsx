import React, { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Navbar from './Navbar'
import './AppLayout.css'

const AppLayout = () => {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="app-layout">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
      />
      <Navbar collapsed={collapsed} />
      <main
        className="app-layout__main"
        style={{
          marginLeft: collapsed
            ? 'var(--sidebar-collapsed-width)'
            : 'var(--sidebar-width)',
        }}
      >
        <div className="app-layout__content">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default AppLayout