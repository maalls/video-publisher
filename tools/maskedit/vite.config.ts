import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Single-file bundle (web/app.js) served by server.py; relative URLs so it works under any path prefix.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': '"production"' },
  build: { outDir: 'web', emptyOutDir: false, lib: { entry: 'src/main.tsx', formats: ['iife'], name: 'maskedit', fileName: () => 'app.js' } },
})
