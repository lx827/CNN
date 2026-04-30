import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',  // 加这行
  server: {
    port: 3000,
    open: true
  }
})
