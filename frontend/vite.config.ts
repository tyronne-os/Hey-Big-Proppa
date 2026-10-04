import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8085,
    strictPort: true,   // never silently fall back to another port
    proxy: {
      "/api": "http://localhost:8086",
    },
  },
});
