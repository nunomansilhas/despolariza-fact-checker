import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3067,
    proxy: {
      '/api': 'http://localhost:3068',
      '/ws': {
        target: 'ws://localhost:3068',
        ws: true,
      },
    },
  },
})
