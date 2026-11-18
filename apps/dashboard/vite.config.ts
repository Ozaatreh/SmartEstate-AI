/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5174, // internal dashboard (the public marketing site uses 5173)
    strictPort: true,
    // The browser only talks to the Vite origin; /api is proxied to FastAPI (same-origin cookies).
    proxy: { "/api": { target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 700 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
