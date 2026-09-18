import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

export default defineConfig(() => ({
  // Router basename. Standalone single-app serves at '/'. Override VITE_BASE_URL
  // for a portal sub-path deploy (e.g. /apps/fimeval-gui/).
  base: process.env.VITE_BASE_URL || '/',

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
      '/apps': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}));
