import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: './',
  // the read-only snapshot build was dropped (2026-10-21); STATIC is always false
  define: { __STATIC__: 'false' },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000', '/geo': 'http://127.0.0.1:8000' },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 4000,
    rollupOptions: { output: { manualChunks: { deck: ['@deck.gl/core', '@deck.gl/layers', '@deck.gl/react', '@deck.gl/mapbox'], maplibre: ['maplibre-gl'], echarts: ['echarts'], cyto: ['cytoscape'] } } },
  },
}))
