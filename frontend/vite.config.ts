import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const basePath = (env.VITE_BASE_PATH || '').trim().replace(/^\/+|\/+$/g, '')
  return {
    plugins: [react()],
    base: basePath ? `/${basePath}/` : '/',
    server: {
      port: Number(env.VITE_PORT || 5173),
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8010',
          changeOrigin: true,
        },
      },
    },
    build: { outDir: 'dist', emptyOutDir: true },
  }
})
