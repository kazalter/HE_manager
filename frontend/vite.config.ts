import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('artplayer')) {
              return 'artplayer'
            }
            if (
              id.includes('@esotericsoftware/spine-player') ||
              id.includes('@esotericsoftware/spine-core') ||
              id.includes('@esotericsoftware/spine-webgl')
            ) {
              return 'spine-player'
            }
            if (id.includes('lucide-vue-next')) {
              return 'lucide-icons'
            }
            if (id.includes('vue') || id.includes('vue-router') || id.includes('axios')) {
              return 'vendor-core'
            }
            return 'vendor-others'
          }
        }
      }
    },
    chunkSizeWarningLimit: 800
  }
})
