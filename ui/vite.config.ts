import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The engine service normally listens on 127.0.0.1:8000. run.sh exports these
// when it is asked to use different ports, so the proxy follows the service
// instead of silently pointing at nothing.
// Declared locally rather than depending on @types/node: this config is the
// only file in the project that reads the process environment.
declare const process: { env: Record<string, string | undefined> };

const apiHost = process.env.API_HOST ?? "127.0.0.1";
const apiPort = process.env.API_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": `http://${apiHost}:${apiPort}`,
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
  },
});
