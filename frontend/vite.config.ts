import react from '@vitejs/plugin-react'
// vitest/config re-exports Vite's defineConfig with the `test` key typed.
import { defineConfig } from 'vitest/config'

// The backend only allows a fixed set of CORS origins (see backend CORS_ORIGINS).
// A browser request straight to http://localhost:8000 is therefore cross-origin
// and gets rejected whenever the page origin differs from that allowlist
// (127.0.0.1 vs localhost, a different dev port, or the preview port).
// Proxying /health and /api through the dev/preview server keeps the browser on a
// single origin, so those requests are same-origin and never hit CORS.
// https://vite.dev/config/
const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

const proxy = {
  '/health': { target: backendTarget, changeOrigin: true },
  '/api': { target: backendTarget, changeOrigin: true },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
