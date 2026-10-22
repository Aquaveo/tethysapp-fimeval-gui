import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

export default defineConfig(({ mode }) => ({
  // Tethys portal serves the app at /apps/fimeval-gui/; the standalone image
  // builds with VITE_BASE_URL=/. Dev serves at / and proxies to Django.
  base: process.env.VITE_BASE_URL || (mode === 'production' ? '/apps/fimeval-gui/' : '/'),
  plugins: [
    react(),
  ],

  build: {
    outDir: path.resolve(
      __dirname,
      '../tethysapp/fimeval_gui/public/frontend'
    ),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'main.js',
        chunkFileNames: 'chunks/[name].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.css')) {
            return 'main.css';
          }
          return 'assets/[name][extname]';
        },
      },
    },
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },

  server: {
    proxy: {
      // API_BASE is /api in dev; Django serves it under the app path.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => `/apps/fimeval-gui${p}`,
      },
      '/apps': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}));
