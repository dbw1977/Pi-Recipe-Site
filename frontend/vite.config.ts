import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The React app is built to ./dist and served by FastAPI as static files. During dev,
// `npm run dev` proxies /api to the FastAPI server on :8000 so both run side by side.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 for LAN testing during dev
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    // Keep the bundle light for the Pi 4.
    chunkSizeWarningLimit: 700,
  },
});
