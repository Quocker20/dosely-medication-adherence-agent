import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      // /ws/dashboard nằm ngoài /api/v1 (xem api-contract.md Slice 8). Không có
      // dòng này thì socket đâm vào chính Vite và fail — bản build production
      // không lộ ra vì FastAPI serve luôn web/dist nên cùng origin.
      "/ws": { target: "ws://localhost:8000", ws: true, changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
