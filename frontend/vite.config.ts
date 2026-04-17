import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon-192.png', 'icons/icon-512.png'],
      manifest: false, // we use our own /public/manifest.json
      workbox: {
        // Only precache small files — skip large vendor chunks to avoid OOM on CI
        globPatterns: ['**/*.{html,css,ico,png,woff2}'],
        maximumFileSizeToCacheInBytes: 500 * 1024, // 500 KB cap
        cleanupOutdatedCaches: true,
        skipWaiting: true,
        clientsClaim: true,
        importScripts: ['/push-sw.js'],
        // Don't fall back to index.html for hashed asset 404s — let them
        // fail so the user gets a real error instead of a JS-as-HTML mess.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/assets\//, /^\/icons\//, /\.(js|css|map|json|svg|png|ico|woff2)$/],
        runtimeCaching: [
          {
            urlPattern: /^\/api\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 3600,
              },
              networkTimeoutSeconds: 10,
            },
          },
          {
            // Always go to network for hashed JS/CSS so a stale SW never
            // serves yesterday's chunk reference.
            urlPattern: /\/assets\/.*\.(js|css)$/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'asset-cache',
              networkTimeoutSeconds: 5,
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 3001,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Keep prior hashed chunks so users with stale cached HTML can still
    // resolve dynamic imports during rollout windows.
    emptyOutDir: false,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-charts': ['recharts'],
        },
      },
    },
  },
})
