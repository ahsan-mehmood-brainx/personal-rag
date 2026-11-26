/**
 * Vite config: dev server, preview server, and Vitest.
 *
 * The browser only ever talks to this server's origin. Requests under `/api` are proxied to
 * the FastAPI backend, so the backend needs no CORS configuration and stays bound to
 * 127.0.0.1. The proxy target comes from `API_PROXY_TARGET` (read from the environment or
 * `web/.env*`), never from code.
 */
import type { ServerResponse } from 'node:http'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ProxyOptions } from 'vite'

const DEFAULT_PROXY_TARGET = 'http://127.0.0.1:8000'

function apiProxy(target: string): Record<string, ProxyOptions> {
  return {
    '/api': {
      target,
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
      configure: (proxy) => {
        // Without this, an unreachable backend surfaces as an empty 500 the UI cannot explain.
        proxy.on('error', (_err, _req, res) => {
          const response = res as ServerResponse
          if (response.headersSent || typeof response.writeHead !== 'function') return
          response.writeHead(503, { 'Content-Type': 'application/json', 'X-Proxy-Error': '1' })
          response.end(JSON.stringify({ detail: 'The backend API is not reachable.' }))
        })
      },
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.API_PROXY_TARGET || DEFAULT_PROXY_TARGET
  return {
    plugins: [react()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: apiProxy(target) },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy: apiProxy(target) },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      css: { modules: { classNameStrategy: 'non-scoped' } },
      restoreMocks: true,
    },
  }
})
