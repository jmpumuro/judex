import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/v1/sse': {
        target: 'http://localhost:8012',
        changeOrigin: true,
        // SSE specific settings
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            // Disable buffering for SSE
            proxyReq.setHeader('X-Accel-Buffering', 'no')
          })
        },
      },
      '/v1': {
        target: 'http://localhost:8012',
        changeOrigin: true,
        timeout: 300000, // 5 minute timeout for long processing
      },
      '/ws': {
        target: 'ws://localhost:8012',
        ws: true,
      },
    },
  },
})
