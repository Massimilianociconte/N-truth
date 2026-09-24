import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Target del proxy di sviluppo: default l'API locale di `ntruth-api`; si puo
// puntare altrove (per esempio un'altra porta) senza modificare il file.
// (niente @types/node nel progetto: accesso tipizzato localmente a process.env).
const nodeEnv = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
const apiTarget = nodeEnv?.NTRUTH_API_URL ?? "http://127.0.0.1:8765";

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
      "/v1": apiTarget,
      "/v7": apiTarget,
      "/v8": apiTarget,
      "/v9": apiTarget,
      "/health": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
