import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5688', changeOrigin: true },
      '/stream': { target: 'http://127.0.0.1:5688', changeOrigin: true }
    }
  },
  build: {
    outDir: '../ui/static/dist',
    emptyOutDir: true
  }
})
