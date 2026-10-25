import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [react()],
    // A relative base works both behind Nginx's /test prefix and when the
    // isolated Test API is opened directly at http://127.0.0.1:8110/.
    base: env.VITE_BASE_PATH || './',
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
