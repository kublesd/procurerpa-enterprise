import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// https://vitejs.dev/config/
export default defineConfig({
  envDir: path.resolve(__dirname, ".."),
  plugins: [react()],
  server: {
    port: 28080,
    proxy: {
      "/api": {
        target: "http://localhost:18000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 28080,
    // Skyvern 容器通过 host.docker.internal 访问供应商静态页，必须放行非 localhost 的 Host。
    allowedHosts: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
