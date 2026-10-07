import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Browser calls /api/... on port 5173, Vite forwards it to the FastAPI backend
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});