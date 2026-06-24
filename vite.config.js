import { fileURLToPath, URL } from 'url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const serveRootIndex = () => ({
  name: 'serve-root-index',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (req.url === '/' || req.url?.startsWith('/?')) {
        req.url = '/index.html'
      }
      next()
    })
  }
})

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [serveRootIndex(), vue()],
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
