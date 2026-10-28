import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Derleme backend'in sunduğu {KYS_BASE_PATH}/app/ altından yüklenir (api/app.py: _add_web_routes).
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/qa/app/' : '/',
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/qa/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/qa/mcp': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
}));
