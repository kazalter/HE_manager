import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const buildId = process.env.HE_BUILD_ID || new Date().toISOString()
const projectDir = fileURLToPath(new URL('.', import.meta.url))
function sourceInfo() {
  try {
    const git = (...args: string[]) => execFileSync('git', ['-C', projectDir, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
    const revision = git('rev-parse', 'HEAD')
    if (!/^[0-9a-f]{40}$/i.test(revision)) throw new Error('invalid revision')
    return { revision, dirty: Boolean(git('status', '--porcelain', '--untracked-files=no')) }
  } catch { return { revision: null, dirty: null } }
}
const source = sourceInfo()
const buildInfo = { buildId, sourceRevision: source.revision, sourceDirty: source.dirty }

export default defineConfig({
  define: { 'import.meta.env.HE_BUILD_ID': JSON.stringify(buildId), 'import.meta.env.HE_SOURCE_REVISION': JSON.stringify(source.revision), 'import.meta.env.HE_SOURCE_DIRTY': JSON.stringify(source.dirty) },
  plugins: [
    vue(),
    tailwindcss(),
    {
      name: 'he-build-version',
      generateBundle() { this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify(buildInfo) }) },
    },
  ],
  build: {
    emptyOutDir: true,
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
