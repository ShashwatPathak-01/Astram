import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks to the FastAPI backend. In dev we proxy /api -> :8000
// so the browser sees same-origin requests (no CORS surprises).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
