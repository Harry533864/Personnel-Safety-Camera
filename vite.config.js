import { fileURLToPath, URL } from 'url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },

  // 新增 server 配置，适配 Docker 开发环境
  server: {
    watch: {
      usePolling: true,
      // interval: 100,
    },
    host: true,
    port: 5173,
  }
})
