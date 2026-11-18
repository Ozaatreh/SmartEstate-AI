/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Public marketing website (Phase 7A). In development only the public API is proxied: the dashboard's internal
 * endpoints are not reachable through this origin. This is defence in depth only — FastAPI itself requires a
 * signed-in user for every non-public endpoint.
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api/v1/public": { target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  preview: { port: 4173 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
