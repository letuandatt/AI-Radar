import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // No VITE_* or other environment variables are injected into browser code.
  envPrefix: [],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    allowedHosts: ['localhost'],
    fs: {
      strict: true,
      allow: [fileURLToPath(new URL('.', import.meta.url))],
    },
    proxy: {
      '/api/': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    maxWorkers: 1,
  },
});