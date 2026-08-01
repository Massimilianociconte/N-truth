import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/app/",
  plugins: [
    react(),
    {
      name: "preserve-hatch-placeholder",
      generateBundle() {
        this.emitFile({ type: "asset", fileName: ".gitkeep", source: "" });
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/v1": "http://127.0.0.1:8765",
      "/health": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
