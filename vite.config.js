import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy:
      process.env.VITE_TWINOPS_DATA_MODE === "live"
        ? {
            "/api": {
              target:
                process.env.TWINOPS_API_PROXY_TARGET ||
                "http://127.0.0.1:8000",
              changeOrigin: false,
            },
          }
        : undefined,
  },
});
