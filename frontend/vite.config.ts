/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backendUrl = process.env['CVIDEE_BACKEND_URL'] ?? 'http://localhost:8099';

export default defineConfig({
  // Relative asset URLs so the build also works behind Home Assistant ingress.
  base: './',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: backendUrl, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
});
