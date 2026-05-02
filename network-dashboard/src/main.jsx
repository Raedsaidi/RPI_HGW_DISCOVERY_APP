import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/global.css'
    console.log('VITE_DISCOVERY_URL =', import.meta.env.VITE_DISCOVERY_URL)
    console.log('VITE_AUTH_URL =', import.meta.env.VITE_AUTH_URL)
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)