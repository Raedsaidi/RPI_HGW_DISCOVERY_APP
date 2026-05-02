// src/App.jsx
import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import { NotificationProvider } from '@/context/NotificationContext'
import AppLayout from '@/components/layout/AppLayout'
import ToastContainer from '@/components/common/ToastContainer'

import LoginPage from '@/pages/Login/LoginPage'
import OverviewPage from '@/pages/Overview/OverviewPage'
import SwitchesPage from '@/pages/Switches/SwitchesPage'
import RPisPage from '@/pages/RPis/RPisPage'
import HGWsPage from '@/pages/HGWs/HGWsPage'
import DiscoveryPage from '@/pages/Discovery/DiscoveryPage'
import TopologyPage from '@/pages/Topology/TopologyPage'
import UsersPage from '@/pages/Users/UsersPage'

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

const PublicRoute = ({ children }) => {
  const { isAuthenticated } = useAuth()
  return !isAuthenticated ? children : <Navigate to="/" replace />
}

const AppRoutes = () => {
  return (
    <Routes>
      {/* Route publique */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        }
      />

      {/* ✅ Routes protégées avec AppLayout comme parent */}
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />  {/* Outlet sera rempli par les enfants */}
          </ProtectedRoute>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/switches" element={<SwitchesPage />} />
        <Route path="/rpis" element={<RPisPage />} />
        <Route path="/hgws" element={<HGWsPage />} />
        <Route path="/discovery" element={<DiscoveryPage />} />
        <Route path="/topology" element={<TopologyPage />} />
        <Route path="/users" element={<UsersPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

const App = () => {
  return (
    <NotificationProvider>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
      <ToastContainer />
    </NotificationProvider>
  )
}

export default App