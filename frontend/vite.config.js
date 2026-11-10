import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001', // 用 IPv4，避免 localhost 解析到 ::1 导致 ECONNRESET
        changeOrigin: true,
      },
    },
  },
})
