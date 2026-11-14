import tailwind from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

// Public addresses come from the environment at build time (no domain in the code).
export default defineConfig({
  site: process.env.ARHA_SITE_URL ?? "http://localhost:4321",
  vite: { plugins: [tailwind()] },
});
