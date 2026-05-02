import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const matchPkg = (id, pkg) =>
  id.includes(`/node_modules/${pkg}/`) || id.includes(`\\node_modules\\${pkg}\\`)

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': path.resolve(process.cwd(), './src'),
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (
            matchPkg(id, 'react') ||
            matchPkg(id, 'react-dom') ||
            matchPkg(id, 'react-router-dom')
          ) return 'vendor'

          if (matchPkg(id, 'recharts')) return 'charts'
          if (matchPkg(id, 'd3')) return 'd3'
          if (matchPkg(id, 'axios') || matchPkg(id, 'dayjs')) return 'utils'
        },
      },
    },
  },

  server: {
    port: 3000,
    proxy: {
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/auth/, '/api/v1/auth'),
      },
      '/api/v1': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})