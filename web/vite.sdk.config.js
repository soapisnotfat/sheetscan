import { defineConfig } from 'vite'
import base from './vite.config.js'

export default defineConfig({
  ...base,
  build: {
    outDir: 'dist-sdk',
    lib: { entry: 'src/converter.js', formats: ['es'], fileName: 'sheetscan' },
  },
})
