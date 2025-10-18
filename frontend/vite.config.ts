import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const frontendPort = Number(process.env.VITE_FRONTEND_PORT ?? process.env.FRONTEND_PORT ?? '3021')
const backendHost = process.env.VITE_BACKEND_HOST ?? 'localhost'
const backendPort = Number(process.env.VITE_BACKEND_PORT ?? process.env.BACKEND_PORT ?? '8021')
const apiTarget = process.env.VITE_API_BASE_URL ?? `http://${backendHost}:${backendPort}`

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: frontendPort,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
