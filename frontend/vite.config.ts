import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { loadEnv } from 'vite';

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api/': { target: loadEnv(mode, '.', 'TALAP_').TALAP_DEV_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: false } } },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], clearMocks: true },
}));
