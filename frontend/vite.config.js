import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const authTarget = process.env.CHEMBRIDGE_AUTH_URL || 'http://localhost:8080'
const ragTarget = process.env.CHEMBRIDGE_RAG_URL || 'http://localhost:8001'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: Number(process.env.CHEMBRIDGE_FRONTEND_PORT || 5174),
    strictPort: true,
    proxy: {
      '/api': { target: authTarget, changeOrigin: true },
      '/rag-query': { target: ragTarget, changeOrigin: true },
      '/health': { target: ragTarget, changeOrigin: true },
    },
  },
})
