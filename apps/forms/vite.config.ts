import preact from "@preact/preset-vite";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// The API origin comes from configuration, never from code (domains are not hard coded).
const api = process.env.ARHA_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [
    preact(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: null,
      manifest: {
        name: "Arha", short_name: "Arha", display: "standalone", start_url: "/",
        background_color: "#FCF9F4", theme_color: "#C9621B", icons: [],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/v1\//, /^\/files\//],
        globPatterns: ["**/*.{js,css,html}"],
        runtimeCaching: [
          { // Published form version: stale-while-revalidate (master prompt section 10)
            urlPattern: ({ url }) => /^\/v1\/public\/forms\/[^/]+$/.test(url.pathname),
            handler: "StaleWhileRevalidate",
            options: { cacheName: "arha-forms", expiration: { maxEntries: 30, maxAgeSeconds: 30 * 86400 } },
          },
        ],
      },
    }),
  ],
  server: { proxy: { "/v1": api, "/files": api } },
  preview: { proxy: { "/v1": api, "/files": api } },
  build: { target: "es2020", cssCodeSplit: false, modulePreload: { polyfill: false } },
});
