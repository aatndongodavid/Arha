import tailwind from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.ARHA_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwind()],
  server: { proxy: { "/v1": api, "/files": api } },
  preview: { proxy: { "/v1": api, "/files": api } },
  build: { target: "es2020" },
});
