/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend so the browser only ever
// talks same-origin — no CORS configuration needed for normal dev use.
// Override the ports when something else already owns 5173 / 8787.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost:8787";
const DEV_PORT = Number(process.env.VITE_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
  server: {
    port: DEV_PORT,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
