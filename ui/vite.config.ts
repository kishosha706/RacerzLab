import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/echarts/") || id.includes("/node_modules/zrender/")) {
            return "charting";
          }
          if (
            id.includes("/node_modules/react/")
            || id.includes("/node_modules/react-dom/")
            || id.includes("/node_modules/scheduler/")
          ) {
            return "react-runtime";
          }
          if (id.includes("/node_modules/lucide-react/")) {
            return "icons";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    watch: {
      ignored: [
        "**/src-tauri/target/**",
        "**/src-tauri/target/**/*",
        "**/target/**",
        "**/target/**/*",
      ],
    },
  },
  clearScreen: false,
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
