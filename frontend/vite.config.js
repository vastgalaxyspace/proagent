import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const createApiProxy = (target) => ({
  "/health": { target, changeOrigin: true },
  "/ready": { target, changeOrigin: true },
  "/v1": { target, changeOrigin: true },
});

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = (env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001")
    .replace(/\/$/, "");

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: createApiProxy(apiTarget),
    },
    preview: {
      port: 4173,
      strictPort: true,
      proxy: createApiProxy(apiTarget),
    },
  };
});
