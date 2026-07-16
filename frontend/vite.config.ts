import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "icons/*.png"],
      manifest: {
        name: "DOMOVINA Stranke — Hrvatske političke stranke",
        short_name: "Stranke",
        description:
          "Katalog svih hrvatskih političkih stranaka iz Registra — kontakti, dužnosnici, karta. Otvoreni podaci.",
        lang: "hr",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#FFFFFF",
        theme_color: "#002F6C",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,ico}"],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/data\//],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/data/"),
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "stranke-data-v1",
              expiration: { maxEntries: 1200, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: ({ url }) => url.origin === "https://p.ff.hr",
            handler: "CacheFirst",
            options: {
              cacheName: "stranke-logos-v1",
              expiration: { maxEntries: 1500, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: /^https:\/\/[abc]\.basemaps\.cartocdn\.com\/.+/,
            handler: "CacheFirst",
            options: {
              cacheName: "stranke-tiles-v1",
              expiration: { maxEntries: 800, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: { port: 5173 },
  build: { sourcemap: true, target: "es2020" },
});
